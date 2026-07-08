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
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


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

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="9">'
    ]

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

    # Day cells.
    for wd in range(7):
        for wk in range(weeks):
            day = grid_start + timedelta(days=wk * 7 + wd)
            if day > today:
                continue
            c = counts_by_day.get(day, 0)
            fill = HEATMAP_PALETTE[level(c)]
            x = left_pad + wk * step
            y = top_pad + wd * step
            noun = "solve" if c == 1 else "solves"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" ry="3" '
                f'fill="{fill}"><title>{day.isoformat()}: {c} {noun}</title></rect>'
            )

    # Legend.
    ly = top_pad + grid_h + 8
    lx = left_pad
    parts.append(
        f'<text x="{lx}" y="{ly + cell - 3}" fill="{HEATMAP_TEXT}">Less</text>'
    )
    lx += 28
    for color in HEATMAP_PALETTE:
        parts.append(
            f'<rect x="{lx}" y="{ly}" width="{cell}" height="{cell}" rx="3" ry="3" '
            f'fill="{color}"/>'
        )
        lx += step
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
        f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
    ]
    for i in (1, 2, 3):
        x = pad + tw * i
        parts.append(
            f'<line x1="{x:.0f}" y1="30" x2="{x:.0f}" y2="120" '
            f'stroke="{div_c}" stroke-width="1"/>'
        )

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
    label(0, "SOLVED")
    value(0, str(total), blue)
    sub(0, "Python")

    # Tile 1: difficulty split (stacked bar + coloured counts).
    label(1, "BY DIFFICULTY")
    bw = tw - 56
    bx = cx(1) - bw / 2
    by, bh = 66, 14
    tot = max(1, easy + medium + hard)
    we, wm = bw * easy / tot, bw * medium / tot
    wh = bw - we - wm
    parts.append(f'<rect x="{bx:.1f}" y="{by}" width="{we:.1f}" height="{bh}" fill="{ec}"/>')
    parts.append(f'<rect x="{bx + we:.1f}" y="{by}" width="{wm:.1f}" height="{bh}" fill="{mc}"/>')
    parts.append(f'<rect x="{bx + we + wm:.1f}" y="{by}" width="{wh:.1f}" height="{bh}" fill="{hc}"/>')
    parts.append(
        f'<text x="{cx(1):.0f}" y="106" text-anchor="middle" font-size="14" '
        f'font-weight="600"><tspan fill="{ec}">{easy}</tspan>'
        f'<tspan fill="{label_c}"> / </tspan><tspan fill="{mc}">{medium}</tspan>'
        f'<tspan fill="{label_c}"> / </tspan><tspan fill="{hc}">{hard}</tspan></text>'
    )

    # Tile 2: NeetCode 150 progress.
    label(2, "NEETCODE 150")
    if nc_total:
        value(2, f"{round(nc_done / nc_total * 100)}%", blue)
        sub(2, f"{nc_done} / {nc_total}")
    else:
        value(2, "\u2014", blue)

    # Tile 3: contest rating / global rank.
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
                frac: float, offset: float) -> str:
    """A donut/ring segment via stroke-dasharray (group is rotated -90)."""
    c = 2 * math.pi * r
    dash = max(0.0, frac) * c
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
        f'stroke-width="{sw}" stroke-dasharray="{dash:.2f} {c:.2f}" '
        f'stroke-dashoffset="{-offset * c:.2f}" />'
    )


