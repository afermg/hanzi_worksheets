#!/usr/bin/python3

import sys
import json
import glob
import os
import math
import getopt
import re
from enum import Enum
from cairosvg import svg2png
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.colors import CMYKColor, Color
from spanning_translation import SpanningTranslation
from exceptions import GenException
from combine_and_shorten_definition import combine_and_shorten_definition
from word_manager import Word, WordManager
from draw import draw_full_summation_curve, \
                    draw_vertical_text, \
                    draw_bottom_summation_curve, \
                    draw_opened_top_summation_curve, \
                    draw_top_summation_curve

PROGRAM_NAME = 'gen.py';
PROGRAM_FULLNAME = 'Chinese Worksheet Generator';
PROGRAM_WEBSITE = 'chineseworksheetgenerator.org';
MAKEMEAHANZI_NAME = 'Make Me a Hanzi';
CEDICT_NAME = 'CEDICT';
CHARACTERS_FILE = 'character_infos.json';
WORDS_FILE = 'word_infos.json';
SHEET_FILE = 'sheet.pdf';

# [hanzi_worksheets patch] Page size and font path overridable via env vars.
# Default to US Letter rather than A4 — see README for rationale.
_PAGE_SIZE_NAME = os.environ.get('CWG_PAGE_SIZE', 'letter').lower();
PAGE_SIZE = letter if _PAGE_SIZE_NAME == 'letter' else A4;
# [hanzi_worksheets patch] Variable-height layout. Each character block has a
# minimum of three rows: stroke build-up (top, shares the row with the
# standalone character), dimmed-trace, cross-guide-only. Stroke build-up
# overflows to additional rows when the character has more strokes than fit
# alongside the standalone character on the top row.
GRID_OFFSET = 30;
RADICAL_HEIGHT = 0;
RADICAL_PINYIN_HEIGHT = 0;
CHARACTERS_PER_ROW = 9;
CHARACTER_ROW_WIDTH = PAGE_SIZE[0]-2*GRID_OFFSET;
SQUARE_SIZE = CHARACTER_ROW_WIDTH/CHARACTERS_PER_ROW;
# Stroke cells available alongside the standalone character on the top row
# (the character occupies cell 0). 8 stroke cells fit before overflow.
TOP_STROKE_CELLS = CHARACTERS_PER_ROW - 1;
# Stroke cells per overflow row (no character cell, whole row is strokes).
ROW_STROKE_CELLS = CHARACTERS_PER_ROW;
# Per character: 1 stroke row (top) + N overflow rows + 1 dimmed-trace + 1 cross.
PRACTICE_NON_STROKE_ROWS = 2;
SQUARE_PADDING = SQUARE_SIZE/15;
RADICAL_PADDING = RADICAL_HEIGHT/10;
# [hanzi_worksheets patch] Allow font swap via env (Source Han Sans SC etc.).
FONT_NAME = os.environ.get('CWG_FONT_NAME', 'SourceHanSansTC-Normal')
FONT_PATH = os.environ.get('CWG_FONT_PATH', FONT_NAME + '.ttf')
FONT_SIZE = 13;
HEADER_FONT_SIZE = 20;
FOOTER_FONT_SIZE = 10;
PAGE_NUMBER_FONT_SIZE = 10;
TEXT_PADDING = SQUARE_SIZE/4;
DEFINITION_PADDING = TEXT_PADDING*2;
STROKE_SIZE = SQUARE_SIZE*0.5; # size of stroke order character
STROKE_PADDING = SQUARE_PADDING*0.3;
STROKES_W = CHARACTER_ROW_WIDTH - SQUARE_SIZE - TEXT_PADDING;
MAX_STROKES = math.floor(STROKES_W / (STROKE_SIZE+STROKE_PADDING));
HEADER_PADDING = 0;
NAME_OFFSET = 300;
SCORE_OFFSET = 150;
PAGE_NUMBER_X_OFFSET = 40;
PAGE_NUMBER_Y_OFFSET = 20;
# [hanzi_worksheets patch] Lifted to handle long HSK lists in one run.
MAX_INPUT_CHARACTERS = int(os.environ.get('CWG_MAX_CHARACTERS', '1000'));
MAX_TITLE_LENGTH = 20;
GUIDE_LINE_WIDTH = 5;
FIRST_CHARACTER_ROW_Y = PAGE_SIZE[1]-HEADER_PADDING-GRID_OFFSET/2;
WORD_FONT_SIZE = 11;
# [hanzi_worksheets patch] CHARACTER_ROW_HEIGHT is per-character now; size
# WORD_OFFSET off SQUARE_SIZE so word braces still look balanced.
WORD_OFFSET = SQUARE_SIZE/4;
SUMMATION_OFFSET = 3;
SUMMATION_FROM_X = GRID_OFFSET*0.4; # word summation
DEFINITION_SEPARATOR = ', ';

