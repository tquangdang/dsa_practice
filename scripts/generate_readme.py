#!/usr/bin/env python3
"""Regenerate the README as a clean, professional DSA practice log.

Data sources:
  - Problem folders in the repo root (``NNNN-some-slug``).
  - LeetCode public GraphQL API for difficulty + topic tags (cached on disk).
  - git history for runtime / memory percentiles and the last-updated date.

The script only rewrites the region between the PROFILE markers and re-emits the
LeetHub topic block (between its own markers) verbatim, so LeetHub and this
generator never overwrite each other.

Every chart is emitted twice, once per :class:`Palette`, and referenced from the
README through a ``<picture>`` element so GitHub serves the variant matching the
reader's theme.
"""
from __future__ import annotations

import base64
import html
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = Path(__file__).resolve().parent / "leetcode_cache.json"
NEETCODE_FILE = Path(__file__).resolve().parent / "neetcode150.json"
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
USER_CACHE_FILE = Path(__file__).resolve().parent / "leetcode_user_cache.json"
ASSETS_DIR = REPO_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
HEATMAP_FILE = ASSETS_DIR / "activity-heatmap.svg"
BANNER_FILE = ASSETS_DIR / "stats-banner.svg"
TOPICS_FILE = ASSETS_DIR / "topics.svg"
NEETCODE_SVG_FILE = ASSETS_DIR / "neetcode.svg"
DIFFICULTY_FILE = ASSETS_DIR / "difficulty-donut.svg"

PROFILE_START = "<!-- PROFILE:START -->"
PROFILE_END = "<!-- PROFILE:END -->"
LEETHUB_START = "<!---LeetCode Topics Start-->"
LEETHUB_END = "<!---LeetCode Topics End-->"

DIFFICULTY_ORDER = {"Easy": 0, "Medium": 1, "Hard": 2}
DIFFICULTY_DOT = {"Easy": "\U0001F7E2", "Medium": "\U0001F7E1", "Hard": "\U0001F534"}

# Community-known approximate contest rating cut-offs for LeetCode badges.
RATING_TIERS = [(1850, "Knight"), (2200, "Guardian")]

TIME_RE = re.compile(
    r"Time:\s*([\d.]+)\s*ms\s*\(([\d.]+)%\),\s*Space:\s*([\d.]+)\s*MB\s*\(([\d.]+)%\)"
)


