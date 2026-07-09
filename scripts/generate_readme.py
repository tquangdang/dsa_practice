#!/usr/bin/env python3
"""Regenerate the README as a clean, professional DSA practice log.

Data sources:
  - Problem folders in the repo root (``NNNN-some-slug``).
  - LeetCode public GraphQL API for difficulty + topic tags (cached on disk).
  - git history for runtime / memory percentiles and the last-updated date.

The script only rewrites the region between the PROFILE markers and re-emits the
LeetHub topic block (between its own markers) verbatim, so LeetHub and this
generator never overwrite each other.
"""
from __future__ import annotations

import base64
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
DIFFICULTY_COLOR = {"Easy": "2DB55D", "Medium": "FFB800", "Hard": "EF4743"}
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


def pct_bar(fraction: float, width: int = 22) -> str:
    filled = max(0, min(width, round(fraction * width)))
    return "\u2588" * filled + "\u2591" * (width - filled)


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "\u2014"


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


# GitHub-style contribution palette (0 = empty, then increasing intensity).
HEATMAP_PALETTE = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
HEATMAP_TEXT = "#768390"
# Neutral gray for empty tracks/rings; used at low opacity so it reads as a
# faint pill on both dark and light backgrounds (an <img> SVG can't detect
# GitHub's theme, so we avoid theme-specific light/dark colors).
TRACK = "#8b949e"
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
_FONT_CACHE: dict[str, str] = {}


def _font_data_uri(path: Path) -> str:
    key = str(path)
    if key not in _FONT_CACHE:
        try:
            raw = path.read_bytes()
            _FONT_CACHE[key] = (
                "data:font/woff2;base64," + base64.b64encode(raw).decode("ascii")
            )
        except OSError:
            _FONT_CACHE[key] = ""
    return _FONT_CACHE[key]


