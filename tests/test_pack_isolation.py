"""Section 5: each pack owns its own 66-book table; a shared table would
silently produce the wrong book name. Spanish `Jue` is Judges while
Portuguese `Jz` is Judges and `Jo` is John; English `Jn` is John while `Jg`
would be Judges. These must never cross-contaminate."""

from mx_narrator.prep.langs.en import EnglishPack
from mx_narrator.prep.langs.es import SpanishPack
from mx_narrator.prep.langs.pt import PortuguesePack


def test_spanish_table_has_no_portuguese_keys():
    from mx_narrator.prep.langs.es import BOOK_TABLE as ES
    from mx_narrator.prep.langs.pt import BOOK_TABLE as PT

    # "Jz" is Portuguese for Judges; Spanish uses "Jue" instead and must not
    # recognize "Jz" as anything at all.
    assert "Jz" in PT
    assert "Jz" not in ES


def test_portuguese_jo_is_joao_not_bled_from_spanish_jn():
    assert PortuguesePack().expand_scripture("Jo 3:16") == "João três, dezesseis"
    # Spanish's "Jn" abbreviation must not accidentally work in Portuguese text.
    unexpanded = "Jn 3:16"
    assert PortuguesePack().expand_scripture(unexpanded) == unexpanded


def test_spanish_jue_is_jueces_and_is_not_recognized_by_english():
    assert "Jueces" in SpanishPack().expand_scripture("Jue 6:12")
    unexpanded = "Jue 6:12"
    assert EnglishPack().expand_scripture(unexpanded) == unexpanded