def run_git(args: list[str]) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def detect_repo_slug_and_branch() -> tuple[str, str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    branch = os.environ.get("GITHUB_REF_NAME", "").strip()
    if not repo:
        url = run_git(["remote", "get-url", "origin"]).strip()
        m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        repo = m.group(1) if m else "user/repo"
    if not branch:
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip() or "main"
    return repo, branch


def discover_problems() -> list[tuple[str, str]]:
    """Return (folder_name, title_slug) for every problem folder."""
    problems = []
    for entry in sorted(REPO_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        m = re.match(r"^(\d+)-(.+)$", entry.name)
        if m:
            problems.append((entry.name, m.group(2)))
    return problems


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fetch_leetcode(slug: str) -> dict | None:
    query = (
        "query q($titleSlug: String!){ question(titleSlug:$titleSlug){"
        " questionFrontendId title difficulty topicTags{ name } } }"
    )
    payload = json.dumps({"query": query, "variables": {"titleSlug": slug}}).encode()
    req = urllib.request.Request(
        "https://leetcode.com/graphql",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (readme-generator)",
            "Referer": f"https://leetcode.com/problems/{slug}/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        q = (data.get("data") or {}).get("question")
        if not q:
            return None
        return {
            "id": q.get("questionFrontendId"),
            "title": q.get("title"),
            "difficulty": q.get("difficulty"),
            "topics": [t["name"] for t in (q.get("topicTags") or [])],
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def difficulty_from_local_readme(folder: str) -> str | None:
    readme = REPO_ROOT / folder / "README.md"
    if not readme.exists():
        return None
    m = re.search(r"<h3>(Easy|Medium|Hard)</h3>", readme.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def title_from_local_readme(folder: str) -> str | None:
    readme = REPO_ROOT / folder / "README.md"
    if not readme.exists():
        return None
    text = readme.read_text(encoding="utf-8")
    m = re.search(r"<h2><a[^>]*>(?:\d+\.\s*)?(.*?)</a></h2>", text)
    return m.group(1).strip() if m else None


def get_meta(folder: str, slug: str, cache: dict) -> dict:
    if slug in cache and cache[slug].get("difficulty"):
        return cache[slug]
    meta = fetch_leetcode(slug)
    if meta is None:
        meta = {
            "id": (re.match(r"^(\d+)", folder).group(1).lstrip("0") or "0"),
            "title": title_from_local_readme(folder) or slug.replace("-", " ").title(),
            "difficulty": difficulty_from_local_readme(folder) or "Easy",
            "topics": cache.get(slug, {}).get("topics", []),
        }
    else:
        time.sleep(0.4)  # be polite to the API
    cache[slug] = meta
    return meta


def runtime_for(folder: str) -> dict | None:
    subjects = run_git(["log", "--format=%s", "--", folder]).splitlines()
    for subject in subjects:
        m = TIME_RE.search(subject)
        if m:
            return {
                "time_ms": float(m.group(1)),
                "time_pct": float(m.group(2)),
                "space_mb": float(m.group(3)),
                "space_pct": float(m.group(4)),
            }
    return None


def last_updated() -> str | None:
    out = run_git(["log", "-1", "--format=%ad", "--date=short"]).strip()
    return out or None


def solved_date_for(folder: str) -> date | None:
    """Earliest commit date touching the folder (i.e. when it was first solved)."""
    out = run_git(
        ["log", "--reverse", "--format=%ad", "--date=short", "--", folder]
    ).splitlines()
    for line in out:
        line = line.strip()
        if line:
            try:
                return date.fromisoformat(line)
            except ValueError:
                return None
    return None


def load_neetcode() -> dict[str, list[str]]:
    if NEETCODE_FILE.exists():
        try:
            return json.loads(NEETCODE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def leetcode_username() -> str | None:
    env = os.environ.get("LEETCODE_USERNAME", "").strip()
    if env:
        return env
    return (load_config().get("leetcode_username") or "").strip() or None


def fetch_user_ranking(username: str) -> dict | None:
    """Fetch live overall + contest ranking, falling back to the cached copy."""
    query = (
        "query userRanking($username: String!){"
        " matchedUser(username: $username){ profile{ ranking } }"
        " userContestRanking(username: $username){"
        " attendedContestsCount rating globalRanking totalParticipants"
        " topPercentage badge{ name } } }"
    )
    payload = json.dumps({"query": query, "variables": {"username": username}}).encode()
    req = urllib.request.Request(
        "https://leetcode.com/graphql",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (readme-generator)",
            "Referer": f"https://leetcode.com/u/{username}/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        root = data.get("data") or {}
        matched = root.get("matchedUser")
        if not matched:
            raise ValueError("user not found")
        contest = root.get("userContestRanking") or {}
        badge = (contest.get("badge") or {}).get("name")
        ranking = {
            "username": username,
            "overall_ranking": (matched.get("profile") or {}).get("ranking"),
            "contest_rating": contest.get("rating"),
            "contest_global_ranking": contest.get("globalRanking"),
            "contest_total_participants": contest.get("totalParticipants"),
            "contest_top_percentage": contest.get("topPercentage"),
            "contest_attended": contest.get("attendedContestsCount"),
            "contest_badge": badge,
        }
        USER_CACHE_FILE.write_text(
            json.dumps(ranking, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return ranking
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        if USER_CACHE_FILE.exists():
            try:
                return json.loads(USER_CACHE_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        return None


def build_problems() -> list[dict]:
    cache = load_cache()
    problems = []
    for folder, slug in discover_problems():
        meta = get_meta(folder, slug, cache)
        difficulty = meta.get("difficulty") or "Easy"
        problems.append(
            {
                "folder": folder,
                "slug": slug,
                "id": int(re.match(r"^(\d+)", folder).group(1)),
                "title": meta.get("title") or slug,
                "difficulty": difficulty,
                "topics": meta.get("topics") or [],
                "runtime": runtime_for(folder),
                "date": solved_date_for(folder),
            }
        )
    save_cache(cache)
    return problems


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def _shield_enc(s: str) -> str:
    """Encode a shields.io path segment (order matters)."""
    return (
        str(s)
        .replace("%", "%25")
        .replace("#", "%23")
        .replace(",", "%2C")
        .replace("/", "%2F")
        .replace("-", "--")
        .replace("_", "__")
        .replace(" ", "_")
    )


def badge(label: str, message: str, color: str, style: str = "flat-square",
          logo: str | None = None) -> str:
    url = (
        f"https://img.shields.io/badge/"
        f"{_shield_enc(label)}-{_shield_enc(message)}-{color}?style={style}"
    )
    if logo:
        url += f"&logo={logo}&logoColor=white"
    return f"![{label}]({url})"


def slug_to_category(neetcode: dict) -> dict:
    mapping: dict[str, str] = {}
    for category, slugs in neetcode.items():
        for s in slugs:
            mapping.setdefault(s, category)
    return mapping


def next_rating_tier(rating: float | None) -> tuple[str, int, int] | None:
    if rating is None:
        return None
    for cutoff, name in RATING_TIERS:
        if rating < cutoff:
            return name, cutoff, cutoff - round(rating)
    return None


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
# A README SVG is served through GitHub's camo proxy as an <img>, so it cannot
# see the page theme. Rather than hunt for colours that survive both
# backgrounds (there aren't many -- a blue dark enough to read on white is
# invisible on #0d1117), each chart is rendered once per palette and the README
# picks between them with <picture media="(prefers-color-scheme: dark)">.
#
# Values come from GitHub Primer, which is already tuned against exactly these
# two backgrounds. Roles carry the contrast threshold they must clear:
#   * text (labels, counts)      >= 4.5:1  vs bg   -- WCAG 1.4.3
#   * large text (>=24px values) >= 3.0:1  vs bg   -- WCAG 1.4.3 (large)
#   * graphics (bars, rings)     >= 3.0:1  vs bg   -- WCAG 1.4.11
#   * decoration (frame, track)  no minimum
# scripts/check_contrast.py enforces all of this against the emitted SVGs.


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str          # the GitHub background this variant is read against
    muted: str       # secondary text: axis labels, legends, captions
    frame: str       # sketched card border (decorative)
    divider: str     # tile dividers (decorative)
    track: str       # unfilled bar/ring background (decorative)
    accent: str      # primary blue: headline numbers, progress
    purple: str      # contest tile
    # Difficulty comes in two grades. The small coloured counts are text and
    # owe 4.5:1; arcs, bars and swatches are graphics and owe only 3:1, which
    # buys a brighter amber than a text-legal one could ever be on white.
    easy: str
    medium: str
    hard: str
    easy_fill: str
    medium_fill: str
    hard_fill: str
    ramp_lo: str     # topic bars, smallest count
    ramp_hi: str     # topic bars, largest count
    sheen: str       # rotating highlight on the NeetCode ring (decorative)
    glint: str       # sweeping gradient highlight (decorative)
    heat: tuple[str, str, str, str, str]  # heatmap levels 0..4

    @property
    def file_suffix(self) -> str:
        return "" if self.name == "light" else f"-{self.name}"

    def difficulty(self, name: str) -> str:
        """Text-grade difficulty colour (>=4.5:1)."""
        return {"Easy": self.easy, "Medium": self.medium, "Hard": self.hard}[name]

    def difficulty_fill(self, name: str) -> str:
        """Graphic-grade difficulty colour (>=3:1) for arcs, bars, swatches."""
        return {"Easy": self.easy_fill, "Medium": self.medium_fill,
                "Hard": self.hard_fill}[name]

    def ramp(self, f: float) -> str:
        """Interpolate the topic-bar ramp at fraction ``f`` in [0, 1].

        The ramp runs light-to-dark on white and dim-to-bright on black, so
        "bigger" always means "more contrast against the page" -- and both
        endpoints clear 3:1, which the old single Material ramp did not.
        """
        lo = tuple(int(self.ramp_lo[i:i + 2], 16) for i in (1, 3, 5))
        hi = tuple(int(self.ramp_hi[i:i + 2], 16) for i in (1, 3, 5))
        r, g, b = (round(lo[i] + (hi[i] - lo[i]) * f) for i in range(3))
        return f"#{r:02x}{g:02x}{b:02x}"

    def hexes(self) -> set[str]:
        """Every colour this palette is allowed to put on the page."""
        fields = (
            self.muted, self.frame, self.divider, self.track, self.accent,
            self.purple, self.easy, self.medium, self.hard, self.easy_fill,
            self.medium_fill, self.hard_fill, self.ramp_lo, self.ramp_hi,
            self.sheen, self.glint,
        )
        return {c.lower() for c in (*fields, *self.heat)}


LIGHT = Palette(
    name="light",
    bg="#ffffff",
    muted="#656d76",
    frame="#afb8c1",
    divider="#d1d9e0",
    track="#d0d7de",
    accent="#0969da",
    purple="#8250df",
    easy="#1a7f37",
    medium="#9a6700",
    hard="#cf222e",
    easy_fill="#2da44e",
    medium_fill="#bf8700",
    hard_fill="#fa4549",
    ramp_lo="#218bff",
    ramp_hi="#0550ae",
    sheen="#b6e3ff",
    glint="#ffffff",
    heat=("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
)

DARK = Palette(
    name="dark",
    bg="#0d1117",
    muted="#8b949e",
    frame="#484f58",
    divider="#3d444d",
    track="#30363d",
    accent="#58a6ff",
    purple="#a371f7",
    easy="#3fb950",
    medium="#d29922",
    hard="#f85149",
    # On #0d1117 the text-grade colours are already vivid, so graphics reuse them.
    easy_fill="#3fb950",
    medium_fill="#d29922",
    hard_fill="#f85149",
    ramp_lo="#0969da",
    ramp_hi="#79c0ff",
    sheen="#b6e3ff",
    glint="#ffffff",
    heat=("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"),
)

PALETTES = (LIGHT, DARK)

# Every card is authored at this width and rendered at width="100%", so the
# stack of charts lines up down the page and stroke weights stay proportional.
CARD_W = 880

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Charts always encode their final frame in the base attributes; the SMIL
# animations below only add motion on top. SMIL is used (not CSS @keyframes)
# because GitHub renders README SVGs through its camo proxy in a sandbox that
# freezes CSS animations at frame 0 -- SMIL still runs there, as it does for
# the many animated-SVG READMEs in the wild (typing banners, contribution
# snake, etc.). Flip ANIMATIONS off to emit the plain static charts.
ANIMATIONS = True


def _delayed(attr: str, hold: str, final: str, delay: float, dur: float) -> str:
    """One-shot SMIL that holds ``hold`` for ``delay`` then eases to ``final``
    and freezes. begin=0 with a held key avoids any base-state flash."""
    if not ANIMATIONS:
        return ""
    total = delay + dur
    kt = (delay / total) if total else 0.0
    return (
        f'<animate attributeName="{attr}" values="{hold};{hold};{final}" '
        f'keyTimes="0;{kt:.3f};1" dur="{total:.3f}s" fill="freeze"/>'
    )


def anim_fade(delay: float = 0.0, dur: float = 0.5) -> str:
    return _delayed("opacity", "0", "1", delay, dur)


def anim_grow_width(final: float, delay: float = 0.0, dur: float = 0.6) -> str:
    return _delayed("width", "0", f"{final:.1f}", delay, dur)


def anim_draw(dash: float, circ: float, delay: float = 0.0,
              dur: float = 0.8) -> str:
    return _delayed(
        "stroke-dasharray", f"0 {circ:.2f}", f"{dash:.2f} {circ:.2f}", delay, dur
    )


def anim_slideup(delay: float = 0.0, dur: float = 0.5) -> str:
    if not ANIMATIONS:
        return ""
    total = delay + dur
    kt = (delay / total) if total else 0.0
    return (
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0 8;0 8;0 0" keyTimes="0;{kt:.3f};1" dur="{total:.3f}s" '
        f'fill="freeze"/>' + anim_fade(delay, dur)
    )


def anim_pulse(dur: float = 2.2) -> str:
    if not ANIMATIONS:
        return ""
    return (
        f'<animate attributeName="opacity" values="1;.4;1" dur="{dur}s" '
        f'repeatCount="indefinite"/>'
    )


def anim_spin(cx: float, cy: float, dur: float = 4.0) -> str:
    if not ANIMATIONS:
        return ""
    return (
        f'<animateTransform attributeName="transform" type="rotate" '
        f'from="0 {cx} {cy}" to="360 {cx} {cy}" dur="{dur}s" '
        f'repeatCount="indefinite"/>'
    )


def anim_sweep_x(x0: float, x1: float, dur: float = 6.0) -> str:
    if not ANIMATIONS:
        return ""
    return (
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="{x0:.0f} 0;{x1:.0f} 0" dur="{dur}s" repeatCount="indefinite"/>'
    )


# ---- Doodle (hand-drawn) styling toolkit ----
# Everything here is self-contained (inline data-URI font, SVG filters and
# patterns) so it renders inside GitHub's <img>/camo sandbox, unlike external
# webfonts. Flip DOODLE off to fall back to the clean charts.
DOODLE = True

FULL_FONTS = {400: FONTS_DIR / "kalam-regular.woff2",
              700: FONTS_DIR / "kalam-bold.woff2"}
_FONT_CACHE: dict[tuple[int, str], str] = {}

# Rendered glyphs, harvested from the chart's own <text> elements. <title>
# tooltips are excluded: GitHub shows them as native tooltips, not as SVG text.
_TEXT_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_TAG_RE = re.compile(r"<[^>]*>")
_BOLD_RE = re.compile(r'font-weight="(?:600|700)"')


def rendered_charsets(markup: str) -> tuple[str, str]:
    """Split the glyphs a chart draws into (regular, bold) character sets.

    Bold is applied per-<text>, and in practice only to numbers, so the bold
    subset lands around 20 glyphs while the regular one carries the prose.
    """
    regular: set[str] = set()
    bold: set[str] = set()
    for attrs, inner in _TEXT_RE.findall(markup):
        target = bold if (_BOLD_RE.search(attrs) or _BOLD_RE.search(inner)) else regular
        target.update(html.unescape(_TAG_RE.sub("", inner)))
    return "".join(sorted(regular)), "".join(sorted(bold))


def _font_data_uri(weight: int, chars: str) -> str:
    """Base64 woff2 for ``weight``, subset to ``chars``.

    Kalam ships ~600 glyphs; a chart draws at most ~75 of them. Subsetting per
    chart matters because the font is inlined into every SVG, and there are ten
    of them (five charts x two themes). Falls back to the full face when
    fontTools/brotli aren't installed, so generation never hard-fails on a
    machine that only wants the README text refreshed.
    """
    key = (weight, chars)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    src = FULL_FONTS[weight]
    data = b""
    try:
        from fontTools import subset as ftsubset

        opts = ftsubset.Options(
            flavor="woff2", desubroutinize=True, layout_features=[],
            notdef_outline=False, recommended_glyphs=False,
        )
        font = ftsubset.load_font(str(src), opts)
        subsetter = ftsubset.Subsetter(options=opts)
        subsetter.populate(text=chars)
        subsetter.subset(font)
        buf = io.BytesIO()
        ftsubset.save_font(font, buf, opts)
        font.close()
        data = buf.getvalue()
    except Exception:  # noqa: BLE001 - any subsetting failure falls back whole
        try:
            data = src.read_bytes()
        except OSError:
            data = b""
    uri = (
        "data:font/woff2;base64," + base64.b64encode(data).decode("ascii")
        if data else ""
    )
    _FONT_CACHE[key] = uri
    return uri


def font_face_defs(regular_chars: str, bold_chars: str) -> str:
    """Embed the Kalam handwriting font as base64 @font-face, subset to use."""
    if not DOODLE:
        return ""
    faces = ""
    for weight, chars in ((400, regular_chars), (700, bold_chars)):
        if not chars:
            continue
        uri = _font_data_uri(weight, chars)
        if uri:
            faces += (
                "@font-face{font-family:'Doodle';font-style:normal;"
                f"font-weight:{weight};src:url({uri}) format('woff2');}}"
            )
    return f"<style>{faces}</style>" if faces else ""


def doodle_font_family() -> str:
    if DOODLE:
        return "'Doodle','Comic Sans MS','Segoe Print','Bradley Hand',cursive"
    return "-apple-system,Segoe UI,Helvetica,Arial,sans-serif"


def rough_filter_defs(boil: bool = True) -> str:
    """A hand-drawn wobble filter; animating the turbulence seed makes edges
    'boil' like a sketch being redrawn frame to frame."""
    if not DOODLE:
        return ""
    seed_anim = (
        '<animate attributeName="seed" values="7;19;31;11" dur="0.5s" '
        'calcMode="discrete" repeatCount="indefinite"/>'
        if (boil and ANIMATIONS) else ""
    )
    return (
        '<filter id="rough" x="-6%" y="-6%" width="112%" height="112%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.018 0.028" '
        f'numOctaves="2" seed="7" result="n">{seed_anim}</feTurbulence>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="3.4" '
        'xChannelSelector="R" yChannelSelector="G"/>'
        '</filter>'
    )


def hachure_pattern(pid: str, color: str, gap: int = 5, sw: float = 1.6,
                    angle: int = 45, base_opacity: float = 0.22) -> str:
    """A pencil-shading pattern: a faint same-color base tile plus parallel
    diagonal strokes in ``color``. The base tint makes filled bars read as a
    solid-ish colored pill (rather than thin lines over the page); legibility
    is carried by the surrounding stroke, which is what clears 3:1."""
    base = (
        f'<rect width="{gap}" height="{gap}" fill="{color}" '
        f'fill-opacity="{base_opacity}"/>'
        if base_opacity else ""
    )
    return (
        f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="{gap}" '
        f'height="{gap}" patternTransform="rotate({angle})">'
        f'{base}<line x1="0" y1="0" x2="0" y2="{gap}" stroke="{color}" '
        f'stroke-width="{sw}"/></pattern>'
    )


def svg_open(width: float, height: float, extra: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="{doodle_font_family()}"{extra}>'
    )


def finish_svg(open_tag: str, body: str, extra_defs: str = "") -> str:
    """Close the SVG, injecting <defs> once the drawn glyphs are known."""
    regular, bold = rendered_charsets(body)
    inner = font_face_defs(regular, bold) + rough_filter_defs() + extra_defs
    defs = f"<defs>{inner}</defs>" if inner else ""
    return f"{open_tag}\n{defs}\n{body}\n</svg>\n"


def rough_g(inner: str) -> str:
    """Wrap shape markup so it picks up the hand-drawn wobble/boil filter."""
    if not DOODLE or not inner:
        return inner
    return f'<g filter="url(#rough)">{inner}</g>'


def anim_pop(cx: float, cy: float, inner: str, delay: float = 0.0,
             dur: float = 0.5) -> str:
    """Centered pop-in (scale 0 -> slight overshoot -> 1) around (cx, cy)."""
    if not (DOODLE and ANIMATIONS):
        return inner
    total = delay + dur
    kt1 = delay / total if total else 0.0
    kt2 = (delay + dur * 0.7) / total if total else 0.7
    return (
        f'<g transform="translate({cx:.1f} {cy:.1f})"><g>'
        f'<animateTransform attributeName="transform" type="scale" '
        f'values="0;0;1.12;1" keyTimes="0;{kt1:.3f};{kt2:.3f};1" '
        f'dur="{total:.3f}s" fill="freeze"/>'
        f'<g transform="translate({-cx:.1f} {-cy:.1f})">{inner}</g></g></g>'
    )


def _xml(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _arc_circle(cx: float, cy: float, r: float, sw: int, color: str,
                frac: float, offset: float, inner: str = "") -> str:
    """A donut/ring segment via stroke-dasharray (group is rotated -90).

    ``inner`` lets callers embed a SMIL child (e.g. a draw-on animation).
    """
    c = 2 * math.pi * r
    dash = max(0.0, frac) * c
    open_tag = (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
        f'stroke-width="{sw}" stroke-dasharray="{dash:.2f} {c:.2f}" '
        f'stroke-dashoffset="{-offset * c:.2f}"'
    )
    return f'{open_tag}>{inner}</circle>' if inner else f'{open_tag} />'


def card_frame(width: float, height: float, pal: Palette) -> str:
    return (
        f'<rect x="4" y="4" width="{width - 8:.0f}" height="{height - 8:.0f}" '
        f'rx="14" fill="none" stroke="{pal.frame}" stroke-width="1.8" '
        f'stroke-linecap="round"/>'
    )


def build_heatmap_svg(dated: list[dict], today: date, week_start: date,
                      pal: Palette, weeks: int = 53) -> str:
    """Render a GitHub-style contribution heatmap as a standalone SVG string."""
    counts_by_day = Counter(p["date"] for p in dated)
    gap = 3
    left_pad, right_pad, top_pad = 34, 14, 22
    # Solve the cell size from the card width instead of the other way round,
    # so the heatmap ends up exactly as wide as every other chart.
    step = (CARD_W - left_pad - right_pad + gap) / weeks
    cell = step - gap
    grid_start = week_start - timedelta(weeks=weeks - 1)
    grid_h = 7 * step - gap
    legend_h = 26
    width = CARD_W
    height = top_pad + grid_h + legend_h

    def level(c: int) -> int:
        return 0 if c <= 0 else min(4, c)

    body = []
    # Hand-drawn shapes (cells, legend swatches, frame) go under the wobble
    # filter; text labels stay crisp for legibility.
    shp = [card_frame(width, height, pal)]

    # Day cells, grouped per week column so the reveal sweeps left to right.
    for wk in range(weeks):
        col_cells = []
        for wd in range(7):
            day = grid_start + timedelta(days=wk * 7 + wd)
            if day > today:
                continue
            c = counts_by_day.get(day, 0)
            x = left_pad + wk * step
            y = top_pad + wd * step
            noun = "solve" if c == 1 else "solves"
            pulse = anim_pulse(2.2) if day == today else ""
            col_cells.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell:.2f}" '
                f'height="{cell:.2f}" rx="3" ry="3" fill="{pal.heat[level(c)]}">'
                f'<title>{day.isoformat()}: {c} {noun}</title>{pulse}</rect>'
            )
        if col_cells:
            shp.append(f'<g>{anim_fade(wk * 0.012, 0.45)}')
            shp.extend(col_cells)
            shp.append("</g>")

    # Legend swatches (shapes).
    ly = top_pad + grid_h + 8
    lx = left_pad + 28
    for lv in range(5):
        shp.append(
            f'<rect x="{lx:.2f}" y="{ly:.2f}" width="{cell:.2f}" '
            f'height="{cell:.2f}" rx="3" ry="3" fill="{pal.heat[lv]}"/>'
        )
        lx += step
    body.append(rough_g("".join(shp)))

    # Month labels along the top (when the column's month changes).
    prev_month = None
    for wk in range(weeks):
        month = (grid_start + timedelta(days=wk * 7)).month
        if month != prev_month:
            x = left_pad + wk * step
            body.append(
                f'<text x="{x:.2f}" y="{top_pad - 8}" fill="{pal.muted}">'
                f'{MONTH_ABBR[month - 1]}</text>'
            )
            prev_month = month

    # Weekday labels (Mon / Wed / Fri, like GitHub).
    for wd, lbl in {0: "Mon", 2: "Wed", 4: "Fri"}.items():
        y = top_pad + wd * step + cell - 3
        body.append(
            f'<text x="{left_pad - 6}" y="{y:.2f}" text-anchor="end" '
            f'fill="{pal.muted}">{lbl}</text>'
        )

    # Legend labels (crisp text).
    body.append(
        f'<text x="{left_pad}" y="{ly + cell - 3:.2f}" fill="{pal.muted}">Less</text>'
    )
    body.append(
        f'<text x="{lx + 2:.2f}" y="{ly + cell - 3:.2f}" fill="{pal.muted}">More</text>'
    )
    return finish_svg(
        svg_open(width, height, ' font-size="11"'), "\n".join(body)
    )


def build_stats_banner_svg(total: int, easy: int, medium: int, hard: int,
                           nc_done: int, nc_total: int,
                           ranking: dict | None, pal: Palette) -> str:
    """Render a hero stats card (4 tiles) as a standalone SVG string."""
    width, height = CARD_W, 160
    pad = 28
    tw = (width - 2 * pad) / 4

    def cx(i: int) -> float:
        return pad + tw * (i + 0.5)

    extra = (
        '<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{pal.accent}" stop-opacity="0"/>'
        f'<stop offset="0.5" stop-color="{pal.accent}" stop-opacity="0.28"/>'
        f'<stop offset="1" stop-color="{pal.accent}" stop-opacity="0"/>'
        '</linearGradient>'
        f'<clipPath id="bclip"><rect width="{width}" height="{height}" rx="10"/>'
        '</clipPath>'
        + hachure_pattern("hachE", pal.easy_fill)
        + hachure_pattern("hachM", pal.medium_fill)
        + hachure_pattern("hachH", pal.hard_fill)
    )

    body: list[str] = []
    # Frame + dividers are hand-drawn (rough); text stays crisp.
    shp = [card_frame(width, height, pal)]
    for i in (1, 2, 3):
        x = pad + tw * i
        shp.append(
            f'<line x1="{x:.0f}" y1="34" x2="{x:.0f}" y2="130" '
            f'stroke="{pal.divider}" stroke-width="1.4">{anim_fade(0.2, 0.7)}</line>'
        )
    body.append(rough_g("".join(shp)))

    def label(i: int, s: str) -> None:
        body.append(
            f'<text x="{cx(i):.0f}" y="52" text-anchor="middle" fill="{pal.muted}" '
            f'font-size="12" letter-spacing="1.5">{s}</text>'
        )

    def value(i: int, s: str, color: str) -> None:
        body.append(
            f'<text x="{cx(i):.0f}" y="100" text-anchor="middle" fill="{color}" '
            f'font-size="40" font-weight="700">{s}</text>'
        )

    def sub(i: int, s: str) -> None:
        body.append(
            f'<text x="{cx(i):.0f}" y="124" text-anchor="middle" fill="{pal.muted}" '
            f'font-size="13">{s}</text>'
        )

    # Tile 0: total solved.
    body.append(f'<g>{anim_slideup(0.0)}')
    label(0, "SOLVED")
    value(0, str(total), pal.accent)
    sub(0, "Python")
    body.append("</g>")

    # Tile 1: difficulty split (stacked bar + coloured counts).
    body.append(f'<g>{anim_slideup(0.08)}')
    label(1, "BY DIFFICULTY")
    bw = tw - 56
    bx = cx(1) - bw / 2
    by, bh = 74, 14
    tot = max(1, easy + medium + hard)
    we, wm = bw * easy / tot, bw * medium / tot
    wh = bw - we - wm
    body.append(rough_g(
        f'<rect x="{bx:.1f}" y="{by}" width="{we:.1f}" height="{bh}" '
        f'fill="url(#hachE)" stroke="{pal.easy_fill}" stroke-width="1.3"/>'
        f'<rect x="{bx + we:.1f}" y="{by}" width="{wm:.1f}" height="{bh}" '
        f'fill="url(#hachM)" stroke="{pal.medium_fill}" stroke-width="1.3"/>'
        f'<rect x="{bx + we + wm:.1f}" y="{by}" width="{wh:.1f}" height="{bh}" '
        f'fill="url(#hachH)" stroke="{pal.hard_fill}" stroke-width="1.3"/>'
    ))
    body.append(
        f'<text x="{cx(1):.0f}" y="114" text-anchor="middle" font-size="14" '
        f'font-weight="600"><tspan fill="{pal.easy}">{easy}</tspan>'
        f'<tspan fill="{pal.muted}"> / </tspan><tspan fill="{pal.medium}">{medium}'
        f'</tspan><tspan fill="{pal.muted}"> / </tspan>'
        f'<tspan fill="{pal.hard}">{hard}</tspan></text>'
    )
    body.append("</g>")

    # Tile 2: NeetCode 150 progress.
    body.append(f'<g>{anim_slideup(0.16)}')
    label(2, "NEETCODE 150")
    if nc_total:
        value(2, f"{round(nc_done / nc_total * 100)}%", pal.accent)
        sub(2, f"{nc_done} / {nc_total}")
    else:
        value(2, "—", pal.accent)
    body.append("</g>")

    # Tile 3: contest rating / global rank.
    body.append(f'<g>{anim_slideup(0.24)}')
    rating = ranking.get("contest_rating") if ranking else None
    rank = ranking.get("overall_ranking") if ranking else None
    if rating:
        label(3, "CONTEST")
        value(3, f"{rating:.0f}", pal.purple)
        sub(3, f"Rank #{fmt_int(rank)}" if rank else "rated")
    elif rank:
        label(3, "GLOBAL RANK")
        value(3, f"#{fmt_int(rank)}", pal.purple)
        sub(3, "worldwide")
    else:
        label(3, "CONTEST")
        value(3, "—", pal.purple)
        sub(3, "not yet")
    body.append("</g>")

    # Continuous accent: a faint diagonal glint sweeping across the banner.
    # Skew lives on an outer group so the SMIL translate can drive the sweep.
    body.append(
        f'<g clip-path="url(#bclip)"><g transform="skewX(-18)">'
        f'<rect x="-100" y="-20" width="80" height="{height + 40}" '
        f'fill="url(#shine)">{anim_sweep_x(0, width + 220, 6.5)}</rect>'
        f'</g></g>'
    )
    return finish_svg(svg_open(width, height), "\n".join(body), extra)


def build_topics_bar_svg(items: list[tuple[str, int]], pal: Palette,
                         top_n: int = 16) -> str:
    """Horizontal bar chart of topic counts (sorted desc), as an SVG string."""
    rows = items[:top_n]
    width = CARD_W
    label_w = 210
    bar_x = label_w + 10
    bar_max = width - bar_x - 56
    row_h, bar_h, top_pad = 24, 14, 16
    height = top_pad + len(rows) * row_h + 16
    max_count = max((n for _, n in rows), default=1)

    shp = [card_frame(width, height, pal)]
    texts: list[str] = []
    hach_defs: list[str] = []
    top_geom = None
    for i, (topic, n) in enumerate(rows):
        row_y = top_pad + i * row_h
        by = row_y + (row_h - bar_h) / 2
        ty = row_y + row_h / 2 + 4
        frac = n / max_count if max_count else 0
        fill_len = bar_max * frac
        col = pal.ramp(frac)
        pid = f"hachT{i}"
        hach_defs.append(hachure_pattern(pid, col))
        if i == 0:
            top_geom = (by, fill_len)
        shp.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{bar_max}" height="{bar_h}" '
            f'rx="6" ry="6" fill="{pal.track}" />'
        )
        shp.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{fill_len:.1f}" '
            f'height="{bar_h}" rx="6" ry="6" fill="url(#{pid})" '
            f'stroke="{col}" stroke-width="1.3">'
            f'{anim_grow_width(fill_len, i * 0.04, 0.6)}</rect>'
        )
        texts.append(
            f'<text x="{label_w - 6}" y="{ty:.0f}" text-anchor="end" '
            f'fill="{pal.muted}">{_xml(topic)}</text>'
        )
        texts.append(
            f'<text x="{bar_x + fill_len + 8:.0f}" y="{ty:.0f}" '
            f'fill="{pal.muted}" font-weight="700">{anim_fade(0.4, 0.6)}{n}</text>'
        )

    # Continuous accent: a soft glint sweeping the longest (top) bar.
    glint = ""
    tshine_def = ""
    if top_geom:
        top_by, top_len = top_geom
        tshine_def = (
            '<linearGradient id="tshine" x1="0" y1="0" x2="1" y2="0">'
            f'<stop offset="0" stop-color="{pal.glint}" stop-opacity="0"/>'
            f'<stop offset="0.5" stop-color="{pal.glint}" stop-opacity="0.55"/>'
            f'<stop offset="1" stop-color="{pal.glint}" stop-opacity="0"/>'
            '</linearGradient>'
            f'<clipPath id="tbar"><rect x="{bar_x}" y="{top_by:.0f}" '
            f'width="{top_len:.1f}" height="{bar_h}" rx="6" ry="6"/></clipPath>'
        )
        glint = (
            f'<g clip-path="url(#tbar)"><rect x="{bar_x - 44}" '
            f'y="{top_by:.0f}" width="44" height="{bar_h}" fill="url(#tshine)">'
            f'{anim_sweep_x(0, top_len + 44, 3.2)}</rect></g>'
        )

    body = [rough_g("".join(shp)), *texts]
    if glint:
        body.append(glint)
    return finish_svg(
        svg_open(width, height, ' font-size="13"'),
        "\n".join(body),
        "".join(hach_defs) + tshine_def,
    )


def build_difficulty_donut_svg(easy: int, medium: int, hard: int,
                               pal: Palette) -> str:
    """Donut chart of the difficulty split with a legend, as an SVG string."""
    width, height = CARD_W, 210
    cx, cy, r, sw = 132, 105, 78, 28
    total = easy + medium + hard
    segs = [
        ("Easy", easy, pal.easy_fill),
        ("Medium", medium, pal.medium_fill),
        ("Hard", hard, pal.hard_fill),
    ]
    c = 2 * math.pi * r
    seg_pat = {"Easy": "hachE", "Medium": "hachM", "Hard": "hachH"}
    extra = (
        hachure_pattern("hachE", pal.easy_fill)
        + hachure_pattern("hachM", pal.medium_fill)
        + hachure_pattern("hachH", pal.hard_fill, gap=5)
    )

    # Legend rows: swatch, name, share bar, count. The bar earns the width the
    # card gained, instead of leaving the right third empty.
    row_y0, row_dy = 70, 40
    swatch_x, name_x = 300, 326
    bar_x, bar_w, bar_h = 430, 360, 12
    count_x = width - 24

    # Hand-drawn shapes: frame, track ring, arcs, legend chips + share bars.
    shp = [
        card_frame(width, height, pal),
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{pal.track}" '
        f'stroke-width="{sw}" />',
        f'<g transform="rotate(-90 {cx} {cy})">',
    ]
    cum = 0.0
    ai = 0
    for _, val, color in segs:
        if val <= 0 or total <= 0:
            continue
        frac = val / total
        draw = anim_draw(frac * c, c, ai * 0.2, 0.7)
        shp.append(_arc_circle(cx, cy, r, sw, color, frac, cum, inner=draw))
        cum += frac
        ai += 1
    shp.append("</g>")

    for i, (name, val, color) in enumerate(segs):
        ry = row_y0 + i * row_dy
        frac = (val / total) if total else 0
        fill_len = bar_w * frac
        shp.append(
            f'<rect x="{swatch_x}" y="{ry - 12}" width="16" height="16" rx="3" '
            f'fill="url(#{seg_pat[name]})" stroke="{color}" stroke-width="1.2" />'
        )
        shp.append(
            f'<rect x="{bar_x}" y="{ry - 11}" width="{bar_w}" height="{bar_h}" '
            f'rx="6" ry="6" fill="{pal.track}" />'
        )
        if fill_len > 0:
            shp.append(
                f'<rect x="{bar_x}" y="{ry - 11}" width="{fill_len:.1f}" '
                f'height="{bar_h}" rx="6" ry="6" fill="url(#{seg_pat[name]})" '
                f'stroke="{color}" stroke-width="1.2">'
                f'{anim_grow_width(fill_len, 0.5 + i * 0.12, 0.6)}</rect>'
            )
    body = [rough_g("".join(shp))]

    # Center count pops in; legend labels stay crisp.
    body.append(anim_pop(
        cx, cy,
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="38" '
        f'font-weight="700" fill="{pal.accent}">{total}</text>'
        f'<text x="{cx}" y="{cy + 24}" text-anchor="middle" font-size="13" '
        f'fill="{pal.muted}">solved</text>',
        0.5, 0.5,
    ))
    for i, (name, val, color) in enumerate(segs):
        ry = row_y0 + i * row_dy
        pct = (val / total * 100) if total else 0
        body.append(
            f'<text x="{name_x}" y="{ry}" font-size="15" fill="{pal.muted}">'
            f'{anim_fade(0.5 + i * 0.12, 0.5)}{name}</text>'
        )
        body.append(
            f'<text x="{count_x}" y="{ry}" text-anchor="end" font-size="14" '
            f'font-weight="700" fill="{pal.muted}">'
            f'{anim_fade(0.5 + i * 0.12, 0.5)}{val} ({pct:.0f}%)</text>'
        )
    return finish_svg(svg_open(width, height), "\n".join(body), extra)


def build_neetcode_svg(cat_rows: list[tuple], nc_done: int, nc_total: int,
                       nc_frac: float, pal: Palette) -> str:
    """Overall progress ring + per-category bars, as an SVG string.

    ``cat_rows`` is a list of ``(frac, category, done, total)`` sorted desc.
    """
    width = CARD_W
    label_w = 210
    bar_x = label_w + 10
    bar_max = width - bar_x - 66
    row_h, bar_h = 24, 14
    top_h = 132
    height = top_h + len(cat_rows) * row_h + 16

    cx, cy, r, sw = 74, 66, 46, 12
    c = 2 * math.pi * r
    extra = (hachure_pattern("ncDone", pal.easy_fill)
             + hachure_pattern("ncPart", pal.accent))

    # Hand-drawn shapes: frame, ring, sheen, bars.
    shp = [
        card_frame(width, height, pal),
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{pal.track}" '
        f'stroke-width="{sw}" />',
        f'<g transform="rotate(-90 {cx} {cy})">'
        + _arc_circle(cx, cy, r, sw, pal.accent, nc_frac, 0.0,
                      inner=anim_draw(nc_frac * c, c, 0.0, 0.9))
        + "</g>",
        f'<g>{anim_spin(cx, cy, 4.0)}<circle cx="{cx}" cy="{cy}" r="{r}" '
        f'fill="none" stroke="{pal.sheen}" stroke-opacity="0.7" stroke-width="{sw}" '
        f'stroke-linecap="round" '
        f'stroke-dasharray="4 {c:.2f}" transform="rotate(-90 {cx} {cy})"/></g>',
    ]
    texts: list[str] = []
    for i, (frac, category, done, tot) in enumerate(cat_rows):
        row_y = top_h + i * row_h
        by = row_y + (row_h - bar_h) / 2
        ty = row_y + row_h / 2 + 4
        complete = done == tot and tot
        pat = "ncDone" if complete else "ncPart"
        stroke = pal.easy_fill if complete else pal.accent
        fill_len = bar_max * frac
        lbl = f"{_xml(category)} ✓" if complete else _xml(category)
        delay = 0.25 + i * 0.03
        shp.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{bar_max}" height="{bar_h}" '
            f'rx="6" ry="6" fill="{pal.track}" />'
        )
        if fill_len > 0:
            shp.append(
                f'<rect x="{bar_x}" y="{by:.0f}" width="{fill_len:.1f}" '
                f'height="{bar_h}" rx="6" ry="6" fill="url(#{pat})" '
                f'stroke="{stroke}" stroke-width="1.3">'
                f'{anim_grow_width(fill_len, delay, 0.6)}</rect>'
            )
        texts.append(
            f'<text x="{label_w - 6}" y="{ty:.0f}" text-anchor="end" '
            f'font-size="12" fill="{pal.muted}">{lbl}</text>'
        )
        texts.append(
            f'<text x="{width - 8}" y="{ty:.0f}" text-anchor="end" '
            f'font-size="12" font-weight="700" fill="{pal.muted}">'
            f'{anim_fade(0.5, 0.6)}{done}/{tot}</text>'
        )
    body = [rough_g("".join(shp))]

    # Center + side text (crisp); percentage pops in.
    body.append(anim_pop(
        cx, cy,
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="22" '
        f'font-weight="700" fill="{pal.accent}">{nc_frac * 100:.0f}%</text>',
        0.3, 0.5,
    ))
    body.append(
        f'<text x="{cx + r + 20}" y="{cy - 6}" font-size="28" font-weight="700" '
        f'fill="{pal.accent}">{anim_fade(0.3, 0.6)}{nc_done} / {nc_total}</text>'
    )
    body.append(
        f'<text x="{cx + r + 20}" y="{cy + 16}" font-size="13" fill="{pal.muted}">'
        f'problems on the roadmap</text>'
    )
    body.extend(texts)
    return finish_svg(svg_open(width, height), "\n".join(body), extra)


def variant_path(base: Path, pal: Palette) -> Path:
    return base.with_name(f"{base.stem}{pal.file_suffix}{base.suffix}")


def emit_chart(base: Path, builder, *args) -> tuple[str, str]:
    """Write one SVG per palette; return (light_rel, dark_rel) repo paths."""
    rels = []
    for pal in PALETTES:
        path = variant_path(base, pal)
        write_if_changed(path, builder(*args, pal))
        rels.append(path.relative_to(REPO_ROOT).as_posix())
    return rels[0], rels[1]


def picture(light_rel: str, dark_rel: str, alt: str, width: str = "") -> str:
    """A theme-aware image. GitHub honours <picture> media queries in Markdown,
    which is the only way an <img>-embedded SVG can react to the page theme."""
    w = f' width="{width}"' if width else ""
    return (
        "<picture>"
        f'<source media="(prefers-color-scheme: dark)" srcset="{dark_rel}">'
        f'<img src="{light_rel}"{w} alt="{alt}">'
        "</picture>"
    )


def render(problems: list[dict], repo: str, branch: str, ranking: dict | None) -> str:
    base = f"https://github.com/{repo}/tree/{branch}"
    dash = "—"
    total = len(problems)
    counts = Counter(p["difficulty"] for p in problems)
    easy, medium, hard = counts["Easy"], counts["Medium"], counts["Hard"]

    topic_counts = Counter()
    for p in problems:
        topic_counts.update(p["topics"])

    solved = [p for p in problems if p["runtime"]]
    avg_speed = (
        sum(p["runtime"]["time_pct"] for p in solved) / len(solved) if solved else 0
    )
    updated = last_updated()

    # NeetCode 150 progress (matched by problem slug).
    neetcode = load_neetcode()
    solved_slugs = {p["slug"] for p in problems}
    nc_total = sum(len(v) for v in neetcode.values())
    nc_done = sum(
        1 for slugs in neetcode.values() for s in slugs if s in solved_slugs
    )
    nc_frac = nc_done / nc_total if nc_total else 0

    # Activity metrics (from per-problem solved dates).
    dated = sorted(
        (p for p in problems if p.get("date")), key=lambda p: (p["date"], p["id"])
    )
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)
    month_start = today.replace(day=1)
    this_week = sum(1 for p in dated if p["date"] >= week_start)
    last_week = sum(1 for p in dated if last_week_start <= p["date"] < week_start)
    this_month = sum(1 for p in dated if p["date"] >= month_start)
    active_days = len({p["date"] for p in dated})

    L: list[str] = []
    a = L.append

    # ---- Header (centered) ----
    a(PROFILE_START)
    a("")
    a('<div align="center">')
    a("")
    a("# Data Structures & Algorithms — Practice Log")
    a("")
    a("*Python solutions to LeetCode problems — my data structures, "
      "algorithms, and interview-prep journal.*")
    a("")
    banner_l, banner_d = emit_chart(
        BANNER_FILE, build_stats_banner_svg,
        total, easy, medium, hard, nc_done, nc_total, ranking,
    )
    a(picture(banner_l, banner_d,
              f"Solved {total} — NeetCode {nc_done}/{nc_total} "
              f"— stats overview", width="100%"))
    a("")
    nav = ["[Overview](#overview)"]
    if dated:
        nav.append("[Activity](#activity)")
    if ranking:
        nav.append("[Competitive](#competitive-standing)")
    if nc_total:
        nav.append("[NeetCode 150](#neetcode-150)")
    nav.append("[Topics](#topics)")
    nav.append("[Solutions](#solutions)")
    a(" &nbsp;&bull;&nbsp; ".join(nav))
    a("")
    a("</div>")
    a("")

    # ---- Overview ----
    # The banner above already carries total / difficulty / NeetCode / contest,
    # so this section adds only what it doesn't, then goes straight to the donut.
    a("---")
    a("")
    a("## Overview")
    a("")
    caption = []
    if solved:
        caption.append(f"Average submission beats **{avg_speed:.0f}%** on runtime.")
    if updated:
        caption.append(f"Last updated **{updated}**.")
    if caption:
        a(" ".join(caption))
        a("")
    donut_l, donut_d = emit_chart(
        DIFFICULTY_FILE, build_difficulty_donut_svg, easy, medium, hard
    )
    a('<div align="center">')
    a("")
    a(picture(donut_l, donut_d,
              f"Difficulty breakdown: {easy} Easy, {medium} Medium, {hard} Hard",
              width="100%"))
    a("")
    a("</div>")
    a("")

    # ---- Activity ----
    if dated:
        a("---")
        a("")
        a("## Activity")
        a("")
        wk_arrow = ""
        if this_week > last_week:
            wk_arrow = f" ⬆ +{this_week - last_week} vs last week"
        elif this_week < last_week:
            wk_arrow = f" ⬇ {this_week - last_week} vs last week"
        a("| This week | This month | Active days |")
        a("| :-------: | :--------: | :---------: |")
        a(f"| **{this_week}**{wk_arrow} | **{this_month}** | **{active_days}** |")
        a("")

        # Full-year contribution heatmap, rendered as a committed SVG image so it
        # stays pixel-aligned (block-character ASCII drifts in GitHub's font).
        heat_l, heat_d = emit_chart(
            HEATMAP_FILE, build_heatmap_svg, dated, today, week_start
        )
        a('<div align="center">')
        a("")
        a(picture(heat_l, heat_d,
                  "Contribution heatmap of the past year", width="100%"))
        a("")
        a("</div>")
        a("")

        # Recent activity feed.
        recent = sorted(dated, key=lambda p: (p["date"], p["id"]), reverse=True)[:5]
        a("**Recently solved**")
        a("")
        a("| Date | # | Problem | Difficulty |")
        a("| :--- | --: | :------ | :--------- |")
        for p in recent:
            dot = DIFFICULTY_DOT.get(p["difficulty"], "")
            a(f"| {p['date'].isoformat()} | {p['id']} "
              f"| [{p['title']}]({base}/{p['folder']}) | {dot} {p['difficulty']} |")
        a("")

    # ---- Competitive Standing ----
    if ranking:
        a("---")
        a("")
        a("## Competitive Standing")
        a("")
        uname = ranking.get("username") or ""
        rating = ranking.get("contest_rating")
        top = ranking.get("contest_top_percentage")
        has_contest = bool(rating and ranking.get("contest_attended"))
        rows: list[tuple[str, str]] = []
        if ranking.get("overall_ranking"):
            rows.append((
                "Global rank",
                f"[#{fmt_int(ranking['overall_ranking'])}]"
                f"(https://leetcode.com/u/{uname}/) worldwide",
            ))
        if has_contest:
            rows.append(("Contest rating", f"{rating:.0f}"))
            rankval = f"#{fmt_int(ranking.get('contest_global_ranking'))}"
            if ranking.get("contest_total_participants"):
                rankval += f" / {fmt_int(ranking['contest_total_participants'])}"
            if top is not None:
                rankval += f" (top {top:.2f}%)"
            rows.append(("Contest rank", rankval))
            rows.append(("Contests attended", str(ranking["contest_attended"])))
            rows.append(("Contest badge", ranking.get("contest_badge") or "none yet"))
        a("| Metric | Value |")
        a("| :----- | :---- |")
        for k, v in rows:
            a(f"| {k} | {v} |")
        a("")
        if has_contest and top is not None:
            tier = next_rating_tier(rating)
            if tier:
                name, cutoff, gap = tier
                a(f"> Next tier: **{name}** (~{cutoff} rating, approx) "
                  f"— {gap} rating to go.")
                a("")
        elif not has_contest:
            a("> No rated contests yet — jump into a weekly contest to start "
              "climbing the global leaderboard.")
            a("")

    # ---- NeetCode 150 ----
    if nc_total:
        a("---")
        a("")
        a("## NeetCode 150")
        a("")
        a(f"Working through the [NeetCode 150](https://neetcode.io/practice) roadmap: "
          f"**{nc_done} / {nc_total}** complete.")
        a("")
        cat_rows = []
        for category, slugs in neetcode.items():
            done = sum(1 for s in slugs if s in solved_slugs)
            frac = done / len(slugs) if slugs else 0
            cat_rows.append((frac, category, done, len(slugs)))
        cat_rows.sort(key=lambda r: (-r[0], r[1]))
        nc_l, nc_d = emit_chart(
            NEETCODE_SVG_FILE, build_neetcode_svg, cat_rows, nc_done, nc_total, nc_frac
        )
        a('<div align="center">')
        a("")
        a(picture(nc_l, nc_d, "NeetCode 150 progress by category", width="100%"))
        a("")
        a("</div>")
        a("")

    # ---- Topics (bar chart) ----
    a("---")
    a("")
    a("## Topics")
    a("")
    topic_items = sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    topics_l, topics_d = emit_chart(TOPICS_FILE, build_topics_bar_svg, topic_items)
    a('<div align="center">')
    a("")
    a(picture(topics_l, topics_d, "Topics solved, by problem count", width="100%"))
    a("")
    extra = len(topic_items) - 16
    if extra > 0:
        a(f"<sub>+{extra} more topics</sub>")
        a("")
    a("</div>")
    a("")

    # ---- Solutions (grouped by NeetCode category, collapsible) ----
    a("---")
    a("")
    a("## Solutions")
    a("")
    a("Runtime / memory percentiles are from my accepted LeetCode submissions, "
      "grouped by NeetCode 150 category.")
    a("")
    cat_map = slug_to_category(neetcode)
    groups: dict[str, list[dict]] = {cat: [] for cat in neetcode}
    other: list[dict] = []
    for p in problems:
        cat = cat_map.get(p["slug"])
        if cat:
            groups[cat].append(p)
        else:
            other.append(p)

    def emit_group(title: str, probs: list[dict], tot: int | None) -> None:
        if not probs:
            return
        count = f"{len(probs)} / {tot}" if tot is not None else str(len(probs))
        a("<details>")
        a(f"<summary><strong>{title}</strong> &nbsp;({count})</summary>")
        a("")
        a("| # | Problem | Difficulty | Runtime | Memory |")
        a("| --: | :------ | :--------- | :------ | :----- |")
        for p in sorted(probs, key=lambda x: x["id"]):
            rt = p["runtime"]
            if rt:
                runtime_str = f"{rt['time_ms']:.0f} ms ({rt['time_pct']:.0f}%)"
                memory_str = f"{rt['space_mb']:.1f} MB ({rt['space_pct']:.0f}%)"
            else:
                runtime_str = memory_str = dash
            dot = DIFFICULTY_DOT.get(p["difficulty"], "")
            a(f"| {p['id']} | [{p['title']}]({base}/{p['folder']}) "
              f"| {dot} {p['difficulty']} | {runtime_str} | {memory_str} |")
        a("")
        a("</details>")
        a("")

    for category, slugs in neetcode.items():
        emit_group(category, groups[category], tot=len(slugs))
    emit_group("Other practice (not in NeetCode 150)", other, tot=None)

    # ---- Footer ----
    a("---")
    a("")
    a('<div align="center">')
    a("")
    a("<sub>Auto-generated from the repository after each commit by "
      f"[`scripts/generate_readme.py`]({base}/scripts/generate_readme.py). "
      "Problems synced via [LeetHub v2](https://github.com/arunbhardwaj/LeetHub-2.0).</sub>")
    a("")
    a("</div>")
    a("")
    a(PROFILE_END)
    return "\n".join(L)


def extract_leethub_block(existing: str) -> str:
    start = existing.find(LEETHUB_START)
    end = existing.find(LEETHUB_END)
    if start != -1 and end != -1 and end > start:
        return existing[start:end + len(LEETHUB_END)]
    return f"{LEETHUB_START}\n# LeetCode Topics\n{LEETHUB_END}"


def assemble(profile: str, leethub_block: str) -> str:
    return (
        f"{profile}\n\n"
        "<details>\n"
        "<summary>Raw LeetHub topic index (auto-generated — do not edit)</summary>\n\n"
        f"{leethub_block}\n\n"
        "</details>\n"
    )


def main() -> int:
    readme_path = REPO_ROOT / "README.md"
    existing = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    leethub_block = extract_leethub_block(existing)

    problems = build_problems()
    repo, branch = detect_repo_slug_and_branch()
    username = leetcode_username()
    ranking = fetch_user_ranking(username) if username else None
    output = assemble(render(problems, repo, branch, ranking), leethub_block)

    if existing == output:
        print("README already up to date.")
        return 0
    readme_path.write_text(output, encoding="utf-8")
    print(f"README regenerated: {len(problems)} problems, branch '{branch}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
