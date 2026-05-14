#!/usr/bin/env bash
# Fetch the runtime data that make_worksheet.py needs:
#   - makemeahanzi (stroke order + radical decomposition + per-char pinyin)
#   - CEDICT (Chinese-English dictionary, source for definitions)
#   - SourceHanSansSC-Normal.ttf (CJK glyphs for the rendered PDF)
#
# Everything lands under ./data/ which is gitignored. Re-running is safe;
# already-present files are skipped.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
DATA="$REPO/data"
mkdir -p "$DATA"

if [ ! -f "$DATA/makemeahanzi/dictionary.txt" ]; then
  echo "==> cloning makemeahanzi (≈280 MB)"
  git clone --depth 1 https://github.com/skishore/makemeahanzi.git "$DATA/makemeahanzi"
  rm -rf "$DATA/makemeahanzi/.git"
fi

if [ ! -f "$DATA/cedict/data" ]; then
  echo "==> downloading CEDICT"
  mkdir -p "$DATA/cedict"
  curl -fsSL https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz \
    | gunzip > "$DATA/cedict/data"
fi

if [ ! -f "$DATA/fonts/SourceHanSansSC-Normal.ttf" ]; then
  echo "==> downloading Source Han Sans SC"
  mkdir -p "$DATA/fonts"
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/shs.7z" \
    https://github.com/be5invis/source-han-sans-ttf/releases/download/v2.001.1/source-han-sans-ttf-2.001.1.7z
  7z e "$tmp/shs.7z" "SourceHanSansSC-Normal.ttf" "-o$DATA/fonts/"
  rm -rf "$tmp"
fi

echo "==> data ready under $DATA"
