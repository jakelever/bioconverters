import re
import unicodedata
import xml.etree.ElementTree as etree
from xml.sax.saxutils import escape as _xml_escape
from xml.sax.saxutils import unescape as _xml_unescape

from spans_and_trees import spans_to_passages, spans_to_tree, tree_to_spans


# Remove empty brackets (that could happen if the contents have been removed already
# e.g. for citation ( [] [] ) -> ( ) -> nothing
def _remove_brackets_without_words(text: str) -> str:
    changed = True
    previous_text = text
    fixed = text
    while changed:
        fixed = re.sub(r"\([^\w\t]*\)", "", previous_text)
        fixed = re.sub(r"\[[^\w\t]*\]", "", fixed)
        fixed = re.sub(r"\{[^\w\t]*\}", "", fixed)
        changed = bool(previous_text != fixed)
        previous_text = fixed
    return fixed


# Some articles have titles like "[A study of ...]."
# This removes the brackets while retaining the full stop
def _remove_brackets_from_titles(title_text: str) -> str:
    title_text = title_text.strip()
    if title_text[0] == "[" and title_text[-2:] == "].":
        title_text = title_text[1:-2] + "."
    return title_text


def _cleanup_pmc_text(text: str) -> str:
    """
    Clean up common Unicode problems (control/separator characters, dash variants)
    without changing the length of the string, so offsets remain valid.
    """
    orig_text = str(text)

    # Remove some "control-like" characters (left/right separator)
    text = text.replace(" ", " ").replace(" ", " ")
    text = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in text)
    text = "".join(ch if unicodedata.category(ch)[0] != "Z" else " " for ch in text)

    dash_characters = ["-", "­", "‐", "‑", "‒", "–", "—", "⁃", "⁓"]
    for dc in dash_characters:
        text = text.replace(dc, "-")

    assert len(text) == len(orig_text)

    return text


def _collapse_whitespace(text: str) -> str:
    """
    Collapse runs of whitespace (including newlines from pretty-printed source XML) into
    a single space and strip the ends.
    """
    return re.sub(r"\s+", " ", text).strip()


def _trim_buggy_sentences(text: str) -> str:
    """
    Replace overly long "sentences" (period-delimited segments) with a period followed by
    enough spaces to keep the text the same length, to avoid issues with buggy, unbroken
    runs of text in some PMC articles. Preserves length (spaces get collapsed later) so no
    span-offset adjustment is needed.
    """
    MAXLENGTH = 90000

    segments = []
    for segment in text.split("."):
        if len(segment) > MAXLENGTH:
            segment = segment[:MAXLENGTH] + "." + " " * (len(segment) - MAXLENGTH - 1)
        segments.append(segment)

    trimmed_text = ".".join(segments)
    assert len(trimmed_text) == len(text)

    return trimmed_text


def _blank_bracketed_xrefs(text: str, spans: list) -> tuple:
    """
    Blank out xref content that reads as clutter once left in plain text, two ways:

    1. An xref whose own content is already wrapped in square brackets (e.g. "[1]",
       "[1,2]") is blanked outright, brackets included - determined purely from the
       xref's own text, no surrounding context needed, since a bracketed marker like
       this reads fine dropped from a sentence as-is (e.g. "shown previously [1]." ->
       "shown previously.").
    2. An xref immediately wrapped in "(...)" with nothing else inside the parentheses
       (e.g. "(Table 1)") has the whole "(...)" blanked, parens included - the reference
       is dropped as unnecessary clutter rather than left dangling for the reader. Only
       fires when the xref is immediately adjacent (aside from whitespace) to both the
       opening and closing paren, so a mixed parenthetical like "(see Table 1)" or a
       grouped one like "(Figure 7 and Table 3)" is left untouched.

    Preserves length (spaces get collapsed later) so no span-offset adjustment is needed
    for the remaining spans.
    """
    new_text = text
    kept_spans = []

    for start, length, tag, attrib in spans:
        if tag != "xref":
            kept_spans.append((start, length, tag, attrib))
            continue

        end = start + length
        xref_text = text[start:end].strip()

        if xref_text.startswith("[") and xref_text.endswith("]"):
            new_text = new_text[:start] + " " * length + new_text[end:]
            continue

        before_idx = start - 1
        while before_idx >= 0 and text[before_idx].isspace():
            before_idx -= 1

        after_idx = end
        while after_idx < len(text) and text[after_idx].isspace():
            after_idx += 1

        is_parenthetical = (
            before_idx >= 0
            and text[before_idx] == "("
            and after_idx < len(text)
            and text[after_idx] == ")"
        )

        if is_parenthetical:
            blank_start, blank_end = before_idx, after_idx + 1
            new_text = new_text[:blank_start] + " " * (blank_end - blank_start) + new_text[blank_end:]
            continue

        kept_spans.append((start, length, tag, attrib))

    return new_text, kept_spans


def _format_metadata_header(fields: dict) -> str:
    """
    Render an ordered {label: value} mapping as "label: value" lines, one per field, skipping
    any field whose value is empty/None so callers can pass a fixed field set unconditionally.
    """
    return "\n".join(f"{label}: {value}" for label, value in fields.items() if value)


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_markup(xml_string: str) -> str:
    """
    Strip all XML tags and unescape entities (e.g. &amp; -> &), returning plain readable text.
    """
    return _xml_unescape(_TAG_RE.sub("", xml_string))


def _tree_to_xml_string(tree: etree.Element) -> str:
    """
    Serialize the inner XML content of a tree (no outer wrapper element), e.g.
    "some <sup>1</sup>H text". With no children (keep_tags=set()), this is just the
    tree's plain text, XML-escaped.
    """
    inner = _xml_escape(tree.text) if tree.text else ""
    for child in tree:
        inner += etree.tostring(child, encoding="unicode")
    return inner


def _extract_passages(
    elements,
    ignore_tags,
    split_tags,
    keep_tags,
    return_xml,
    trim_buggy_sentences,
    clean_xrefs_in_brackets: bool = False,
):
    """
    Flatten a list of XML elements into cleaned-up passages, one string per passage. With
    return_xml=True, any keep_tags spans are preserved as inline markup (e.g. "some
    <sup>1</sup>H text"). With return_xml=False, the result is plain, unescaped text with
    any markup stripped.

    Args:
        elements: an XML element, or a list of XML elements, to be processed
        ignore_tags: tags whose covered text is dropped
        split_tags: tags that create passage boundaries
        keep_tags: tags whose spans are preserved while building each passage
        return_xml: return marked-up XML strings if True, plain unescaped text if False
        trim_buggy_sentences: trim overly long, unbroken runs of text (see _trim_buggy_sentences)
        clean_xrefs_in_brackets: drop xref content that's either wrapped in "[...]" itself,
            or the sole content of a surrounding "(...)" (see _blank_bracketed_xrefs)
    """
    if not isinstance(elements, list):
        elements = [elements]

    results = []
    for elem in elements:
        text, spans = tree_to_spans(elem)
        text = _cleanup_pmc_text(text)
        if clean_xrefs_in_brackets:
            text, spans = _blank_bracketed_xrefs(text, spans)
        for passage in spans_to_passages(text, spans, ignore_tags, split_tags, keep_tags):
            passage_text = passage["text"]
            if trim_buggy_sentences:
                passage_text = _trim_buggy_sentences(passage_text)

            tree = spans_to_tree(passage_text, passage["spans"])
            xml_string = _tree_to_xml_string(tree)
            xml_string = _collapse_whitespace(xml_string)

            results.append(xml_string if return_xml else _strip_markup(xml_string))

    return results