# [hanzi_worksheets patch] Pleco-style tone coloring for pinyin syllables.
# Mapping per user's preferred Pleco palette: 1=red, 2=green, 3=blue, 4=purple.
TONE_COLORS = {
    1: Color(0.86, 0.13, 0.13),   # red — high level
    2: Color(0.16, 0.62, 0.27),   # green — rising
    3: Color(0.13, 0.36, 0.78),   # blue — dip
    4: Color(0.55, 0.20, 0.65),   # purple — falling
    5: Color(0.35, 0.35, 0.35),   # gray — neutral
}
_TONE_VOWELS = {}
for _t, _vs in enumerate([
        'āēīōūǖĀĒĪŌŪǕ', 'áéíóúǘÁÉÍÓÚǗ',
        'ǎěǐǒǔǚǍĚǏǑǓǙ', 'àèìòùǜÀÈÌÒÙǛ'], start=1):
    for _v in _vs:
        _TONE_VOWELS[_v] = _t

def detect_tone(syllable):
    for ch in syllable:
        if ch in _TONE_VOWELS:
            return _TONE_VOWELS[ch]
    return 5

def draw_colored_pinyin(c, x, y, pinyin, font_name, font_size):
    """Draw `pinyin` at (x, y), each whitespace-delimited syllable colored
    by its tone. Returns total width drawn."""
    saved = c._fillColorObj
    cur_x = x
    tokens = pinyin.split(' ')
    for i, syl in enumerate(tokens):
        if not syl:
            continue
        c.setFillColor(TONE_COLORS.get(detect_tone(syl), TONE_COLORS[5]))
        c.drawString(cur_x, y, syl)
        cur_x += stringWidth(syl, font_name, font_size)
        if i < len(tokens) - 1:
            c.drawString(cur_x, y, ' ')
            cur_x += stringWidth(' ', font_name, font_size)
    c.setFillColor(saved)
    return cur_x - x

def usage():
    print('usage: ' + PROGRAM_NAME + '\n' + \
            ' <default>\n' + \
            '   --makemeahanzi=<' + MAKEMEAHANZI_NAME + ' path>\n' + \
            '   --cedict=<' + CEDICT_NAME + ' path>\n' + \
            '   --characters=<chinese characters>\n' + \
            '   [--title=<custom title>]\n' + \
            '   [--guide=star]\n' + \
            ' --info\n' + \
            '   --makemeahanzi=<' + MAKEMEAHANZI_NAME + ' path>\n' + \
            '   --cedict=<' + CEDICT_NAME + ' path>\n' + \
            '   --characters=<chinese characters>\n' + \
            ' --sheet\n' + \
            '   --makemeahanzi=<' + MAKEMEAHANZI_NAME + ' path>\n' + \
            '   [--title=<custom title>]\n' + \
            '   [--guide=star]\n' + \
            '   [--stroke-order-color=black]');

# TODO: rename to character
class character_info:
    def __init__(self, character, radical, pinyin, radical_pinyin, \
            definition, stroke_order):
        self.character = character;
        self.radical = radical;
        self.pinyin = pinyin;
        self.radical_pinyin = radical_pinyin;
        self.definition = definition;
        self.stroke_order = stroke_order;

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True);

def object_to_character_info(obj):
    return character_info(obj['character'], obj['radical'], obj['pinyin'], \
            obj['radical_pinyin'], obj['definition'], obj['stroke_order']);

class Guide(Enum):
    NONE = 1
    STAR = 2
    CROSS = 3
    CROSS_STAR = 4
    CHARACTER = 5

def get_character_json(file, character):
    while 1:
        line = file.readline();
        if line == '':
            break;
        item = json.loads(line);
        if item['character'] == character:
            return item;
    return -1;

def get_dictionary_json(dataset_path, character):
    with open(dataset_path + '/dictionary.txt', 'r', encoding='utf8') as dictionary:
        return get_character_json(dictionary, character);

