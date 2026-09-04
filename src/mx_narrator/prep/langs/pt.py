"""Portuguese language pack.

Keep accents and the tilde (`ã`, `õ`, `ç`, `é`, `ê`) — they change the word or
its stress. Uses the `pt_BR` num2words locale (spec 7.3 flags this as a
VERIFY item for European vs Brazilian Portuguese; ARC is a Brazilian
translation, so `pt_BR` is the correct default here). This pack owns its own
66-book abbreviation table; see `_shared.py` for why it is never shared with
`es.py` — `Jz` (Juízes/Judges) vs `Jo` (João/John) is exactly the collision
section 5 warns about.
"""

from __future__ import annotations

import logging
import re

from num2words import num2words

from mx_narrator.prep.langs._shared import (
    ScriptureWords,
    expand_scripture_generic,
    generic_sanity_checks,
    split_into_sentences,
)

logger = logging.getLogger(__name__)

BOOK_TABLE: dict[str, str] = {
    # Pentateuco
    "Gn": "Gênesis",
    "Êx": "Êxodo", "Ex": "Êxodo",
    "Lv": "Levítico",
    "Nm": "Números",
    "Dt": "Deuteronômio",
    # Históricos
    "Js": "Josué",
    "Jz": "Juízes",
    "Rt": "Rute",
    "Sm": "Samuel",
    "Rs": "Reis",
    "Cr": "Crônicas",
    "Ed": "Esdras",
    "Ne": "Neemias",
    "Et": "Ester",
    # Poéticos
    "Jó": "Jó",
    "Sl": "Salmo",  # spoken singular ("Salmo 23"), not the book name's plural
    "Pv": "Provérbios",
    "Ec": "Eclesiastes",
    "Ct": "Cânticos",
    # Profetas maiores
    "Is": "Isaías",
    "Jr": "Jeremias",
    "Lm": "Lamentações",
    "Ez": "Ezequiel",
    "Dn": "Daniel",
    # Profetas menores
    "Os": "Oseias",
    "Jl": "Joel",
    "Am": "Amós",
    "Ob": "Obadias",
    "Jon": "Jonas",
    "Mq": "Miqueias",
    "Na": "Naum",
    "Hc": "Habacuque",
    "Sf": "Sofonias",
    "Ag": "Ageu",
    "Zc": "Zacarias",
    "Ml": "Malaquias",
    # Evangelhos e Atos
    "Mt": "Mateus",
    "Mc": "Marcos",
    "Lc": "Lucas",
    "Jo": "João",
    "At": "Atos",
    # Cartas paulinas
    "Rm": "Romanos",
    "Co": "Coríntios",
    "Gl": "Gálatas",
    "Ef": "Efésios",
    "Fp": "Filipenses",
    "Cl": "Colossenses",
    "Ts": "Tessalonicenses",
    "Tm": "Timóteo",
    "Tt": "Tito",
    "Fm": "Filemom",
    # Gerais e Apocalipse
    "Hb": "Hebreus",
    "Tg": "Tiago",
    "Pe": "Pedro",
    "Jd": "Judas",
    "Ap": "Apocalipse",
}
# Scripts naturally sometimes spell the book name out in full ("1 João
# 1:1-4") instead of abbreviating it ("1 Jo 1:1-4"). Without this, the full
# name silently fails to match at all, falls through to generic number
# expansion, and produces garbled output — with no warning, since by the
# time sanity_checks runs the digits are already words. Let every full name
# match itself too.
BOOK_TABLE.update({name: name for name in set(BOOK_TABLE.values()) if name not in BOOK_TABLE})

WORDS = ScriptureWords(
    chapter_word="capítulo",
    verse_word="versículo",
    verses_word="versículos",
    range_connector="a",
    numeral_words={1: "Primeira de", 2: "Segunda de", 3: "Terceira de"},
)


def _n2w(n: int) -> str:
    return num2words(n, lang="pt_BR")


_ORDINAL_M = {
    1: "primeiro", 2: "segundo", 3: "terceiro", 4: "quarto", 5: "quinto",
    6: "sexto", 7: "sétimo", 8: "oitavo", 9: "nono", 10: "décimo",
    11: "décimo primeiro", 12: "décimo segundo", 13: "décimo terceiro",
    14: "décimo quarto", 15: "décimo quinto", 16: "décimo sexto",
    17: "décimo sétimo", 18: "décimo oitavo", 19: "décimo nono", 20: "vigésimo",
}
_ORDINAL_F = {n: (w[:-1] + "a" if w.endswith("o") else w) for n, w in _ORDINAL_M.items()}

_ORDINAL_RE = re.compile(r"\b(\d{1,2})([ºª])")
_NUMBER_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b|\b\d+(?:,\d+)?\b")

_ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bDr\."), "Doutor"),
    (re.compile(r"\bDra\."), "Doutora"),
    (re.compile(r"\bSr\."), "Senhor"),
    (re.compile(r"\bSra\."), "Senhora"),
    (re.compile(r"\betc\."), "etecétera"),
    (re.compile(r"\bp\.\s?ex\."), "por exemplo"),
    # Era markers must lose their internal periods before sentence splitting,
    # or "... 90 d.C. nos lembra" gets misread as two sentences.
    (re.compile(r"\ba\.C\."), "antes de Cristo"),
    (re.compile(r"\bd\.C\."), "depois de Cristo"),
]

_BREAK_WORDS = ("e", "mas", "porque", "que", "quando", "embora", "para", "assim")


class PortuguesePack:
    code = "pt"
    num2words_locale = "pt_BR"
    kokoro_voice = "pm_alex"

    def expand_scripture(self, text: str) -> str:
        return expand_scripture_generic(text, book_table=BOOK_TABLE, words=WORDS, num2words_fn=_n2w)

    def expand_numbers(self, text: str) -> str:
        def replace_ordinal(m: re.Match) -> str:
            n = int(m.group(1))
            feminine = m.group(2) == "ª"
            table = _ORDINAL_F if feminine else _ORDINAL_M
            if n in table:
                return table[n]
            logger.warning("pt: no ordinal word for %d%s, using cardinal instead", n, m.group(2))
            return _n2w(n)

        text = _ORDINAL_RE.sub(replace_ordinal, text)

        def replace_number(m: re.Match) -> str:
            raw = m.group(0)
            if "," in raw:
                int_part, dec_part = raw.split(",", 1)
                int_clean = int_part.replace(".", "")
                spoken_int = _n2w(int(int_clean))
                spoken_dec = " ".join(_n2w(int(d)) for d in dec_part)
                return f"{spoken_int} vírgula {spoken_dec}"
            int_clean = raw.replace(".", "")
            return _n2w(int(int_clean))

        return _NUMBER_RE.sub(replace_number, text)

    def expand_abbreviations(self, text: str) -> str:
        for pattern, replacement in _ABBREVIATIONS:
            text = pattern.sub(replacement, text)
        return text

    def split_sentences(self, text: str) -> list[str]:
        return split_into_sentences(text, max_words=25, break_words=_BREAK_WORDS)

    def sanity_checks(self, text: str) -> list[str]:
        return generic_sanity_checks(text, max_words=25)
