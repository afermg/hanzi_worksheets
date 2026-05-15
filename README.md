# hanzi_worksheets

Printable Hanzi practice worksheets — variable-height blocks (3 rows for
chars with ≤8 strokes, more rows added as needed for higher-stroke chars),
US Letter or A4, with Pleco-style tone-colored pinyin (1=red, 2=green,
3=blue, 4=purple), per-character stroke build-up from stroke 1 to full
character, plus rows for tracing and free practice. Built on a lightly
patched fork of [`lucivpav/cwg`](https://github.com/lucivpav/cwg) driven
by character lists derived from the HSK 3.0 vocabulary.

Each character block (3 rows for ≤8-stroke chars; more for longer ones):

```
┌────┬────────────────────────────────────────┐  ↑
│ 字 │ ① ② ③ ④ ⑤ ⑥ ⑦ ⑧  ← strokes 1..8      │  │
├────┴────────────────────────────────────────┤  │ ← side margin:
│ ⑨ ⑩ ⑪ ⑫ ⑬ ░ ░ ░ ░  ← overflow strokes    │  │   tone-colored
├─────────────────────────────────────────────┤  │   pinyin +
│ 字 字 字 字 字 字 字 字 字 ← dimmed trace   │  │   short def.,
├─────────────────────────────────────────────┤  ↓   rotated 90°
│  ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕  ← cross-guide only   │
└─────────────────────────────────────────────┘
```

Cell 0 of the **top row** holds the solid reference character — the only
place the solid glyph appears in the block. Every other row follows its
content type: overflow stroke rows have continuing strokes across all 9
cells (only present when stroke_n > 8), the dimmed-trace row is dimmed
in all 9 cells, and the cross-only row has just the faint guide.
Characters with 9–17 strokes get one overflow row (4 rows total); ≥18
strokes get two (5 rows); and so on. The left margin carries a curly
brace + the combined definition whenever a row of characters forms a
grouped word.

```
hanzi_worksheets/
├── hsk3/                       # source character lists (4-col TSV)
│   ├── HSK 1 (3.0 only).tsv    # 252 entries new in HSK 3.0 HSK 1
│   ├── HSK 1.tsv .. HSK 6.tsv  # full HSK 3.0 lists by level
│   └── HSK 7-9.tsv
├── cwg/                        # patched fork of lucivpav/cwg
├── make_worksheet.py           # driver — reads an HSK TSV, calls cwg
├── setup.sh                    # fetch makemeahanzi + CEDICT + Source Han Sans
├── flake.nix                   # reproducible dev shell (python + cairo + 7z)
└── data/                       # gitignored — runtime data dependencies
    ├── makemeahanzi/           # stroke/radical/pinyin dataset
    ├── cedict/data             # CC-CEDICT, source for definitions
    └── fonts/                  # SourceHanSansSC-Normal.ttf
```

TSV input format (tab-separated, no header):

```
traditional<TAB>simplified<TAB>pinyin<TAB>definition
```

Only the *simplified* column is read by the driver; the others are kept
so the files round-trip through other tooling. Pinyin and definitions
shown on the worksheet come from CEDICT (looked up by cwg).

## About cwg

**Chinese Worksheet Generator** ([lucivpav/cwg](https://github.com/lucivpav/cwg),
GPLv3) reads a string of Chinese characters and renders a printable PDF
worksheet with one row per character. Each row shows the character itself,
its radical, pinyin, a short CC-CEDICT definition, a stroke-order
sequence, and a row of practice squares with an optional grid guide
(star, cross, faint character, etc.). Multi-character words can be
grouped with parentheses, e.g. `(你好)`, in which case cwg draws a curly
brace alongside the grouped rows with the word's combined definition.

This repo vendors cwg under `cwg/` (its `.git` removed) and applies a
handful of patches in `cwg/backend/src/gen.py`. Each patch is tagged
with a `[hanzi_worksheets patch]` comment so it's easy to rebase on
upstream:

| Patch | What changes | Why |
|-------|--------------|-----|
| `PAGE_SIZE` defaults to US Letter (via `CWG_PAGE_SIZE` env) | A4 → Letter | Match local paper |
| `MAX_INPUT_CHARACTERS` defaults to 1000 (via `CWG_MAX_CHARACTERS`) | 50 → 1000 | The 50-char ceiling can't fit an HSK list in one run |
| `FONT_NAME` / `FONT_PATH` overridable via `CWG_FONT_NAME` / `CWG_FONT_PATH` | Hard-coded `SourceHanSansTC-Normal.ttf` in CWD | Let the driver point at the font in `data/fonts/` |
| `draw_colored_pinyin()` + tone-detection helpers | Plain black pinyin → Pleco-style red/green/blue/purple/gray (tones 1–5) | Visual feedback during practice |
| `_draw_side_label()` | Pinyin + definition drawn inline on the top row | Free up the top row for stroke cells; pinyin + def now rotate 90° in the right margin |
| `draw_character_row(..., suppress_definition=False)` | Always draw per-char definition | When a character is part of a `(...)` word group, skip its individual definition so only the word's combined meaning is shown |
| Variable-height blocks (`compute_page_layout` + `compute_char_layout`), `CHARACTERS_PER_ROW = 9`, cell 0 of every row = solid reference char | Fixed rows-per-char, fixed chars-per-page | Default 3 rows per char (≤8 strokes); ≥9-stroke chars overflow to additional stroke rows. Stroke build-up starts at stroke 1 in cell 1 (no empty cell after the reference). |
| `create_stroke_svg(..., dimmed=True)` | "New" stroke in red + future strokes ghosted in gray | All drawn strokes in dimmed gray; no future preview. Build-up reads "no strokes → full dimmed character." `create_character_svg` keeps `dimmed=False` so cell 0's reference character stays solid black. |
| `combine_and_shorten_definition` returns truncated text instead of raising | Aborted whole run when any single definition didn't fit | A few CEDICT entries are very wide; truncating with `…` is preferable to failing |

Upstream cwg also ships a Flask frontend; we ignore it — only
`cwg/backend/src/gen.py` is used.

## Setup

Two prerequisites: a Python environment with `cairosvg` + `reportlab`,
and the data files (makemeahanzi, CC-CEDICT, the CJK font).

### Reproducible via Nix

```sh
nix develop                  # drops you in a shell with python + deps + p7zip
./setup.sh                   # one-time: clones makemeahanzi, fetches cedict + font
```

`setup.sh` is idempotent — re-running skips anything already on disk.

### Without Nix

If you're not on Nix, install Python 3.11+, `cairosvg`, `reportlab`,
`pillow`, plus `7z` (for the font archive), then run `./setup.sh`.

## Generating a worksheet

```sh
python make_worksheet.py
# → worksheets/hsk1-3.0-only.pdf
```

That's the default: reads `hsk3/HSK 1 (3.0 only).md`, writes
`worksheets/hsk1-3.0-only.pdf`, US Letter, cross guide, ~50 pages.

### Custom inputs

```sh
python make_worksheet.py \
    --input 'hsk3/HSK 2.tsv' \
    --title 'HSK 2' \
    --output worksheets/hsk2.pdf \
    --guide cross \
    --page-size letter   # or 'a4'
```

Available `--guide` values: `none`, `star`, `cross`, `cross_star`, `character`
(prefills a faint character to trace over).

### Adding new lists

Two input formats are accepted:

- **TSV** (4 cols `traditional<TAB>simplified<TAB>pinyin<TAB>definition`,
  same shape as everything in `hsk3/`). Only the simplified column is read.
- **Plain text** (`*.txt`, one entry per line). Each line is a character
  or a multi-character word. A line may also contain inline `(...)`
  groups to mix words and individual characters: `(我们)去年` →
  `["我们", "去", "年"]`.

Multi-character entries (e.g. `爱好`) are automatically wrapped in
parentheses before being passed to cwg, so they render contiguously with
a single combined definition.

## Project history

The HSK 3.0 character lists in `hsk3/` originate from
[`afermg/HSK-3.0-words-list`](https://github.com/afermg/HSK-3.0-words-list)
(itself a fork of [`drninjabatman/HSK-3.0-words-list`](https://github.com/drninjabatman/HSK-3.0-words-list)).
The `(3.0 only)` files are the subset of HSK 1 (3.0) words that don't
appear in the older HSK 2.0 HSK 1 + HSK 2 — useful for learners who
already know the pre-3.0 vocabulary.

## License

The whole repository is GPLv3. `cwg/` is GPLv3 upstream and the patches
inherit that license; the rest of the repo is GPLv3 to stay compatible
with the vendored dependency. See `LICENSE` for the full text.