def get_graphics_json(dataset_path, character):
    with open(dataset_path + '/graphics.txt', 'r', encoding='utf8') as graphics:
        return get_character_json(graphics, character);

def retrieve_info(dataset_path, character):
    d = get_dictionary_json(dataset_path, character);
    g = get_graphics_json(dataset_path, character);

    if d == -1 or g == -1:
        return -1;

    try:
        radical = d['radical'];
        pinyin = d['pinyin'];

        r = get_dictionary_json(dataset_path, radical);

        if r == -1:
            return -1;

        radical_pinyin = r['pinyin'];
        definition = d['definition'];

        stroke_order = g['strokes'];
        return character_info(character, radical, pinyin, radical_pinyin, \
                definition, stroke_order);
    except KeyError:
        raise GenException('Invalid dataset data for character ' + character);
    
def create_character_svg(working_dir, character_info):
    create_stroke_svg(working_dir, character_info.character, character_info.stroke_order, \
                        len(character_info.stroke_order), dimmed=False);

def create_radical_svg(dataset_path, working_dir, character_info):
    radical = character_info.radical;

    g = get_graphics_json(dataset_path, radical)
    if g == -1:
        raise GenException('Could not find data for radical ' + radical);
    stroke_order = g['strokes'];
    create_stroke_svg(working_dir, radical, stroke_order, \
                        len(stroke_order));

def create_stroke_svg(working_dir, filename, stroke_order, stroke_number, stroke_color="black", dimmed=True):
    # [hanzi_worksheets patch] All progressive/dimmed strokes drawn in gray —
    # no "current stroke" highlight, no ghost preview of future strokes. The
    # progressive row builds up from empty to a full dimmed character.
    # The standalone reference (`<char>.png`, via create_character_svg) keeps
    # solid `stroke_color` so cell 0 of the top row stays prominent.
    output = '<svg viewBox="0 0 128 128">' \
            '<g transform="scale(0.125, -0.125) translate(0, -900)">'
    if not dimmed:
        fill = stroke_color
        for j in range(len(stroke_order)):
            output += '\n<path fill="' + fill + '" d="' + stroke_order[j] + '"></path>';
    elif stroke_number == 0:
        for j in range(len(stroke_order)):
            output += '\n<path fill="gray" d="' + stroke_order[j] + '"></path>';
    else:
        for j in range(stroke_number):
            output += '\n<path fill="gray" d="' + stroke_order[j] + '"></path>';
    output += '</g>\n</svg>';
    with open(os.path.join(working_dir, filename + '.svg'), 'w') as svg:
        svg.write(output);

def create_stroke_order_svgs(working_dir, character_info, stroke_order_color):
    character = character_info.character;
    stroke_order = character_info.stroke_order;
    for i in range(0, len(stroke_order)+1):
        create_stroke_svg(working_dir, character + str(i), stroke_order, i, stroke_order_color);

def convert_svg_to_png(svg_path, png_path):
    quality = 100;
    with open(svg_path, 'r') as f:
        svg_data = '\n'.join(f.readlines());
    svg2png(bytestring=svg_data, write_to=png_path, \
            output_width=quality, output_height=quality);

def convert_svgs_to_pngs(working_dir):
    for file in list_files(working_dir, '.*\.svg'):
        file = os.path.join(working_dir, file[:-4]);
        convert_svg_to_png(file + '.svg', file + '.png');

def delete_files(directory, pattern):
    for file in list_files(directory, pattern):
        os.remove(os.path.join(directory, file));

def list_files(directory, pattern):
    result = [];
    for f in os.listdir(directory):
        if re.match(pattern, f):
            result.append(f);
    return result;

def shorten_stroke_order(stroke_order, max_strokes):
    if len(stroke_order) <= max_strokes:
        return stroke_order;
    step = math.ceil(len(stroke_order) / max_strokes);
    new_stroke_order = [];
    for i in range(0, len(stroke_order), step):
        new_stroke_order.append(stroke_order[i]);
    if new_stroke_order[-1] != stroke_order[-1]:
        new_stroke_order.append(stroke_order[-1]);
    return new_stroke_order;

def draw_header(canvas, title, font_size, y):
    canvas.setFont(FONT_NAME, font_size);
    canvas.drawString(GRID_OFFSET, y, title);
    canvas.drawString(NAME_OFFSET, y, 'Name:');
    canvas.drawString(NAME_OFFSET + SCORE_OFFSET, y, 'Score:');

