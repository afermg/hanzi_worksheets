from reportlab.pdfbase.pdfmetrics import stringWidth
from exceptions import GenException

class Result:
    # num_words: number of words used in text
    def __init__(self, text, num_words):
        self.text = text;
        self.num_words = num_words;

# sep: string separating translations in definition
# definition: list of translations (strings)
def combine_and_shorten_definition(definition, sep, max_w, font_name, font_size):
    if len(definition) == 0:
        return Result('', 0);
    text = sep.join(definition);
    w = stringWidth(text, font_name, font_size);
    if w <= max_w:
        return Result(text, len(definition));
    if len(definition) == 1:
        # [hanzi_worksheets patch] First translation is itself too wide.
        # Truncate it with an ellipsis instead of raising — losing some
        # text is preferable to aborting the whole worksheet.
        text = definition[0];
        while text and stringWidth(text + '…', font_name, font_size) > max_w:
            text = text[:-1];
        return Result((text + '…') if text else '', 1);
    return combine_and_shorten_definition(definition[0:-1], sep, max_w, font_name, font_size);
