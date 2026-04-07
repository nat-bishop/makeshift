"""Phase B1: creation pipeline unit tests (mock LLM)."""

from app.creator.questions import parse_bool, parse_float, parse_int, parse_text


def test_parse_int():
    assert parse_int("42") == 42
    assert parse_int("the answer is 42 kg") == 42
    assert parse_int("") == 0


def test_parse_float():
    assert parse_float("1.5") == 1.5
    assert parse_float("about 0.001 kg") == 0.001


def test_parse_bool():
    assert parse_bool("1") is True
    assert parse_bool("0") is False
    assert parse_bool("0 no") is False


def test_parse_text():
    assert parse_text("  a flaming sword  ") == "a flaming sword"