def draw_guide(canvas, x, y, guide, working_dir, character_info):
    if guide == Guide.CHARACTER:
        prefill_character(working_dir, canvas, x + SQUARE_PADDING, \
                            y - SQUARE_PADDING, \
                            character_info.character + '0.png');
        return;

    canvas.setDash(1, 2);
    canvas.setStrokeColor(CMYKColor(0, 0, 0, 0.2));

    if guide == Guide.STAR or guide == Guide.CROSS_STAR:
        x1 = x;
        y1 = y;
        x2 = x1 + SQUARE_SIZE;
        y2 = y - SQUARE_SIZE;
        canvas.line(x1, y1, x2, y2);
        canvas.line(x2, y1, x1, y2);
    if guide == Guide.CROSS or guide == Guide.CROSS_STAR:
        x1 = x;
        y1 = y - SQUARE_SIZE/2;
        x2 = x1 + SQUARE_SIZE;
        y2 = y1;
        canvas.line(x1, y1, x2, y2);
        x1 = x + SQUARE_SIZE/2;
        y1 = y;
        x2 = x1;
        y2 = y1 - SQUARE_SIZE;
        canvas.line(x1, y1, x2, y2);
        
    canvas.setDash();
    canvas.setStrokeColor(CMYKColor(0, 0, 0, 1));

def prefill_character(working_dir, canvas, x, y, filename):
    size = SQUARE_SIZE - 2*SQUARE_PADDING
    canvas.drawImage(os.path.join(working_dir, filename), \
            x, \
            y - size, \
            size, \
            size, mask='auto');

def _stroke_rows_needed(stroke_n):
    """Number of stroke-progression rows required for stroke_n strokes.
    Each stroke row has CHARACTERS_PER_ROW-1 stroke cells (cell 0 is the
    reference character)."""
    per_row = CHARACTERS_PER_ROW - 1
    if stroke_n <= 0:
        return 1
    return max(1, math.ceil(stroke_n / per_row))


def compute_char_layout(stroke_n):
    """Return (n_total_rows, n_stroke_rows) for a character with stroke_n strokes."""
    n_stroke_rows = _stroke_rows_needed(stroke_n)
    # +2: one dimmed-trace row + one cross-only row.
    return n_stroke_rows + 2, n_stroke_rows


def compute_page_layout(character_infos):
    """Pack characters greedily into pages. Returns a list of dicts:
       {'page', 'top_y', 'n_total_rows', 'n_stroke_rows'} per character."""
    page_top_y = PAGE_SIZE[1] - GRID_OFFSET/2
    page_min_y = GRID_OFFSET/2
    positions = []
    current_y = page_top_y
    page = 1
    for info in character_infos:
        n_total_rows, n_stroke_rows = compute_char_layout(len(info.stroke_order))
        h = n_total_rows * SQUARE_SIZE
        if current_y - h < page_min_y - 1e-6:
            page += 1
            current_y = page_top_y
        positions.append({
            'page': page,
            'top_y': current_y,
            'n_total_rows': n_total_rows,
            'n_stroke_rows': n_stroke_rows,
        })
        current_y -= h
    return positions


def _draw_side_label(canvas, char_block_top_y, block_h, character_info, suppress_definition):
    """Draw colored pinyin (+ short definition) rotated 90° in the right margin
    of the character block. Definition suppressed when the character is part
    of a grouped word."""
    pinyin = character_info.pinyin[0]
    tone_color = TONE_COLORS.get(detect_tone(pinyin), TONE_COLORS[5])

    sep = '  '
    pinyin_w = stringWidth(pinyin, FONT_NAME, FONT_SIZE)
    sep_w = stringWidth(sep, FONT_NAME, FONT_SIZE)
    available = block_h - 2*TEXT_PADDING
    max_def_w = available - pinyin_w - sep_w

    def_text = ''
    if not suppress_definition and max_def_w > 0:
        definition = character_info.definition.replace(';', ',').split(',')
        def_text = combine_and_shorten_definition(definition, DEFINITION_SEPARATOR,
                                                  max_def_w, FONT_NAME, FONT_SIZE).text
    def_w = stringWidth(def_text, FONT_NAME, FONT_SIZE) if def_text else 0
    total_w = pinyin_w + (sep_w + def_w if def_text else 0)

    xto = PAGE_SIZE[0] - GRID_OFFSET/2
    ymid = char_block_top_y - block_h/2

    canvas.saveState()
    canvas.setFont(FONT_NAME, FONT_SIZE)
    canvas.translate(xto, ymid - total_w/2)
    canvas.rotate(90)
    saved = canvas._fillColorObj
    canvas.setFillColor(tone_color)
    canvas.drawString(0, 0, pinyin)
    canvas.setFillColor(saved)
    if def_text:
        canvas.drawString(pinyin_w + sep_w, 0, def_text)
    canvas.restoreState()