def font_face_defs() -> str:
    """Embed the Kalam handwriting font (regular + bold) as base64 @font-face."""
    if not DOODLE:
        return ""
    reg = _font_data_uri(FONTS_DIR / "kalam-regular.woff2")
    if not reg:
        return ""
    faces = (
        "@font-face{font-family:'Doodle';font-style:normal;font-weight:400;"
        f"src:url({reg}) format('woff2');}}"
    )
    bold = _font_data_uri(FONTS_DIR / "kalam-bold.woff2")
    if bold:
        faces += (
            "@font-face{font-family:'Doodle';font-style:normal;font-weight:700;"
            f"src:url({bold}) format('woff2');}}"
        )
    return f"<style>{faces}</style>"


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
    solid-ish colored pill (rather than thin lines over the page) so they stay
    legible on dark backgrounds."""
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


def svg_defs(extra: str = "") -> str:
    """Bundle the shared font + rough filter (and any per-chart defs) once."""
    inner = font_face_defs() + rough_filter_defs() + extra
    return f"<defs>{inner}</defs>" if inner else ""


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


def build_heatmap_svg(dated: list[dict], today: date, week_start: date,
                      weeks: int = 53) -> str:
    """Render a GitHub-style contribution heatmap as a standalone SVG string."""
    counts_by_day = Counter(p["date"] for p in dated)
    cell, gap = 14, 3
    step = cell + gap
    left_pad, top_pad = 34, 22
    grid_start = week_start - timedelta(weeks=weeks - 1)
    grid_w = weeks * step - gap
    grid_h = 7 * step - gap
    legend_h = 26
    width = left_pad + grid_w + 14
    height = top_pad + grid_h + legend_h

    def level(c: int) -> int:
        return 0 if c <= 0 else min(4, c)

    def cell_fill(lv: int) -> str:
        """Fill attrs for a heatmap level; empty (0) is a faint neutral so it
        never glares white on a dark page."""
        if lv <= 0:
            return f'fill="{TRACK}" fill-opacity="0.16"'
        return f'fill="{HEATMAP_PALETTE[lv]}"'

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="{doodle_font_family()}" '
        f'font-size="11">'
    ]
    parts.append(svg_defs())

    # Hand-drawn shapes (cells, legend swatches, frame) go under the wobble
    # filter; text labels stay crisp for legibility.
    shp = [
        f'<rect x="3" y="3" width="{width - 6}" height="{height - 6}" rx="12" '
        f'fill="none" stroke="#b8bcc4" stroke-width="1.6" stroke-linecap="round"/>'
    ]

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
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                f'rx="3" ry="3" {cell_fill(level(c))}>'
                f'<title>{day.isoformat()}: {c} {noun}</title>{pulse}</rect>'
            )
        if col_cells:
            shp.append(f'<g>{anim_fade(wk * 0.012, 0.45)}')
            shp.extend(col_cells)
            shp.append("</g>")

    # Legend swatches (shapes).
    ly = top_pad + grid_h + 8
    lx = left_pad + 28
    for lv in range(len(HEATMAP_PALETTE)):
        shp.append(
            f'<rect x="{lx}" y="{ly}" width="{cell}" height="{cell}" rx="3" ry="3" '
            f'{cell_fill(lv)}/>'
        )
        lx += step
    parts.append(rough_g("".join(shp)))

    # Month labels along the top (when the column's month changes).
    prev_month = None
    for wk in range(weeks):
        month = (grid_start + timedelta(days=wk * 7)).month
        if month != prev_month:
            x = left_pad + wk * step
            parts.append(
                f'<text x="{x}" y="{top_pad - 8}" fill="{HEATMAP_TEXT}">'
                f'{MONTH_ABBR[month - 1]}</text>'
            )
            prev_month = month

    # Weekday labels (Mon / Wed / Fri, like GitHub).
    for wd, label in {0: "Mon", 2: "Wed", 4: "Fri"}.items():
        y = top_pad + wd * step + cell - 3
        parts.append(
            f'<text x="{left_pad - 6}" y="{y}" text-anchor="end" '
            f'fill="{HEATMAP_TEXT}">{label}</text>'
        )

    # Legend labels (crisp text).
    parts.append(
        f'<text x="{left_pad}" y="{ly + cell - 3}" fill="{HEATMAP_TEXT}">Less</text>'
    )
    parts.append(
        f'<text x="{lx + 2}" y="{ly + cell - 3}" fill="{HEATMAP_TEXT}">More</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def build_stats_banner_svg(total: int, easy: int, medium: int, hard: int,
                           nc_done: int, nc_total: int,
                           ranking: dict | None) -> str:
    """Render a hero stats card (4 tiles) as a standalone SVG string."""
    width, height = 720, 150
    pad = 24
    tw = (width - 2 * pad) / 4
    label_c, div_c = "#768390", "#d0d7de"
    blue, purple = "#1F6FEB", "#8E44AD"
    ec = f"#{DIFFICULTY_COLOR['Easy']}"
    mc = f"#{DIFFICULTY_COLOR['Medium']}"
    hc = f"#{DIFFICULTY_COLOR['Hard']}"

    def cx(i: int) -> float:
        return pad + tw * (i + 0.5)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="{doodle_font_family()}">'
    ]
    extra = (
        '<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#4f8ff5" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#4f8ff5" stop-opacity="0.28"/>'
        '<stop offset="1" stop-color="#4f8ff5" stop-opacity="0"/>'
        '</linearGradient>'
        f'<clipPath id="bclip"><rect width="{width}" height="{height}" rx="10"/>'
        '</clipPath>'
        + hachure_pattern("hachE", ec) + hachure_pattern("hachM", mc)
        + hachure_pattern("hachH", hc)
    )
    parts.append(svg_defs(extra))

    # Frame + dividers are hand-drawn (rough); text stays crisp.
    shp = [
        f'<rect x="4" y="4" width="{width - 8}" height="{height - 8}" rx="14" '
        f'fill="none" stroke="#b8bcc4" stroke-width="1.8" stroke-linecap="round"/>'
    ]
    for i in (1, 2, 3):
        x = pad + tw * i
        shp.append(
            f'<line x1="{x:.0f}" y1="30" x2="{x:.0f}" y2="120" '
            f'stroke="{div_c}" stroke-width="1.4">{anim_fade(0.2, 0.7)}</line>'
        )
    parts.append(rough_g("".join(shp)))

    def label(i: int, s: str) -> None:
        parts.append(
            f'<text x="{cx(i):.0f}" y="48" text-anchor="middle" fill="{label_c}" '
            f'font-size="12" letter-spacing="1.5">{s}</text>'
        )

    def value(i: int, s: str, color: str) -> None:
        parts.append(
            f'<text x="{cx(i):.0f}" y="92" text-anchor="middle" fill="{color}" '
            f'font-size="40" font-weight="700">{s}</text>'
        )

    def sub(i: int, s: str) -> None:
        parts.append(
            f'<text x="{cx(i):.0f}" y="114" text-anchor="middle" fill="{label_c}" '
            f'font-size="13">{s}</text>'
        )

    # Tile 0: total solved.
    parts.append(f'<g>{anim_slideup(0.0)}')
    label(0, "SOLVED")
    value(0, str(total), blue)
    sub(0, "Python")
    parts.append("</g>")

    # Tile 1: difficulty split (stacked bar + coloured counts).
    parts.append(f'<g>{anim_slideup(0.08)}')
    label(1, "BY DIFFICULTY")
    bw = tw - 56
    bx = cx(1) - bw / 2
    by, bh = 66, 14
    tot = max(1, easy + medium + hard)
    we, wm = bw * easy / tot, bw * medium / tot
    wh = bw - we - wm
    parts.append(rough_g(
        f'<rect x="{bx:.1f}" y="{by}" width="{we:.1f}" height="{bh}" '
        f'fill="url(#hachE)" stroke="{ec}" stroke-width="1.3"/>'
        f'<rect x="{bx + we:.1f}" y="{by}" width="{wm:.1f}" height="{bh}" '
        f'fill="url(#hachM)" stroke="{mc}" stroke-width="1.3"/>'
        f'<rect x="{bx + we + wm:.1f}" y="{by}" width="{wh:.1f}" height="{bh}" '
        f'fill="url(#hachH)" stroke="{hc}" stroke-width="1.3"/>'
    ))
    parts.append(
        f'<text x="{cx(1):.0f}" y="106" text-anchor="middle" font-size="14" '
        f'font-weight="600"><tspan fill="{ec}">{easy}</tspan>'
        f'<tspan fill="{label_c}"> / </tspan><tspan fill="{mc}">{medium}</tspan>'
        f'<tspan fill="{label_c}"> / </tspan><tspan fill="{hc}">{hard}</tspan></text>'
    )
    parts.append("</g>")

    # Tile 2: NeetCode 150 progress.
    parts.append(f'<g>{anim_slideup(0.16)}')
    label(2, "NEETCODE 150")
    if nc_total:
        value(2, f"{round(nc_done / nc_total * 100)}%", blue)
        sub(2, f"{nc_done} / {nc_total}")
    else:
        value(2, "\u2014", blue)
    parts.append("</g>")

    # Tile 3: contest rating / global rank.
    parts.append(f'<g>{anim_slideup(0.24)}')
    rating = ranking.get("contest_rating") if ranking else None
    rank = ranking.get("overall_ranking") if ranking else None
    if rating:
        label(3, "CONTEST")
        value(3, f"{rating:.0f}", purple)
        sub(3, f"Rank #{fmt_int(rank)}" if rank else "rated")
    elif rank:
        label(3, "GLOBAL RANK")
        value(3, f"#{fmt_int(rank)}", purple)
        sub(3, "worldwide")
    else:
        label(3, "CONTEST")
        value(3, "\u2014", purple)
        sub(3, "not yet")
    parts.append("</g>")

    # Continuous accent: a faint diagonal glint sweeping across the banner.
    # Skew lives on an outer group so the SMIL translate can drive the sweep.
    parts.append(
        f'<g clip-path="url(#bclip)"><g transform="skewX(-18)">'
        f'<rect x="-100" y="-20" width="80" height="{height + 40}" '
        f'fill="url(#shine)">{anim_sweep_x(0, width + 220, 6.5)}</rect>'
        f'</g></g>'
    )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _xml(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _blue_scale(f: float) -> str:
    """Light-to-dark blue by fraction f in [0, 1] (darker = larger)."""
    lo = (158, 197, 251)  # #9EC5FB
    hi = (13, 71, 161)     # #0D47A1
    r, g, b = (round(lo[i] + (hi[i] - lo[i]) * f) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


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


def build_topics_bar_svg(items: list[tuple[str, int]], top_n: int = 16) -> str:
    """Horizontal bar chart of topic counts (sorted desc), as an SVG string."""
    rows = items[:top_n]
    width = 900
    label_w = 210
    bar_x = label_w + 10
    bar_max = width - bar_x - 56
    row_h, bar_h, top_pad = 24, 14, 16
    height = top_pad + len(rows) * row_h + 16
    max_count = max((n for _, n in rows), default=1)
    label_c = "#768390"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="{doodle_font_family()}" '
        f'font-size="13">'
    ]
    shp = [
        f'<rect x="4" y="4" width="{width - 8}" height="{height - 8}" rx="14" '
        f'fill="none" stroke="#b8bcc4" stroke-width="1.8" stroke-linecap="round"/>'
    ]
    texts: list[str] = []
    hach_defs: list[str] = []
    top_geom = None
    for i, (topic, n) in enumerate(rows):
        row_y = top_pad + i * row_h
        by = row_y + (row_h - bar_h) / 2
        ty = row_y + row_h / 2 + 4
        frac = n / max_count if max_count else 0
        fill_len = bar_max * frac
        col = _blue_scale(frac)
        pid = f"hachT{i}"
        hach_defs.append(hachure_pattern(pid, col))
        if i == 0:
            top_geom = (by, fill_len)
        shp.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{bar_max}" height="{bar_h}" '
            f'rx="6" ry="6" fill="{TRACK}" fill-opacity="0.18" />'
        )
        shp.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{fill_len:.1f}" '
            f'height="{bar_h}" rx="6" ry="6" fill="url(#{pid})" '
            f'stroke="{col}" stroke-width="1.3">'
            f'{anim_grow_width(fill_len, i * 0.04, 0.6)}</rect>'
        )
        texts.append(
            f'<text x="{label_w - 6}" y="{ty:.0f}" text-anchor="end" '
            f'fill="{label_c}">{_xml(topic)}</text>'
        )
        texts.append(
            f'<text x="{bar_x + fill_len + 8:.0f}" y="{ty:.0f}" '
            f'fill="{label_c}" font-weight="700">{anim_fade(0.4, 0.6)}{n}</text>'
        )

    # Continuous accent: a soft glint sweeping the longest (top) bar.
    glint = ""
    tshine_def = ""
    if top_geom:
        top_by, top_len = top_geom
        tshine_def = (
            '<linearGradient id="tshine" x1="0" y1="0" x2="1" y2="0">'
            '<stop offset="0" stop-color="#ffffff" stop-opacity="0"/>'
            '<stop offset="0.5" stop-color="#ffffff" stop-opacity="0.55"/>'
            '<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
            '</linearGradient>'
            f'<clipPath id="tbar"><rect x="{bar_x}" y="{top_by:.0f}" '
            f'width="{top_len:.1f}" height="{bar_h}" rx="6" ry="6"/></clipPath>'
        )
        glint = (
            f'<g clip-path="url(#tbar)"><rect x="{bar_x - 44}" '
            f'y="{top_by:.0f}" width="44" height="{bar_h}" fill="url(#tshine)">'
            f'{anim_sweep_x(0, top_len + 44, 3.2)}</rect></g>'
        )
    parts.append(svg_defs("".join(hach_defs) + tshine_def))
    parts.append(rough_g("".join(shp)))
    parts.extend(texts)
    if glint:
        parts.append(glint)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def build_difficulty_donut_svg(easy: int, medium: int, hard: int) -> str:
    """Donut chart of the difficulty split with a legend, as an SVG string."""
    width, height = 480, 200
    cx, cy, r, sw = 108, 100, 78, 28
    total = easy + medium + hard
    label_c = "#768390"
    segs = [
        ("Easy", easy, f"#{DIFFICULTY_COLOR['Easy']}"),
        ("Medium", medium, f"#{DIFFICULTY_COLOR['Medium']}"),
        ("Hard", hard, f"#{DIFFICULTY_COLOR['Hard']}"),
    ]
    c = 2 * math.pi * r
    seg_pat = {"Easy": "hachE", "Medium": "hachM", "Hard": "hachH"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="{doodle_font_family()}">'
    ]
    parts.append(svg_defs(
        hachure_pattern("hachE", f"#{DIFFICULTY_COLOR['Easy']}")
        + hachure_pattern("hachM", f"#{DIFFICULTY_COLOR['Medium']}")
        + hachure_pattern("hachH", f"#{DIFFICULTY_COLOR['Hard']}", gap=5)
    ))

    # Hand-drawn shapes: frame, track ring, arcs, legend chips.
    shp = [
        f'<rect x="4" y="4" width="{width - 8}" height="{height - 8}" rx="14" '
        f'fill="none" stroke="#b8bcc4" stroke-width="1.8" stroke-linecap="round"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{TRACK}" '
        f'stroke-opacity="0.22" stroke-width="{sw}" />',
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
    ly = 66
    for name, val, color in segs:
        shp.append(
            f'<rect x="250" y="{ly - 12}" width="16" height="16" rx="3" '
            f'fill="url(#{seg_pat[name]})" stroke="{color}" stroke-width="1.2" />'
        )
        ly += 34
    parts.append(rough_g("".join(shp)))

    # Center count pops in; legend labels stay crisp.
    parts.append(anim_pop(
        cx, cy,
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="38" '
        f'font-weight="700" fill="#1F6FEB">{total}</text>'
        f'<text x="{cx}" y="{cy + 24}" text-anchor="middle" font-size="13" '
        f'fill="{label_c}">solved</text>',
        0.5, 0.5,
    ))
    ly = 66
    for i, (name, val, color) in enumerate(segs):
        pct = (val / total * 100) if total else 0
        parts.append(
            f'<text x="274" y="{ly}" font-size="15" fill="{label_c}">'
            f'{anim_fade(0.5 + i * 0.12, 0.5)}{name} &#8212; {val} ({pct:.0f}%)</text>'
        )
        ly += 34
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def build_neetcode_svg(cat_rows: list[tuple], nc_done: int, nc_total: int,
                       nc_frac: float) -> str:
    """Overall progress ring + per-category bars, as an SVG string.

    ``cat_rows`` is a list of ``(frac, category, done, total)`` sorted desc.
    """
    width = 900
    label_w = 210
    bar_x = label_w + 10
    bar_max = width - bar_x - 66
    row_h, bar_h = 24, 14
    top_h = 132
    height = top_h + len(cat_rows) * row_h + 16
    label_c, done_c, part_c = "#768390", "#2DB55D", "#1F6FEB"

    cx, cy, r, sw = 74, 66, 46, 12
    c = 2 * math.pi * r
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="{doodle_font_family()}">'
    ]
    parts.append(svg_defs(
        hachure_pattern("ncDone", done_c) + hachure_pattern("ncPart", part_c)
    ))

    # Hand-drawn shapes: frame, ring, glint, bars.
    shp = [
        f'<rect x="4" y="4" width="{width - 8}" height="{height - 8}" rx="14" '
        f'fill="none" stroke="#b8bcc4" stroke-width="1.8" stroke-linecap="round"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{TRACK}" '
        f'stroke-opacity="0.22" stroke-width="{sw}" />',
        f'<g transform="rotate(-90 {cx} {cy})">'
        + _arc_circle(cx, cy, r, sw, part_c, nc_frac, 0.0,
                      inner=anim_draw(nc_frac * c, c, 0.0, 0.9))
        + "</g>",
        f'<g>{anim_spin(cx, cy, 4.0)}<circle cx="{cx}" cy="{cy}" r="{r}" '
        f'fill="none" stroke="#cfe3ff" stroke-opacity="0.7" stroke-width="{sw}" '
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
        stroke = done_c if complete else part_c
        fill_len = bar_max * frac
        label = f"{_xml(category)} \u2713" if complete else _xml(category)
        delay = 0.25 + i * 0.03
        shp.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{bar_max}" height="{bar_h}" '
            f'rx="6" ry="6" fill="{TRACK}" fill-opacity="0.18" />'
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
            f'font-size="12" fill="{label_c}">{label}</text>'
        )
        texts.append(
            f'<text x="{width - 8}" y="{ty:.0f}" text-anchor="end" '
            f'font-size="12" font-weight="700" fill="{label_c}">'
            f'{anim_fade(0.5, 0.6)}{done}/{tot}</text>'
        )
    parts.append(rough_g("".join(shp)))

    # Center + side text (crisp); percentage pops in.
    parts.append(anim_pop(
        cx, cy,
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="22" '
        f'font-weight="700" fill="{part_c}">{nc_frac * 100:.0f}%</text>',
        0.3, 0.5,
    ))
    parts.append(
        f'<text x="{cx + r + 20}" y="{cy - 6}" font-size="28" font-weight="700" '
        f'fill="{part_c}">{anim_fade(0.3, 0.6)}{nc_done} / {nc_total}</text>'
    )
    parts.append(
        f'<text x="{cx + r + 20}" y="{cy + 16}" font-size="13" fill="{label_c}">'
        f'problems on the roadmap</text>'
    )
    parts.extend(texts)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render(problems: list[dict], repo: str, branch: str, ranking: dict | None) -> str:
    base = f"https://github.com/{repo}/tree/{branch}"
    dash = "\u2014"
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
    a("# Data Structures & Algorithms \u2014 Practice Log")
    a("")
    a("*Python solutions to LeetCode problems \u2014 my data structures, "
      "algorithms, and interview-prep journal.*")
    a("")
    write_if_changed(
        BANNER_FILE,
        build_stats_banner_svg(total, easy, medium, hard, nc_done, nc_total, ranking),
    )
    banner_rel = BANNER_FILE.relative_to(REPO_ROOT).as_posix()
    a(f'<img src="{banner_rel}" width="100%" alt="Solved {total} \u2014 NeetCode '
      f'{nc_done}/{nc_total} \u2014 stats overview" />')
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
    a("---")
    a("")
    a("## Overview")
    a("")
    a("| Metric | Value |")
    a("| :----- | :---- |")
    a(f"| Total solved | **{total}** |")
    if solved:
        a(f"| Avg runtime | beats {avg_speed:.0f}% of submissions |")
    if nc_total:
        a(f"| NeetCode 150 | {nc_done} / {nc_total} ({nc_frac * 100:.0f}%) |")
    if updated:
        a(f"| Last updated | {updated} |")
    a("")
    a("**By difficulty**")
    a("")
    write_if_changed(DIFFICULTY_FILE, build_difficulty_donut_svg(easy, medium, hard))
    difficulty_rel = DIFFICULTY_FILE.relative_to(REPO_ROOT).as_posix()
    a('<div align="center">')
    a("")
    a(f'<img src="{difficulty_rel}" alt="Difficulty breakdown: '
      f'{easy} Easy, {medium} Medium, {hard} Hard" />')
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
            wk_arrow = f" \u2b06 +{this_week - last_week} vs last week"
        elif this_week < last_week:
            wk_arrow = f" \u2b07 {this_week - last_week} vs last week"
        a("| This week | This month | Active days |")
        a("| :-------: | :--------: | :---------: |")
        a(f"| **{this_week}**{wk_arrow} | **{this_month}** | **{active_days}** |")
        a("")

        # Full-year contribution heatmap, rendered as a committed SVG image so it
        # stays pixel-aligned (block-character ASCII drifts in GitHub's font).
        write_if_changed(HEATMAP_FILE, build_heatmap_svg(dated, today, week_start))
        heatmap_rel = HEATMAP_FILE.relative_to(REPO_ROOT).as_posix()
        a('<div align="center">')
        a("")
        a(f'<img src="{heatmap_rel}" width="100%" '
          f'alt="Contribution heatmap of the past year" />')
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
            ahead = max(0.0, 100.0 - top)
            a(f"`{pct_bar(ahead / 100, width=30)}` ahead of {ahead:.1f}% of contestants")
            a("")
            tier = next_rating_tier(rating)
            if tier:
                name, cutoff, gap = tier
                a(f"> Next tier: **{name}** (~{cutoff} rating, approx) "
                  f"\u2014 {gap} rating to go.")
                a("")
        elif not has_contest:
            a("> No rated contests yet \u2014 jump into a weekly contest to start "
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
        write_if_changed(
            NEETCODE_SVG_FILE, build_neetcode_svg(cat_rows, nc_done, nc_total, nc_frac)
        )
        neetcode_rel = NEETCODE_SVG_FILE.relative_to(REPO_ROOT).as_posix()
        a('<div align="center">')
        a("")
        a(f'<img src="{neetcode_rel}" alt="NeetCode 150 progress by category" />')
        a("")
        a("</div>")
        a("")

    # ---- Topics (bar chart) ----
    a("---")
    a("")
    a("## Topics")
    a("")
    topic_items = sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    write_if_changed(TOPICS_FILE, build_topics_bar_svg(topic_items))
    topics_rel = TOPICS_FILE.relative_to(REPO_ROOT).as_posix()
    a('<div align="center">')
    a("")
    a(f'<img src="{topics_rel}" alt="Topics solved, by problem count" />')
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
        "<summary>Raw LeetHub topic index (auto-generated \u2014 do not edit)</summary>\n\n"
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
