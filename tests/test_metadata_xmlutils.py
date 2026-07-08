import pytest

from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    drop_unknown,
    first_string,
    publication_idno_string,
)


class FakeXPathResult:
    def __init__(self, string_value):
        self.string_value = string_value


class FakeXPathProcessor:
    def __init__(self, result):
        self.result = result
        self.contexts = []
        self.evaluated_xpaths = []
        self.namespaces = []

    def declare_namespace(self, prefix, uri):
        self.namespaces.append((prefix, uri))

    def set_context(self, *, xdm_item):
        self.contexts.append(xdm_item)

    def evaluate_single(self, xpath):
        self.evaluated_xpaths.append(xpath)
        return self.result


class FakeProcessor:
    def __init__(self, result):
        self.xpath_processor = FakeXPathProcessor(result)

    def new_xpath_processor(self):
        return self.xpath_processor


def test_create_xpath_expr_evaluates_with_tei_namespace_and_context():
    proc = FakeProcessor(FakeXPathResult(" O.Vleem. 11A "))

    evaluate = create_xpath_expr(
        proc,
        "normalize-space(.)",
        value_processor=lambda value: value.strip().upper(),
    )

    assert evaluate("root") == "O.VLEEM. 11A"
    assert proc.xpath_processor.namespaces == [("tei", "http://www.tei-c.org/ns/1.0")]
    assert proc.xpath_processor.contexts == ["root"]
    assert proc.xpath_processor.evaluated_xpaths == ["normalize-space(.)"]


@pytest.mark.parametrize("result", [None, FakeXPathResult("")])
def test_create_xpath_expr_returns_none_for_missing_or_empty_result(result):
    evaluate = create_xpath_expr(FakeProcessor(result), "string(.)")

    assert evaluate("root") is None


def test_create_xpath_expr_returns_none_when_value_processor_drops_result():
    evaluate = create_xpath_expr(
        FakeProcessor(FakeXPathResult("hgvTEMP")),
        "string(.)",
        value_processor=drop_known_id_placeholders,
    )

    assert evaluate("root") is None


def test_create_xpath_expr_returns_none_when_value_processor_returns_empty_string():
    evaluate = create_xpath_expr(
        FakeProcessor(FakeXPathResult("placeholder")),
        "string(.)",
        value_processor=lambda value: "",
    )

    assert evaluate("root") is None


def test_first_string_wraps_xpath_with_first_item_selection():
    assert first_string(".//tei:titleStmt/tei:title") == (
        "string((.//tei:titleStmt/tei:title)[1])"
    )


def test_publication_idno_string_targets_publication_identifier_type():
    assert publication_idno_string("TM") == (
        "string((.//tei:publicationStmt/tei:idno[@type='TM'])[1])"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("hgvTEMP", None),
        ("46", "46"),
    ],
)
def test_drop_known_id_placeholders(value, expected):
    assert drop_known_id_placeholders(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("unbekannt", None),
        ("keiner", None),
        ("Cairo", "Cairo"),
    ],
)
def test_drop_unknown(value, expected):
    assert drop_unknown(value) == expected
