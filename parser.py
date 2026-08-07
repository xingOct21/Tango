import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORD_FILES = {
    "jp": os.path.join(BASE_DIR, "word.md"),
    "en": os.path.join(BASE_DIR, "word_en.md"),
}
HEADER_LABELS = {"日语", "英语", "问题"}


def parse_words(book="jp"):
    path = WORD_FILES.get(book, WORD_FILES["jp"])
    words = []
    with open(path, encoding="utf-8") as f:
        current_section = ""
        for line in f:
            line = line.rstrip()
            section_match = re.match(r"^## (.+)", line)
            if section_match:
                current_section = section_match.group(1)
                continue
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 3:
                continue
            jp, kana, zh = cols[0], cols[1], cols[2]
            if jp in HEADER_LABELS or not jp or not zh:
                continue
            words.append({"jp": jp, "kana": kana, "zh": zh, "section": current_section})
    return words
