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
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = Path(__file__).resolve().parent / "leetcode_cache.json"
NEETCODE_FILE = Path(__file__).resolve().parent / "neetcode150.json"
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
USER_CACHE_FILE = Path(__file__).resolve().parent / "leetcode_user_cache.json"

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
    nav = ["[Overview](#overview)"]
    if ranking:
        nav.append("[Competitive](#competitive-standing)")
    if nc_total:
        nav.append("[NeetCode 150](#neetcode-150)")
    nav.append("[Topics](#topics)")
    nav.append("[Solutions](#solutions)")
    a(" &nbsp;&bull;&nbsp; ".join(nav))
    a("")
    a(badge("Solved", str(total), "1F6FEB", "for-the-badge"))
    a(badge("Easy", str(easy), DIFFICULTY_COLOR["Easy"], "for-the-badge"))
    a(badge("Medium", str(medium), DIFFICULTY_COLOR["Medium"], "for-the-badge"))
    a(badge("Hard", str(hard), DIFFICULTY_COLOR["Hard"], "for-the-badge"))
    a("")
    a(badge("Language", "Python", "3776AB", "flat-square", logo="python"))
    if nc_total:
        a(badge("NeetCode 150", f"{nc_done}/{nc_total}", "1F6FEB", "flat-square",
                logo="leetcode"))
    if ranking:
        if ranking.get("overall_ranking"):
            a(badge("Global Rank", f"#{fmt_int(ranking['overall_ranking'])}",
                    "F89F1B", "flat-square", logo="leetcode"))
        if ranking.get("contest_rating"):
            a(badge("Contest Rating", str(round(ranking["contest_rating"])),
                    "8E44AD", "flat-square", logo="leetcode"))
        if ranking.get("contest_top_percentage") is not None:
            a(badge("Contest Top", f"{ranking['contest_top_percentage']:.1f}%",
                    "8E44AD", "flat-square"))
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
    a("| Difficulty | Solved | Share |")
    a("| :--------- | :----: | :---- |")
    for diff in ("Easy", "Medium", "Hard"):
        n = counts[diff]
        frac = n / total if total else 0
        a(f"| {diff} | {n} | `{pct_bar(frac, width=24)}` {frac * 100:.0f}% |")
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
        a(f"`{pct_bar(nc_frac, width=30)}` {nc_frac * 100:.0f}%")
        a("")
        a("| Category | Done | Progress |")
        a("| :------- | :--: | :------- |")
        cat_rows = []
        for category, slugs in neetcode.items():
            done = sum(1 for s in slugs if s in solved_slugs)
            frac = done / len(slugs) if slugs else 0
            cat_rows.append((frac, category, done, len(slugs)))
        cat_rows.sort(key=lambda r: (-r[0], r[1]))
        for frac, category, done, tot in cat_rows:
            mark = " \u2713" if done == tot and tot else ""
            a(f"| {category}{mark} | {done} / {tot} | `{pct_bar(frac, width=12)}` |")
        a("")

    # ---- Topics (chips) ----
    a("---")
    a("")
    a("## Topics")
    a("")
    a('<div align="center">')
    a("")
    for topic, n in sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        a(badge(topic, str(n), "555", "flat-square"))
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
