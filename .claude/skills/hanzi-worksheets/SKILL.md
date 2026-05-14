---
name: hanzi-worksheets
description: Working inside the `hanzi_worksheets` repo — modifying the patched fork of `lucivpav/cwg` in `cwg/`, generating PDF practice worksheets from HSK TSVs in `hsk3/`, debugging stroke-order rendering, tone-colored pinyin, the practice-grid layout, or the side-margin labels. Use this whenever the user is adding a new HSK list, swapping fonts, changing the practice rows (stroke build-up / dimmed tracing / cross-guide), tweaking the Pleco-style tone palette, fixing definition truncation, or anything else in this repo's reportlab + cairosvg PDF pipeline. Also covers the makemeahanzi + CEDICT data dependencies and the nix devshell driving everything.
---

# hanzi_worksheets

A vendored fork of [lucivpav/cwg](https://github.com/lucivpav/cwg) plus HSK 3.0 lists plus a nix flake, producing printable PDF practice sheets. The interesting code is the patches to `cwg/backend/src/gen.py` — they're all tagged with `[hanzi_worksheets patch]` so they're easy to find when rebasing on upstream.

## Layout

```
hanzi_worksheets/
├── cwg/backend/src/gen.py    ← patched renderer (see "Patches" below)
├── hsk3/*.tsv                ← input character lists
├── make_worksheet.py         ← driver wrapping gen.py
├── setup.sh                  ← idempotent fetcher for external data
├── flake.nix                 ← reproducible devshell
├── data/                     ← gitignored runtime deps (makemeahanzi, cedict, fonts)
└── worksheets/*.pdf          ← rendered output
```

## How to run

Always inside the nix shell so cairo, the CJK font and Python deps are on path:

```bash
nix-shell -p 'python3.withPackages(ps: with ps; [cairosvg reportlab pillow])' \
  --run "python make_worksheet.py"
```

For a different list:

```bash
python make_worksheet.py --input 'hsk3/HSK 2.tsv' --title 'HSK 2' \
                         --output worksheets/hsk2.pdf
```

The driver sets four env vars `gen.py` reads at import time:

| Env | Purpose |
|-----|---------|
| `CWG_PAGE_SIZE`     | `letter` (default) or `a4` |
| `CWG_FONT_NAME`     | name used to register the TTF with reportlab |
| `CWG_FONT_PATH`     | absolute path to the TTF |
| `CWG_MAX_CHARACTERS`| input ceiling (upstream caps at 50 for the Flask demo) |

## Input format

TSV only (Markdown support was removed deliberately — don't add it back). Four tab-separated columns, no header:

```
traditional<TAB>simplified<TAB>pinyin<TAB>definition
```

Only the *simplified* column is consumed. Pinyin and definitions on the worksheet come from CEDICT via cwg's `--info` lookup, not from the TSV. Multi-character entries (e.g. `爱好`) are auto-wrapped in `(...)` so cwg groups them and renders one combined definition.

## Patches to gen.py

Every patch is tagged `[hanzi_worksheets patch]`. The important ones:

### Tone colors — Pleco palette

```python
TONE_COLORS = {
    1: Color(0.86, 0.13, 0.13),   # red — high level
    2: Color(0.16, 0.62, 0.27),   # green — rising
    3: Color(0.13, 0.36, 0.78),   # blue — dip
    4: Color(0.55, 0.20, 0.65),   # purple — falling
    5: Color(0.35, 0.35, 0.35),   # gray — neutral
}
```

Tone is detected from diacritics on vowels (macron=1, acute=2, caron=3, grave=4, no mark=5). See `_TONE_VOWELS` and `detect_tone()`. Don't add a pinyin-lookup table — the diacritic alone is unambiguous.

### Stroke rendering: build-up from empty to dimmed

`create_stroke_svg` produces three categories of PNG and the distinction matters:

- `<char>.png` (via `create_character_svg`, called with `dimmed=False`) — solid black reference character. Used in cell 0 of the top row.
- `<char>0.png` — full dimmed character. Used as the trace template in Row 2.
- `<char>k.png` for k≥1 — cumulative strokes 0..k-1 in dimmed gray, **no** future-stroke preview. Used across stroke-progression cells.

The previous "current stroke in red, future strokes ghosted in gray" look was deliberately removed — the user found it visually noisy. The progression now reads as "empty → full dimmed character." If you need a different convention, change the `dimmed=True` branch of `create_stroke_svg` and update `create_character_svg`'s flag accordingly.

### Layout: 4 chars/page, 12 cells/row, three practice rows

`CHARACTERS_PER_PAGE = 4`, `CHARACTERS_PER_ROW = 12`, `PRACTICE_ROWS = 3`, no page header, no footer, no radical band. Per character block:

```
┌────┬────────────────────────────────────────────────┐
│ 字 │ ░ ░ ░ ░ ░ ░ ░ 字 字 字 字  ← stroke build-up  │
├────┴────────────────────────────────────────────────┤
│ ░ ░ ░ ░ ░ ░ 字 字 字 字 字 字  ← stroke build-up   │
├─────────────────────────────────────────────────────┤
│ 字 字 字 字 字 字 字 字 字 字 字 字  ← dimmed trace │
├─────────────────────────────────────────────────────┤
│  ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕ ⊕   ← cross-guide only   │
└─────────────────────────────────────────────────────┘
```

Pinyin (tone-colored) + short definition rotate 90° in the right margin via `_draw_side_label()`. The left margin carries the word-group curly brace when characters are grouped.

If you change `PRACTICE_ROWS`, `CHARACTERS_PER_PAGE`, or `CHARACTERS_PER_ROW`, recompute the height budget — Letter is 792 pt tall and:

```
SQUARE_SIZE          = (PAGE_W - 2 * GRID_OFFSET) / CHARACTERS_PER_ROW
CHARACTER_ROW_HEIGHT = SQUARE_SIZE * (1 + PRACTICE_ROWS)
                        + RADICAL_HEIGHT + RADICAL_PINYIN_HEIGHT
```

You want `CHARACTERS_PER_PAGE * CHARACTER_ROW_HEIGHT ≤ ~790`.

### Word grouping + per-char definition suppression

cwg's parentheses syntax (`(爱好)`) draws a curly brace + combined definition in the left margin. We added a `suppress_definition` flag to `draw_character_row` so individual characters belonging to a word group don't ALSO show their own definition — otherwise both compete and the result is noisy.

### Definition truncation, not failure

cwg upstream raises `GenException("Definition is too long")` when even one translation doesn't fit. We patched `combine_and_shorten_definition` to truncate with `…` instead. Losing a few words is better than aborting the whole run.

### Lifted input ceiling

`MAX_INPUT_CHARACTERS` upstream is 50, gated for the Flask demo. We default to 1000 via `CWG_MAX_CHARACTERS` so a whole HSK level goes through in one invocation.

## External data

Lives under `data/` (gitignored). `setup.sh` is idempotent — re-running skips anything already on disk.

- **makemeahanzi** (~280 MB clone): SVG strokes + per-character dictionary. `dictionary.txt` and `graphics.txt` are JSONL files keyed by character.
- **CEDICT** (single text file at `data/cedict/data`, ~10 MB after gunzip): `traditional simplified [pinyin] /def1/def2/...`
- **Source Han Sans SC** (~33 MB TTF): extracted from be5invis's 7z release. Needs `p7zip` for extraction — already in the flake's devshell.

Noto Sans CJK SC ships as OTC on the system, which reportlab can choke on. Stick with Source Han Sans where possible. If you must swap, override `CWG_FONT_PATH` to a real TTF.

## Common gotchas

- **`gen.py` runs in a temp working directory.** It writes SVGs and PNGs there per character. The driver copies `sheet.pdf` out at the end. Don't add long-lived state into the working dir.
- **Pinyin is per-character, list-typed.** `character_info.pinyin` is a list from makemeahanzi; the driver uses `[0]`. Characters with multiple readings show only the first reading.
- **`<char>.png` and `<char>0.png` are not the same file.** First is solid black (reference), second is full dimmed (trace template). If you change one, check the other.
- **gen.py's main() exits 0 on errors.** It catches `GenException` and `print`s, then returns. Always check that `sheet.pdf` actually exists before treating a run as successful — the driver does this with `produced.exists()`.
- **cwg expects the working dir, not the source dir, for character_infos.json.** The driver writes the JSONs into the tempdir via cwg's `--info` phase, then re-reads them in the `--sheet` phase. Don't break this assumption when adding env vars.
- **The vendored cwg has `.git` removed.** Don't reintroduce it as a submodule — rebase patches manually if upstream changes.
- **Don't reach into makemeahanzi via Python.** Use cwg's `--info` phase to populate `character_infos.json`. The data format is JSONL, parseable, but cwg already handles all the lookups including radical pinyin.

## Extending

| Goal | Where to edit |
|------|---------------|
| New HSK list | Drop a 4-col TSV into `hsk3/`, point `--input` at it. No code changes. |
| Different tone palette | `TONE_COLORS` in `gen.py`. Reportlab `Color(r, g, b)` takes floats in [0, 1]. |
| Different practice layout | `draw_character_row()` + the constants block at the top of `gen.py`. Recompute the height budget per "Layout" above. |
| Different page size | `CWG_PAGE_SIZE=a4` or patch the env-read line for new sizes. |
| Add a new column to TSV | `read_entries()` in `make_worksheet.py` only reads `cells[1]`. To consume more columns, extend `build_characters_arg()` and decide whether to override cwg's CEDICT-driven lookup or stay layered. |
| Generate without nix | `setup.sh` still works on plain Linux/macOS if you've got Python 3.11+ with cairosvg + reportlab + pillow plus `7z`. The flake is convenience, not a hard requirement. |

## When NOT to use this skill

If the user is working with Chinese vocabulary or HSK lists in some other repo (not `hanzi_worksheets`), most of the cwg-specific patches won't apply. The tone-detection code and Pleco color mapping are reusable in isolation, but the layout math, env-var conventions, and `<char>.png` vs `<char>0.png` distinctions are specific to this repo's vendored fork.
