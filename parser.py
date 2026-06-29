import os
import re

WORD_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "word.md")


def parse_words():
    words = []
    with open(WORD_MD, encoding="utf-8") as f:
        current_section = ""
        for line in f:
            line = line.rstrip()
            section_match = re.match(r"^## (.+)", line)
            if section_match:
                current_section = section_match.group(1)
                continue
            if not line.startswith("|") or line.startswith("| 日语") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 3:
                continue
            jp, kana, zh = cols[0], cols[1], cols[2]
            if not jp or not zh:
                continue
            words.append({"jp": jp, "kana": kana, "zh": zh, "section": current_section})
    return words
