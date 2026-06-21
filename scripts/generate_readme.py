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

PROFILE_START = "<!-- PROFILE:START -->"
PROFILE_END = "<!-- PROFILE:END -->"
LEETHUB_START = "<!---LeetCode Topics Start-->"
LEETHUB_END = "<!---LeetCode Topics End-->"

DIFFICULTY_ORDER = {"Easy": 0, "Medium": 1, "Hard": 2}
DIFFICULTY_COLOR = {"Easy": "2DB55D", "Medium": "FFB800", "Hard": "EF4743"}

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


def render(problems: list[dict], repo: str, branch: str) -> str:
    base = f"https://github.com/{repo}/tree/{branch}"
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

    L: list[str] = []
    a = L.append

    a(PROFILE_START)
    a("")
    a("# Data Structures & Algorithms \u2014 Practice Log")
    a("")
    a("Solutions to LeetCode problems I've worked through in Python while studying "
      "data structures, algorithms, and preparing for technical interviews. "
      "Each folder holds the problem statement and my solution.")
    a("")
    a(f"![Solved](https://img.shields.io/badge/Problems_Solved-{total}-1F6FEB)")
    a(f"![Easy](https://img.shields.io/badge/Easy-{easy}-{DIFFICULTY_COLOR['Easy']})")
    a(f"![Medium](https://img.shields.io/badge/Medium-{medium}-{DIFFICULTY_COLOR['Medium']})")
    a(f"![Hard](https://img.shields.io/badge/Hard-{hard}-{DIFFICULTY_COLOR['Hard']})")
    a("![Language](https://img.shields.io/badge/Language-Python-3776AB?logo=python&logoColor=white)")
    if nc_total:
        a(f"![NeetCode](https://img.shields.io/badge/NeetCode_150-{nc_done}%2F{nc_total}-1F6FEB)")
    a("")
    a("---")
    a("")
    a("## Progress")
    a("")
    a("```text")
    a(f"Total solved : {total}")
    if updated:
        a(f"Last updated : {updated}")
    if solved:
        a(f"Avg runtime  : beats {avg_speed:.0f}% of submissions")
    a("```")
    a("")
    a("**By difficulty**")
    a("")
    a("| Difficulty | Solved | Share |")
    a("| :--------- | :----: | :---- |")
    for diff in ("Easy", "Medium", "Hard"):
        n = counts[diff]
        frac = n / total if total else 0
        a(f"| {diff} | {n} | `{pct_bar(frac)}` {frac * 100:.0f}% |")
    a("")
    if nc_total:
        a("---")
        a("")
        a("## NeetCode 150")
        a("")
        overall = nc_done / nc_total if nc_total else 0
        a(f"Working through the [NeetCode 150](https://neetcode.io/practice) roadmap: "
          f"**{nc_done} / {nc_total}** complete.")
        a("")
        a(f"`{pct_bar(overall, width=30)}` {overall * 100:.0f}%")
        a("")
        a("| Category | Done | Progress |")
        a("| :------- | :--: | :------- |")
        for category, slugs in neetcode.items():
            done = sum(1 for s in slugs if s in solved_slugs)
            frac = done / len(slugs) if slugs else 0
            mark = " \u2713" if done == len(slugs) and slugs else ""
            a(f"| {category}{mark} | {done} / {len(slugs)} | `{pct_bar(frac, width=12)}` |")
    a("")
    a("---")
    a("")
    a("## Topics")
    a("")
    a("| Topic | Solved |")
    a("| :---- | :----: |")
    for topic, n in sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        a(f"| {topic} | {n} |")
    a("")
    a("---")
    a("")
    a("## Solutions")
    a("")
    a("Runtime / memory percentiles are taken from my accepted LeetCode submissions.")
    a("")
    a("| # | Problem | Difficulty | Topics | Runtime | Memory |")
    a("| --: | :------ | :--------- | :----- | :------ | :----- |")
    dash = "\u2014"
    for p in sorted(problems, key=lambda x: x["id"]):
        topics = p["topics"][:3]
        topics_str = ", ".join(topics) + (" \u2026" if len(p["topics"]) > 3 else "")
        if not topics_str:
            topics_str = dash
        rt = p["runtime"]
        if rt:
            runtime_str = f"{rt['time_ms']:.0f} ms ({rt['time_pct']:.0f}%)"
            memory_str = f"{rt['space_mb']:.1f} MB ({rt['space_pct']:.0f}%)"
        else:
            runtime_str = memory_str = dash
        a(
            f"| {p['id']} | [{p['title']}]({base}/{p['folder']}) "
            f"| {p['difficulty']} | {topics_str} | {runtime_str} | {memory_str} |"
        )
    a("")
    a("---")
    a("")
    a("<sub>This file is generated automatically from the repository after each commit "
      f"by [`scripts/generate_readme.py`]({base}/scripts/generate_readme.py). "
      "Problems are synced via [LeetHub v2](https://github.com/arunbhardwaj/LeetHub-2.0).</sub>")
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
    output = assemble(render(problems, repo, branch), leethub_block)

    if existing == output:
        print("README already up to date.")
        return 0
    readme_path.write_text(output, encoding="utf-8")
    print(f"README regenerated: {len(problems)} problems, branch '{branch}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
