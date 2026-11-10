import re


UNCERTAINTY_MARKER_RE = re.compile(r"\(\s*\?\s*\)|\?")


def normalize_uncertain_text(value: str) -> tuple[str | None, bool]:
    """Remove uncertainty markers and report whether the value contained one."""
    value, marker_count = UNCERTAINTY_MARKER_RE.subn("", value)
    value = " ".join(value.split())
    return value or None, marker_count > 0
