import pytest

from scrapyrus.metadata.uncertainty import normalize_uncertain_text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Alexandria", ("Alexandria", False)),
        ("Alexandria?", ("Alexandria", True)),
        ("Alexandria (?)", ("Alexandria", True)),
        ("Alexandria ( ? )", ("Alexandria", True)),
        ("  Alexandria   (?)  in   Egypt ", ("Alexandria in Egypt", True)),
        ("?", (None, True)),
        ("(?)", (None, True)),
        ("", (None, False)),
    ],
)
def test_normalize_uncertain_text(source, expected):
    assert normalize_uncertain_text(source) == expected