def draw_character_row(working_dir, canvas, character_info, top_y, n_total_rows, n_stroke_rows, suppress_definition=False):
    """[hanzi_worksheets patch] Variable-height character block.

    Layout per character (3 rows for ≤8-stroke chars; more for longer ones):

      - Row 0 (top stroke row): cell 0 = solid reference character (the
        ONLY place the solid glyph appears in the block); cells 1..N-1 =
        progressive stroke build-up (strokes 1..min(8, stroke_n)).
      - Rows 1..n_stroke_rows-1 (overflow stroke rows, only when stroke_n > 8):
        every cell continues the stroke progression. No solid reference,
        so the build-up reads cleanly left-to-right, top-to-bottom.
      - Dimmed-trace row: every cell holds the dimmed full character.
      - Cross-only row: every cell holds just the cross guide.

    Past the last real stroke, trailing cells in the final stroke row fall
    back to the full dimmed character so the build-up "lands" cleanly."""
    stroke_n = len(character_info.stroke_order)
    character_png = character_info.character + '.png'
    dimmed_png = character_info.character + '0.png'

    def draw_progressive_cell(x, row_top, row_bot, step):
        canvas.rect(x, row_bot, SQUARE_SIZE, SQUARE_SIZE)
        draw_guide(canvas, x, row_top, Guide.CROSS, working_dir, character_info)
        fname = (character_info.character + str(step) + '.png'
                 if 1 <= step <= stroke_n else dimmed_png)
        path = os.path.join(working_dir, fname)
        if os.path.exists(path):
            prefill_character(working_dir, canvas,
                              x + SQUARE_PADDING, row_top - SQUARE_PADDING, fname)

    # Top stroke row — cell 0 is the only solid reference.
    row_top = top_y
    row_bot = row_top - SQUARE_SIZE
    canvas.rect(GRID_OFFSET, row_bot, SQUARE_SIZE, SQUARE_SIZE)
    ref_path = os.path.join(working_dir, character_png)
    if os.path.exists(ref_path):
        canvas.drawImage(ref_path,
                         GRID_OFFSET + SQUARE_PADDING, row_bot + SQUARE_PADDING,
                         SQUARE_SIZE - 2*SQUARE_PADDING,
                         SQUARE_SIZE - 2*SQUARE_PADDING, mask='auto')
    for cell in range(1, CHARACTERS_PER_ROW):
        x = GRID_OFFSET + cell * SQUARE_SIZE
        # In the top row: cell 1 = stroke 1, cell 2 = strokes 1..2, etc.
        draw_progressive_cell(x, row_top, row_bot, cell)

    # Overflow stroke rows — full row of stroke cells, no solid reference.
    for row_idx in range(1, n_stroke_rows):
        row_top = top_y - row_idx * SQUARE_SIZE
        row_bot = row_top - SQUARE_SIZE
        # Strokes already shown above this row = top row's 8 + (row_idx-1)*9.
        base_step = (CHARACTERS_PER_ROW - 1) + (row_idx - 1) * CHARACTERS_PER_ROW
        for cell in range(CHARACTERS_PER_ROW):
            x = GRID_OFFSET + cell * SQUARE_SIZE
            draw_progressive_cell(x, row_top, row_bot, base_step + cell + 1)

    # Dimmed-trace row — every cell is the dimmed full character.
    trace_top = top_y - n_stroke_rows * SQUARE_SIZE
    trace_bot = trace_top - SQUARE_SIZE
    dimmed_path = os.path.join(working_dir, dimmed_png)
    for cell in range(CHARACTERS_PER_ROW):
        x = GRID_OFFSET + cell * SQUARE_SIZE
        canvas.rect(x, trace_bot, SQUARE_SIZE, SQUARE_SIZE)
        draw_guide(canvas, x, trace_top, Guide.CROSS, working_dir, character_info)
        if os.path.exists(dimmed_path):
            prefill_character(working_dir, canvas,
                              x + SQUARE_PADDING, trace_top - SQUARE_PADDING, dimmed_png)

    # Cross-only row — guides only, no character at all.
    cross_top = trace_bot
    cross_bot = cross_top - SQUARE_SIZE
    for cell in range(CHARACTERS_PER_ROW):
        x = GRID_OFFSET + cell * SQUARE_SIZE
        canvas.rect(x, cross_bot, SQUARE_SIZE, SQUARE_SIZE)
        draw_guide(canvas, x, cross_top, Guide.CROSS, working_dir, character_info)

    _draw_side_label(canvas, top_y, n_total_rows * SQUARE_SIZE,
                     character_info, suppress_definition)