def build_topics_bar_svg(items: list[tuple[str, int]], top_n: int = 16) -> str:
    """Horizontal bar chart of topic counts (sorted desc), as an SVG string."""
    rows = items[:top_n]
    width = 880
    label_w = 180
    bar_x = label_w + 8
    bar_max = width - bar_x - 48
    row_h, bar_h, top_pad = 22, 12, 12
    height = top_pad + len(rows) * row_h + 12
    max_count = max((n for _, n in rows), default=1)
    label_c = "#768390"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="11">'
    ]
    for i, (topic, n) in enumerate(rows):
        row_y = top_pad + i * row_h
        by = row_y + (row_h - bar_h) / 2
        ty = row_y + row_h / 2 + 4
        frac = n / max_count if max_count else 0
        fill_len = bar_max * frac
        parts.append(
            f'<text x="{label_w - 6}" y="{ty:.0f}" text-anchor="end" '
            f'fill="{label_c}">{_xml(topic)}</text>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{bar_max}" height="{bar_h}" '
            f'rx="6" ry="6" fill="#ebedf0" />'
        )
        parts.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{fill_len:.1f}" height="{bar_h}" '
            f'rx="6" ry="6" fill="{_blue_scale(frac)}" />'
        )
        parts.append(
            f'<text x="{bar_x + fill_len + 6:.0f}" y="{ty:.0f}" '
            f'fill="{label_c}" font-weight="600">{n}</text>'
        )
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
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
    ]
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#ebedf0" '
        f'stroke-width="{sw}" />'
    )
    parts.append(f'<g transform="rotate(-90 {cx} {cy})">')
    cum = 0.0
    for _, val, color in segs:
        if val <= 0 or total <= 0:
            continue
        frac = val / total
        parts.append(_arc_circle(cx, cy, r, sw, color, frac, cum))
        cum += frac
    parts.append("</g>")
    parts.append(
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="38" '
        f'font-weight="700" fill="#1F6FEB">{total}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 24}" text-anchor="middle" font-size="12" '
        f'fill="{label_c}">solved</text>'
    )
    lx, ly = 250, 66
    for name, val, color in segs:
        pct = (val / total * 100) if total else 0
        parts.append(
            f'<rect x="{lx}" y="{ly - 12}" width="15" height="15" rx="3" '
            f'fill="{color}" />'
        )
        parts.append(
            f'<text x="{lx + 24}" y="{ly}" font-size="14" fill="{label_c}">'
            f'{name} &#8212; {val} ({pct:.0f}%)</text>'
        )
        ly += 34
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def build_neetcode_svg(cat_rows: list[tuple], nc_done: int, nc_total: int,
                       nc_frac: float) -> str:
    """Overall progress ring + per-category bars, as an SVG string.

    ``cat_rows`` is a list of ``(frac, category, done, total)`` sorted desc.
    """
    width = 880
    label_w = 180
    bar_x = label_w + 8
    bar_max = width - bar_x - 62
    row_h, bar_h = 22, 12
    top_h = 132
    height = top_h + len(cat_rows) * row_h + 12
    label_c, done_c, part_c = "#768390", "#2DB55D", "#1F6FEB"

    cx, cy, r, sw = 74, 62, 46, 12
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
    ]
    # Overall progress ring.
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#ebedf0" '
        f'stroke-width="{sw}" />'
    )
    parts.append(f'<g transform="rotate(-90 {cx} {cy})">')
    parts.append(_arc_circle(cx, cy, r, sw, part_c, nc_frac, 0.0))
    parts.append("</g>")
    parts.append(
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="20" '
        f'font-weight="700" fill="{part_c}">{nc_frac * 100:.0f}%</text>'
    )
    parts.append(
        f'<text x="{cx + r + 20}" y="{cy - 6}" font-size="26" font-weight="700" '
        f'fill="{part_c}">{nc_done} / {nc_total}</text>'
    )
    parts.append(
        f'<text x="{cx + r + 20}" y="{cy + 16}" font-size="12" fill="{label_c}">'
        f'problems on the roadmap</text>'
    )

    # Per-category bars.
    for i, (frac, category, done, tot) in enumerate(cat_rows):
        row_y = top_h + i * row_h
        by = row_y + (row_h - bar_h) / 2
        ty = row_y + row_h / 2 + 4
        complete = done == tot and tot
        fill = done_c if complete else part_c
        fill_len = bar_max * frac
        label = f"{_xml(category)} \u2713" if complete else _xml(category)
        parts.append(
            f'<text x="{label_w - 6}" y="{ty:.0f}" text-anchor="end" '
            f'font-size="11" fill="{label_c}">{label}</text>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="{by:.0f}" width="{bar_max}" height="{bar_h}" '
            f'rx="6" ry="6" fill="#ebedf0" />'
        )
        if fill_len > 0:
            parts.append(
                f'<rect x="{bar_x}" y="{by:.0f}" width="{fill_len:.1f}" '
                f'height="{bar_h}" rx="6" ry="6" fill="{fill}" />'
            )
        parts.append(
            f'<text x="{width - 6}" y="{ty:.0f}" text-anchor="end" font-size="11" '
            f'font-weight="600" fill="{label_c}">{done}/{tot}</text>'
        )
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
