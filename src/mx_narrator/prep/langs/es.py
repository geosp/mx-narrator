"""Spanish language pack.

Never strip accents or opening marks (`¿`, `¡`, `ñ`) — see module docstring in
`cli.py` and spec section 7.1. This pack owns its own 66-book abbreviation
table; see `_shared.py` for why it is never shared with `pt.py`.
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

# Abbreviation -> full spoken book name. Keys are case-sensitive, matched with
# an optional trailing period; numeral prefixes (1/2/3) are parsed separately
# by _shared.build_book_pattern, so keys never include the numeral.
BOOK_TABLE: dict[str, str] = {
    # Pentateuco
    "Gn": "Génesis", "Gen": "Génesis",
    "Ex": "Éxodo", "Éx": "Éxodo",
    "Lv": "Levítico", "Lev": "Levítico",
    "Nm": "Números", "Num": "Números",
    "Dt": "Deuteronomio", "Deut": "Deuteronomio",
    # Históricos
    "Jos": "Josué",
    "Jue": "Jueces",
    "Rt": "Rut",
    "Sam": "Samuel",
    "Re": "Reyes", "Rey": "Reyes",
    "Cr": "Crónicas", "Cron": "Crónicas",
    "Esd": "Esdras",
    "Neh": "Nehemías",
    "Est": "Ester",
    # Poéticos
    "Job": "Job",
    "Sal": "Salmo",  # spoken singular ("Salmo 23"), not the book name's plural
    "Pr": "Proverbios", "Prov": "Proverbios",
    "Ec": "Eclesiastés", "Ecl": "Eclesiastés",
    "Cnt": "Cantares",
    # Profetas mayores
    "Is": "Isaías",
    "Jer": "Jeremías",
    "Lm": "Lamentaciones", "Lam": "Lamentaciones",
    "Ez": "Ezequiel",
    "Dn": "Daniel", "Dan": "Daniel",
    # Profetas menores
    "Os": "Oseas",
    "Jl": "Joel",
    "Am": "Amós",
    "Abd": "Abdías",
    "Jon": "Jonás",
    "Miq": "Miqueas",
    "Nah": "Nahúm",
    "Hab": "Habacuc",
    "Sof": "Sofonías",
    "Hag": "Hageo",
    "Zac": "Zacarías",
    "Mal": "Malaquías",
    # Evangelios y Hechos
    "Mt": "Mateo",
    "Mr": "Marcos", "Mc": "Marcos",
    "Lc": "Lucas",
    "Jn": "Juan",
    "Hch": "Hechos",
    # Cartas paulinas
    "Ro": "Romanos", "Rom": "Romanos",
    "Co": "Corintios", "Cor": "Corintios",
    "Ga": "Gálatas", "Gal": "Gálatas",
    "Ef": "Efesios",
    "Fil": "Filipenses", "Flp": "Filipenses",
    "Col": "Colosenses",
    "Ts": "Tesalonicenses", "Tes": "Tesalonicenses",
    "Ti": "Timoteo", "Tim": "Timoteo",
    "Tit": "Tito",
    "Flm": "Filemón",
    # Generales
    "Heb": "Hebreos",
    "Stg": "Santiago",
    "Pe": "Pedro", "Ped": "Pedro",
    "Jud": "Judas",
    "Ap": "Apocalipsis", "Apoc": "Apocalipsis",
}
# Scripts naturally sometimes spell the book name out in full ("1 Juan
# 1:1-4") instead of abbreviating it ("1 Jn 1:1-4"). Without this, the full
# name silently fails to match at all, falls through to generic number
# expansion, and produces garbled output like "Juan uno:uno-cuatro" — with
# no warning, since by the time sanity_checks runs the digits are already
# words. Let every full name match itself too.
BOOK_TABLE.update({name: name for name in set(BOOK_TABLE.values()) if name not in BOOK_TABLE})

WORDS = ScriptureWords(
    chapter_word="capítulo",
    verse_word="versículo",
    verses_word="versículos",
    range_connector="al",
    numeral_words={1: "Primera de", 2: "Segunda de", 3: "Tercera de"},
)


def _n2w(n: int) -> str:
    return num2words(n, lang="es")


_ORDINAL_M = {
    1: "primero", 2: "segundo", 3: "tercero", 4: "cuarto", 5: "quinto",
    6: "sexto", 7: "séptimo", 8: "octavo", 9: "noveno", 10: "décimo",
    11: "undécimo", 12: "duodécimo", 13: "decimotercero", 14: "decimocuarto",
    15: "decimoquinto", 16: "decimosexto", 17: "decimoséptimo",
    18: "decimoctavo", 19: "decimonoveno", 20: "vigésimo",
}
_ORDINAL_F = {n: (w[:-1] + "a" if w.endswith("o") else w) for n, w in _ORDINAL_M.items()}

_ORDINAL_RE = re.compile(r"\b(\d{1,2})([ºª])")
# Grouped-thousands (dot) numbers with an optional comma-decimal, OR a bare
# digit run with an optional comma-decimal. See prep/langs/es.py tests for
# why the alternation is ordered this way.
_NUMBER_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b|\b\d+(?:,\d+)?\b")

_ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bDr\."), "Doctor"),
    (re.compile(r"\bDra\."), "Doctora"),
    (re.compile(r"\bSr\."), "Señor"),
    (re.compile(r"\bSra\."), "Señora"),
    (re.compile(r"\bSrta\."), "Señorita"),
    (re.compile(r"\b[UV]d\."), "usted"),
    (re.compile(r"\b[UV]ds\."), "ustedes"),
    (re.compile(r"\betc\."), "etcétera"),
    (re.compile(r"\bp\.\s?ej\."), "por ejemplo"),
    # Era markers must lose their internal periods before sentence splitting,
    # or "... 90 d.C. nos recuerda" gets misread as two sentences.
    (re.compile(r"\ba\.C\."), "antes de Cristo"),
    (re.compile(r"\bd\.C\."), "después de Cristo"),
]

_BREAK_WORDS = ("y", "pero", "porque", "que", "cuando", "aunque", "para", "así")


class SpanishPack:
    code = "es"
    num2words_locale = "es"
    kokoro_voice = "em_alex"

    def expand_scripture(self, text: str) -> str:
        return expand_scripture_generic(text, book_table=BOOK_TABLE, words=WORDS, num2words_fn=_n2w)

    def expand_numbers(self, text: str) -> str:
        def replace_ordinal(m: re.Match) -> str:
            n = int(m.group(1))
            feminine = m.group(2) == "ª"
            table = _ORDINAL_F if feminine else _ORDINAL_M
            if n in table:
                return table[n]
            logger.warning("es: no ordinal word for %d%s, using cardinal instead", n, m.group(2))
            return _n2w(n)

        text = _ORDINAL_RE.sub(replace_ordinal, text)

        def replace_number(m: re.Match) -> str:
            raw = m.group(0)
            if "," in raw:
                int_part, dec_part = raw.split(",", 1)
                int_clean = int_part.replace(".", "")
                spoken_int = _n2w(int(int_clean))
                spoken_dec = " ".join(_n2w(int(d)) for d in dec_part)
                return f"{spoken_int} coma {spoken_dec}"
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
