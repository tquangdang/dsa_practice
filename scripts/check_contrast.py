#!/usr/bin/env python3
"""Verify the generated chart SVGs are legible on the theme they target.

Two independent checks, because each catches what the other can't:

  A. Every colour role in a :class:`Palette` clears the WCAG contrast ratio its
     job demands, measured against that palette's page background.
  B. Every hex literal that actually appears in a generated SVG belongs to that
     variant's palette -- so a hardcoded colour slipped into a chart builder
     fails the build instead of quietly shipping.

Run after ``generate_readme.py``. Exits non-zero on any violation.
"""
from __future__ import annotations

import re
import sys

from generate_readme import (
    ASSETS_DIR, DARK, LIGHT, PALETTES, Palette, variant_path,
    BANNER_FILE, DIFFICULTY_FILE, HEATMAP_FILE, NEETCODE_SVG_FILE, TOPICS_FILE,
)

# WCAG 1.4.3 (text) and 1.4.11 (non-text contrast).
TEXT = 4.5      # labels, legends, counts at normal size
LARGE = 3.0     # >=24px values -- the banner tiles and ring percentages
GRAPHIC = 3.0   # bars, rings, arcs: shape must be distinguishable from page

# role -> (minimum ratio vs bg, why)
ROLES: dict[str, tuple[float, str]] = {
    "muted": (TEXT, "axis labels, legends, captions"),
    "easy": (TEXT, "difficulty counts in the banner"),
    "medium": (TEXT, "difficulty counts in the banner"),
    "hard": (TEXT, "difficulty counts in the banner"),
    "easy_fill": (GRAPHIC, "donut arc, stacked bar, swatch"),
    "medium_fill": (GRAPHIC, "donut arc, stacked bar, swatch"),
    "hard_fill": (GRAPHIC, "donut arc, stacked bar, swatch"),
    "accent": (LARGE, "headline numbers (>=22px) and progress arcs"),
    "purple": (LARGE, "contest tile value (40px)"),
    "ramp_lo": (GRAPHIC, "smallest topic bar"),
    "ramp_hi": (GRAPHIC, "largest topic bar"),
}

# Decorative by design: a sketched border or an empty bar track carries no
# information, so WCAG imposes no minimum. Listed here so the omission is a
# decision rather than an oversight.
DECORATIVE = ("frame", "divider", "track", "sheen", "glint")

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    chans = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def check_roles(pal: Palette, failures: list[str]) -> None:
    for role, (minimum, why) in ROLES.items():
        color = getattr(pal, role)
        ratio = contrast(color, pal.bg)
        status = "ok " if ratio >= minimum else "FAIL"
        print(f"  {status} {role:9} {color} {ratio:5.2f}:1 "
              f"(needs {minimum}) — {why}")
        if ratio < minimum:
            failures.append(
                f"{pal.name}: {role} {color} is {ratio:.2f}:1 on {pal.bg}, "
                f"needs {minimum}:1 ({why})"
            )

    # The topic ramp is interpolated, so spot-check the interior too. Both
    # endpoints passing implies the middle does (luminance is monotonic along
    # an RGB lerp), but an accidental hue flip would show up here.
    for f in (0.25, 0.5, 0.75):
        color = pal.ramp(f)
        ratio = contrast(color, pal.bg)
        if ratio < GRAPHIC:
            failures.append(
                f"{pal.name}: topic ramp at f={f} is {color} "
                f"({ratio:.2f}:1), needs {GRAPHIC}:1"
            )

    # Heatmap levels are a sequential scale read against level 0, not the page.
    # These are GitHub's own contribution colours; the requirement is that each
    # step is distinguishable from the one below it.
    for i in range(1, 5):
        step = contrast(pal.heat[i], pal.heat[i - 1])
        if step < 1.15:
            failures.append(
                f"{pal.name}: heat level {i} ({pal.heat[i]}) is only "
                f"{step:.2f}:1 against level {i - 1}"
            )
    top = contrast(pal.heat[4], pal.bg)
    print(f"  {'ok ' if top >= GRAPHIC else 'FAIL'} heat[4]   {pal.heat[4]} "
          f"{top:5.2f}:1 (needs {GRAPHIC}) — busiest day vs page")
    if top < GRAPHIC:
        failures.append(
            f"{pal.name}: heat[4] {pal.heat[4]} is {top:.2f}:1 on {pal.bg}"
        )


def check_emitted(pal: Palette, failures: list[str]) -> None:
    allowed = pal.hexes()
    # Topic bars are interpolated, so they are legitimately not palette members.
    # Enumerating the ramp densely gives the exact set of colours it can reach.
    ramp = {pal.ramp(i / 10000) for i in range(10001)}
    for base in (BANNER_FILE, DIFFICULTY_FILE, HEATMAP_FILE, NEETCODE_SVG_FILE,
                 TOPICS_FILE):
        path = variant_path(base, pal)
        if not path.exists():
            failures.append(f"{pal.name}: {path.name} not generated")
            continue
        found = {m.lower() for m in HEX_RE.findall(path.read_text(encoding="utf-8"))}
        rel = path.relative_to(ASSETS_DIR.parent).as_posix()
        strays, ramped = [], 0
        for color in sorted(found):
            if color in allowed:
                continue
            if color in ramp:
                # Each interpolated bar is held to the graphic threshold in its
                # own right, not merely inherited from the two endpoints.
                ratio = contrast(color, pal.bg)
                ramped += 1
                if ratio < GRAPHIC:
                    failures.append(
                        f"{pal.name}: {rel} topic bar {color} is "
                        f"{ratio:.2f}:1 on {pal.bg}, needs {GRAPHIC}:1"
                    )
                continue
            strays.append(color)
        note = f" (+{ramped} on ramp)" if ramped else ""
        print(f"  {'ok ' if not strays else 'FAIL'} {rel:38} "
              f"{len(found) - ramped:2} palette{note}")
        for s in strays:
            failures.append(
                f"{pal.name}: {rel} uses {s}, which is neither in the "
                f"{pal.name} palette nor on its ramp (hardcoded colour?)"
            )


def main() -> int:
    failures: list[str] = []
    for pal in PALETTES:
        print(f"\n{pal.name} theme — roles vs {pal.bg}")
        check_roles(pal, failures)
        print(f"\n{pal.name} theme — emitted SVGs")
        check_emitted(pal, failures)

    print()
    if failures:
        print(f"{len(failures)} contrast violation(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All palette roles and emitted SVGs pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
