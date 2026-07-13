from collections.abc import Callable
from typing import Any


def optional_string(result: Any) -> str | None:
    """Return a stripped Saxon string value, or ``None`` when it is empty."""

    if result is None:
        return None

    value = result.string_value.strip()
    return value or None


def create_xpath_expr(
    proc: Any, xpath: str, value_processor: Callable[[str], str | None] | None = None
):
    xpath_proc = proc.new_xpath_processor()
    xpath_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")

    def eval(root):
        xpath_proc.set_context(xdm_item=root)
        result = xpath_proc.evaluate_single(xpath)
        if result is None:
            return None
        result = result.string_value
        if result == "":
            return None
        if value_processor is not None:
            result = value_processor(result)
        if result is None or result == "":
            return None

        return result

    return eval


def drop_known_id_placeholders(val):
    if val in ("hgvTEMP",):
        return None
    return val


def first_string(path):
    return f"string(({path})[1])"


def publication_idno_string(identifier_type):
    return first_string(f".//tei:publicationStmt/tei:idno[@type='{identifier_type}']")


def drop_unknown(val):
    if val in ("unbekannt", "keiner"):
        return None
    return val
