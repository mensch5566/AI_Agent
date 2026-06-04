"""Classify a fact.source_account into one of four display-resolution classes
(spec §15 G6). Order matters: null -> synthetic -> preserved_pdf_label -> tag_like."""
import re

_QNAME_LIKE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")  # CamelCase local tag, no spaces

def classify_source_account(sa):
    if sa is None or sa == "":
        return "null"
    if sa.startswith("SUM(") or "components)" in sa or "+G&A)" in sa:
        return "synthetic"
    if _QNAME_LIKE.match(sa):
        return "tag_like"
    return "preserved_pdf_label"   # has spaces / punctuation -> already PDF text
