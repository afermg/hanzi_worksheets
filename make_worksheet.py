#!/usr/bin/env python3
"""Generate a printable Hanzi practice PDF from an HSK list.

Wraps the patched fork of `lucivpav/cwg` in `cwg/` to produce:
  - one PDF, US Letter, with cross-grid practice squares
  - Pleco-style tone-colored pinyin (1=red, 2=green, 3=blue, 4=purple)
  - per-character stroke progression (1..N strokes built up)
  - multi-character words kept contiguous with a combined definition

Two input formats:
  - **TSV** (`*.tsv`): 4 columns — traditional, simplified, pinyin, definition.
    Only the simplified column is read.
  - **Plain text** (`*.txt`): one entry per line. Multi-char entries are
    treated as words. A line may also contain inline `(...)` groups to mix
    words and individual characters: `(我们)去年` → "我们" + "去" + "年".

Pinyin and definitions on the worksheet come from CEDICT via cwg.

Usage (defaults pick up HSK 1 3.0-only):
    python make_worksheet.py
    python make_worksheet.py --input 'hsk3/HSK 1.tsv' \
                             --title 'HSK 1' \
                             --output worksheets/hsk1.pdf

Run inside `nix develop` so cairo, the CJK font and Python deps are on path.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"
MAKEMEAHANZI = DATA / "makemeahanzi"
CEDICT = DATA / "cedict"
FONT_NAME = "SourceHanSansSC-Normal"
FONT_PATH = DATA / "fonts" / f"{FONT_NAME}.ttf"
CWG_SRC = REPO / "cwg" / "backend" / "src"
GEN_PY = CWG_SRC / "gen.py"


def read_entries(path: Path) -> list[str]:
    """Return the per-character/per-word entries from the input file.

    Two formats accepted:

    1. **TSV** (4 cols: traditional, simplified, pinyin, definition) — used by
       the HSK lists in `hsk3/`. Only the simplified column is consumed.

    2. **Plain text** (one entry per line). Each line is a character or a
       multi-character word. Parenthesised groups within a line are split
       into separate words; loose characters between groups are emitted
       one per entry. So a line like `(我们)去年` yields entries
       `["我们", "去", "年"]`.

    The format is chosen by file extension: `.txt` → plain, anything else
    → TSV. Empty lines and rows missing a simplified value are skipped.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".txt":
        return _read_plain_entries(text)
    entries = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) < 2:
            continue
        simp = cells[1].strip()
        if simp:
            entries.append(simp)
    return entries


def _read_plain_entries(text: str) -> list[str]:
    """Parse the plain-text input format. Each non-empty line is processed:
    `(...)` segments become one entry each (the inside of the parens);
    any character outside parens becomes its own entry. Whitespace is
    ignored. Both ASCII and full-width parentheses are recognised."""
    entries: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "(" not in stripped and ")" not in stripped \
                and "（" not in stripped and "）" not in stripped:
            entries.append(stripped)
            continue
        buf = ""
        in_paren = False
        for ch in stripped:
            if ch in "(（":
                in_paren = True
                buf = ""
            elif ch in ")）":
                if buf:
                    entries.append(buf)
                buf = ""
                in_paren = False
            elif ch.isspace():
                continue
            elif in_paren:
                buf += ch
            else:
                entries.append(ch)
        if buf:
            entries.append(buf)
    return entries


def build_characters_arg(entries: list[str]) -> str:
    """Build cwg's `--characters` argument: single hanzi as-is, multi-char
    entries wrapped in parentheses so cwg groups them as words and renders
    a single combined definition spanning their rows."""
    out = []
    for entry in entries:
        if len(entry) == 1:
            out.append(entry)
        else:
            out.append("(" + entry + ")")
    return "".join(out)


def check_deps() -> None:
    missing = []
    if not MAKEMEAHANZI.joinpath("dictionary.txt").exists():
        missing.append(f"  - {MAKEMEAHANZI}/dictionary.txt (run ./setup.sh)")
    if not CEDICT.joinpath("data").exists():
        missing.append(f"  - {CEDICT}/data (run ./setup.sh)")
    if not FONT_PATH.exists():
        missing.append(f"  - {FONT_PATH} (run ./setup.sh)")
    if missing:
        sys.stderr.write("Missing data dependencies:\n" + "\n".join(missing) + "\n")
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--input",
        type=Path,
        default=REPO / "hsk3" / "HSK 1 (3.0 only).tsv",
        help="4-column TSV (traditional, simplified, pinyin, definition).",
    )
    ap.add_argument(
        "--title",
        default="HSK 1 (3.0 only)",
        help="Worksheet header title (cwg caps at 20 chars).",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=REPO / "worksheets" / "hsk1-3.0-only.pdf",
        help="Where to write the resulting PDF.",
    )
    ap.add_argument(
        "--guide",
        default="cross",
        choices=["none", "star", "cross", "cross_star", "character"],
        help="Practice-grid guide style. 'cross' = horizontal + vertical mid lines.",
    )
    ap.add_argument(
        "--page-size",
        default="letter",
        choices=["letter", "a4"],
        help="Paper size. Layout math (square size, packing) adapts automatically.",
    )
    ap.add_argument(
        "--stroke-order-color",
        default="red",
        help="Color of the current stroke in the stroke-order sequence.",
    )
    args = ap.parse_args()

    check_deps()

    entries = read_entries(args.input)
    if not entries:
        sys.exit(f"No entries parsed from {args.input}")
    chars = build_characters_arg(entries)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hanzi-worksheet-") as wd:
        env = os.environ.copy()
        env["CWG_FONT_NAME"] = FONT_NAME
        env["CWG_FONT_PATH"] = str(FONT_PATH)
        env["CWG_PAGE_SIZE"] = args.page_size
        env["CWG_MAX_CHARACTERS"] = "2000"
        env["PYTHONPATH"] = str(CWG_SRC) + os.pathsep + env.get("PYTHONPATH", "")

        subprocess.run(
            [
                sys.executable,
                str(GEN_PY),
                f"--makemeahanzi={MAKEMEAHANZI}",
                f"--cedict={CEDICT}",
                f"--characters={chars}",
                f"--title={args.title}",
                f"--guide={args.guide}",
                f"--stroke-order-color={args.stroke_order_color}",
            ],
            cwd=wd,
            env=env,
            check=True,
        )
        produced = Path(wd) / "sheet.pdf"
        if not produced.exists():
            sys.exit("cwg did not produce sheet.pdf (see stderr above)")
        shutil.copy(produced, args.output)
        print(f"Wrote {args.output} ({len(entries)} entries)")


if __name__ == "__main__":
    main()