def draw_footer(canvas, font_size, y):
    text1 = 'Created with ' + PROGRAM_FULLNAME;
    text2 = PROGRAM_WEBSITE;
    text2_w = stringWidth(text2, FONT_NAME, FOOTER_FONT_SIZE);
    text2_x = PAGE_SIZE[0]-GRID_OFFSET-text2_w;
    canvas.setFont(FONT_NAME, font_size);
    canvas.drawString(GRID_OFFSET, y, text1);
    canvas.drawString(text2_x, y, text2);
    y -= 0.2*FONT_SIZE;
    canvas.linkURL('www.' + text2, (text2_x, y, \
                    text2_x + text2_w, y + 0.8*FONT_SIZE));

def draw_page_number(canvas, page_number, font_size):
    canvas.setFont(FONT_NAME, font_size);
    canvas.drawString(PAGE_SIZE[0]-PAGE_NUMBER_X_OFFSET, PAGE_NUMBER_Y_OFFSET, \
            str(int(page_number)));

def _char_top_y(positions, idx):
    return positions[idx]['top_y']

def _char_bot_y(positions, idx):
    p = positions[idx]
    return p['top_y'] - p['n_total_rows'] * SQUARE_SIZE

def draw_words(canvas, positions, words, page_number, spanning_map):
    """[hanzi_worksheets patch] Use precomputed per-character positions so
    word braces still align when blocks have variable heights."""
    # bottom words — end is on this page, begin was on a previous page
    for word in words:
        end = word.character_end_index
        begin = word.character_begin_index
        if positions[end]['page'] == page_number and positions[begin]['page'] < page_number:
            draw_bottom_word(canvas, _char_bot_y(positions, end),
                             spanning_map[word].bottom_translation)
    # full words — both begin and end on this page
    for word in words:
        begin = word.character_begin_index
        end = word.character_end_index
        if positions[begin]['page'] == page_number and positions[end]['page'] == page_number:
            draw_full_word(canvas, _char_top_y(positions, begin),
                           _char_bot_y(positions, end), word)
    # top words — begin on this page, end on a later page
    for word in words:
        begin = word.character_begin_index
        end = word.character_end_index
        if positions[begin]['page'] == page_number and positions[end]['page'] > page_number:
            draw_top_word(canvas, _char_top_y(positions, begin),
                          spanning_map[word].top_translation)

def draw_top_word(canvas, yto, top_translation):
    yto_word = yto - WORD_OFFSET
    ymid = int(yto_word/2)
    if top_translation == '':
        draw_opened_top_summation_curve(canvas,
                                        SUMMATION_FROM_X+SUMMATION_OFFSET,
                                        SUMMATION_OFFSET, GRID_OFFSET,
                                        yto)
        return
    draw_vertical_text(canvas, FONT_NAME, WORD_FONT_SIZE, SUMMATION_FROM_X,
                       ymid, top_translation)
    draw_top_summation_curve(canvas,
                             SUMMATION_FROM_X+SUMMATION_OFFSET,
                             SUMMATION_OFFSET, GRID_OFFSET,
                             yto)

def draw_bottom_word(canvas, yfrom, bottom_translation):
    yfrom_word = yfrom + WORD_OFFSET
    ymid = PAGE_SIZE[1] - int((PAGE_SIZE[1]-yfrom_word)/2)
    draw_vertical_text(canvas, FONT_NAME, WORD_FONT_SIZE,
                       SUMMATION_FROM_X, ymid, bottom_translation)
    draw_bottom_summation_curve(canvas, SUMMATION_FROM_X+SUMMATION_OFFSET,
                                yfrom, GRID_OFFSET,
                                PAGE_SIZE[1]-SUMMATION_OFFSET)

def draw_full_word(canvas, yto, ybot, word):
    h = yto - ybot
    h_word = h - 2*WORD_OFFSET
    ymid = yto - WORD_OFFSET - h_word/2
    text = combine_and_shorten_definition(word.definition,
                                          DEFINITION_SEPARATOR, h,
                                          FONT_NAME, WORD_FONT_SIZE).text
    draw_vertical_text(canvas, FONT_NAME, WORD_FONT_SIZE,
                       SUMMATION_FROM_X, ymid, text)
    draw_full_summation_curve(canvas, SUMMATION_FROM_X+SUMMATION_OFFSET,
                              ybot, GRID_OFFSET, yto)
   
# TODO: this should return list of words not found
# and main should display them as warnings
def generate_infos(makemeahanzi_path, cedict_path, working_dir, characters):
    if ( len(characters) == 0 ):
        raise GenException('No characters provided');
    manager = WordManager(characters, cedict_path);
    characters = manager.get_characters();
    words = manager.get_words();
    if len(characters) > MAX_INPUT_CHARACTERS:
        raise GenException('Maximum number of characters exceeded (' + \
                str(len(characters)) + \
                '/' + str(MAX_INPUT_CHARACTERS) + ')');

    generate_character_infos(working_dir, characters, makemeahanzi_path);
    generate_word_infos(working_dir, words);

def generate_character_infos(working_dir, characters, makemeahanzi_path):
    with open(os.path.join(working_dir, CHARACTERS_FILE), 'w') as cf:
        for i in range(len(characters)):
            character = characters[i];
            info = retrieve_info(makemeahanzi_path, character);
            if info == -1:
                raise GenException('Could not find data for character ' + \
                        character);
            j = info.toJSON();
            cf.write(j + '\n');

def generate_word_infos(working_dir, words):
    with open(os.path.join(working_dir, WORDS_FILE), 'w') as wf:
        for word in words:
            j = word.toJSON();
            wf.write(j + '\n');

def load_data_from_json_file(working_dir, filename, parse_function):
    data = [];
    with open(os.path.join(working_dir, filename), 'r') as f:
        while 1:
            line = f.readline();
            if line == '':
                break;
            j = json.loads(line);
            data.append(parse_function(j));
    return data;

def filter_out_words_with_empty_definition(words):
    filtered = [];
    for word in words:
        if len(word.definition) != 0:
            filtered.append(word);
    return filtered;

# returns map from word to spanning translation
# not all words have a spanning translation
def get_spanning_translations(positions, words):
    """[hanzi_worksheets patch] Position-aware spanning: relies on the
    precomputed `positions` to detect words split across pages and to size
    the available vertical space for the two halves of the definition."""
    spanning_translations = dict()
    page_top = PAGE_SIZE[1] - GRID_OFFSET/2
    for word in words:
        begin = word.character_begin_index
        end = word.character_end_index
        if positions[end]['page'] - positions[begin]['page'] != 1:
            continue  # only handle exactly-one-page spans for now

        # bottom half: from end-char's bottom up to top of its page
        end_bot = positions[end]['top_y'] - positions[end]['n_total_rows'] * SQUARE_SIZE
        yfrom = end_bot + WORD_OFFSET
        max_w = page_top - yfrom
        result = combine_and_shorten_definition(word.definition,
                                                DEFINITION_SEPARATOR,
                                                max_w,
                                                FONT_NAME, WORD_FONT_SIZE)
        bottom_translation = result.text

        if result.num_words == len(word.definition):
            spanning_translations[word] = SpanningTranslation('', bottom_translation)
            continue

        # top half: remaining text on begin-char's page
        remaining = word.definition[result.num_words:]
        max_w = positions[begin]['top_y'] - WORD_OFFSET
        top_result = combine_and_shorten_definition(remaining,
                                                    DEFINITION_SEPARATOR,
                                                    max_w,
                                                    FONT_NAME, WORD_FONT_SIZE)
        spanning_translations[word] = SpanningTranslation(top_result.text, bottom_translation)
    return spanning_translations

def generate_sheet(makemeahanzi_path, working_dir, title, guide, stroke_order_color):
    if len(title) > MAX_TITLE_LENGTH:
        raise GenException('Title length exceeded (' + str(len(title)) + \
                '/' + str(MAX_TITLE_LENGTH) + ')');

    character_infos = [];
    words = [];

    character_infos = load_data_from_json_file(working_dir, CHARACTERS_FILE, \
                                                object_to_character_info);
    words = load_data_from_json_file(working_dir, WORDS_FILE, Word.fromJSON);
    words = filter_out_words_with_empty_definition(words);

    c = canvas.Canvas(os.path.join(working_dir, SHEET_FILE), PAGE_SIZE);
    pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH));

    chars_in_word = set()
    for w in words:
        for j in range(w.character_begin_index, w.character_end_index + 1):
            chars_in_word.add(j)

    # [hanzi_worksheets patch] Pre-compute per-char layout so we can pack
    # variable-height blocks onto pages and word braces still align.
    positions = compute_page_layout(character_infos)
    words_with_spanning_translation = get_spanning_translations(positions, words)

    current_page = 1
    for i in range(len(character_infos)):
        pos = positions[i]
        if pos['page'] != current_page:
            draw_words(c, positions, words, current_page,
                       words_with_spanning_translation)
            c.showPage()
            current_page = pos['page']
        info = character_infos[i]
        create_character_svg(working_dir, info)
        create_radical_svg(makemeahanzi_path, working_dir, info)
        create_stroke_order_svgs(working_dir, info, stroke_order_color)
        convert_svgs_to_pngs(working_dir)
        draw_character_row(working_dir, c, info, pos['top_y'],
                           pos['n_total_rows'], pos['n_stroke_rows'],
                           i in chars_in_word)
        delete_files(working_dir, '.*\.svg')
        delete_files(working_dir, '.*\.png')

    draw_words(c, positions, words, current_page,
               words_with_spanning_translation)
    c.setTitle(title)
    c.showPage()
    c.save()

def get_guide(guide_str):
    if guide_str == '' or guide_str == Guide.NONE.name.lower():
        return Guide.NONE;
    elif guide_str == Guide.STAR.name.lower():
        return Guide.STAR;
    elif guide_str == Guide.CROSS.name.lower():
        return Guide.CROSS;
    elif guide_str == Guide.CROSS_STAR.name.lower():
        return Guide.CROSS_STAR;
    elif guide_str == Guide.CHARACTER.name.lower():
        return Guide.CHARACTER;
    else:
        raise GenException('Invalid guide ' + guide_str);

def main(argv):
    makemeahanzi = '';
    cedict = ''
    characters = '';
    title = '';
    guide = '';
    stroke_order_color = '';
    info_mode = False;
    sheet_mode = False;
    opts, args = getopt.getopt(argv, '', \
            ['makemeahanzi=', 'cedict=', 'characters=', \
            'title=', 'guide=', 'stroke-order-color=', 'info', 'sheet']);
    for opt, arg in opts:
        if opt == '--makemeahanzi':
            makemeahanzi = arg;
        elif opt == '--cedict':
            cedict = arg;
        elif opt == '--characters':
            characters = arg;
        elif opt == '--title':
            title = arg;
        elif opt == '--guide':
            guide = arg;
        elif opt == '--stroke-order-color':
            stroke_order_color = arg;
        elif opt == '--info':
            info_mode = True;
        elif opt == '--sheet':
            sheet_mode = True;
        else:
            usage();
            exit(1);

    if info_mode == sheet_mode:
        info_mode = True;
        sheet_mode = True;

    if makemeahanzi == '' \
            or (info_mode and cedict == '') \
            or (info_mode and characters == '') \
            or (sheet_mode and not info_mode and characters != '') \
            or (info_mode and not sheet_mode and title != ''):
        usage();
        exit(1);

    working_dir = os.getcwd();
    try:
        guide_val = get_guide(guide);
        if info_mode == sheet_mode:
            generate_infos(makemeahanzi, cedict, working_dir, characters);
            generate_sheet(makemeahanzi, working_dir, title, guide_val, stroke_order_color);
            delete_files(working_dir, CHARACTERS_FILE.replace('.', '\.'));
            delete_files(working_dir, WORDS_FILE.replace('.', '\.'));
        elif info_mode:
            generate_infos(makemeahanzi, cedict, working_dir, characters);
        else:
            generate_sheet(makemeahanzi, working_dir, title, guide_val, stroke_order_color);
    except GenException as e:
        print(str(e));

if __name__ == '__main__':
    main(sys.argv[1:]);
