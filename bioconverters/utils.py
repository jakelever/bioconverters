import re
import unicodedata
import xml.etree.ElementTree as etree
from xml.sax.saxutils import escape as _xml_escape
from xml.sax.saxutils import unescape as _xml_unescape

from spans_and_trees import spans_to_passages, spans_to_tree, tree_to_spans


# Remove empty brackets (that could happen if the contents have been removed already
# e.g. for citation ( [] [] ) -> ( ) -> nothing). Also eats one adjacent leading space
# along with the bracket group, so "word ( )." doesn't leave "word ." behind.
def _remove_brackets_without_words(text: str) -> str:
    changed = True
    previous_text = text
    fixed = text
    while changed:
        fixed = re.sub(r"\s?\([^\w\t]*\)", "", previous_text)
        fixed = re.sub(r"\s?\[[^\w\t]*\]", "", fixed)
        fixed = re.sub(r"\s?\{[^\w\t]*\}", "", fixed)
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


_BRACKET_PAIRS = {"(": ")", "[": "]"}


def _blank_bracketed_xrefs(text: str, spans: list) -> tuple:
    """
    Blank out an xref that's the sole content of a surrounding "(...)"/"[...]" wrapper (e.g.
    "(Table 1)"), wrapper included. Mixed ("(see Table 1)"), grouped ("(Figure 7 and Table
    3)"), or mismatched ("[Table 1)") wrappers are left untouched. (A bibr citation whose own
    content is already bracketed, e.g. "[1]", is handled separately by _clean_numeric_citations,
    which runs first - by the time this runs, such spans are already blanked and gone.)
    Preserves length so no span-offset adjustment is needed.
    """
    new_text = text
    kept_spans = []

    for start, length, tag, attrib in spans:
        if tag != "xref":
            kept_spans.append((start, length, tag, attrib))
            continue

        end = start + length

        before_idx = start - 1
        while before_idx >= 0 and text[before_idx].isspace():
            before_idx -= 1

        after_idx = end
        while after_idx < len(text) and text[after_idx].isspace():
            after_idx += 1

        context_bracketed = (
            before_idx >= 0
            and after_idx < len(text)
            and text[before_idx] in _BRACKET_PAIRS
            and text[after_idx] == _BRACKET_PAIRS[text[before_idx]]
        )

        if context_bracketed:
            blank_start, blank_end = before_idx, after_idx + 1
            new_text = new_text[:blank_start] + " " * (blank_end - blank_start) + new_text[blank_end:]
            continue

        kept_spans.append((start, length, tag, attrib))

    return new_text, kept_spans


_CITATION_NUMBER_RE = re.compile(r"^\[?\s*\d+(?:\s*[,;\-–—]\s*\d+)*\s*\]?$")


def _clean_numeric_citations(text: str, spans: list) -> tuple:
    """
    Blank out any bibr xref (ref-type="bibr") whose own text is purely numeric, or numeric
    wrapped in square brackets - e.g. "1", "1,2,3", "1-3", "[1]", "[1,2,3]" - regardless of
    what (if anything) surrounds it in the text. Unlike _blank_bracketed_xrefs, no
    surrounding context is required: this is what catches a citation marker glued directly
    onto a word with no separating space at all (e.g. "tuberculosis<xref><sup>1</sup>
    </xref>" -> "tuberculosis1" if left unblanked), which can't be detected by looking at
    context since there isn't any.

    An author-date citation (e.g. "Smith et al., 2020") isn't purely numeric, so it's left
    untouched - unlike a bare reference number, it's still informative without the full
    reference resolved. Preserves length so no span-offset adjustment is needed.
    """
    new_text = text
    kept_spans = []
    removed_xref_starts = []

    for start, length, tag, attrib in spans:
        if tag != "xref" or attrib.get("ref-type") != "bibr":
            kept_spans.append((start, length, tag, attrib))
            continue

        end = start + length
        xref_text = text[start:end].strip()

        if _CITATION_NUMBER_RE.match(xref_text):
            new_text = new_text[:start] + " " * length + new_text[end:]
            removed_xref_starts.append(start)
            continue

        kept_spans.append((start, length, tag, attrib))

    for start in removed_xref_starts:
        collapsable_regex =  re.match(r'[\s,]\.',new_text[start:])
        if collapsable_regex:
            length = len(collapsable_regex.group(0))
            new_text = new_text[:start] + "." + ' '*(length-1) + new_text[start + length:]

    return new_text, kept_spans


_EXPONENT_RE = re.compile(r"(?<=\d)<sup[^>]*>(-?\d+)</sup>")


def _fix_exponentials(xml_string: str) -> str:
    """
    Replace "<sup>N</sup>" with "^N" when N is numeric and immediately preceded by a digit,
    e.g. "10<sup>8</sup>" -> "10^8" (plain concatenation alone would give "108"). An ordinal
    suffix ("1<sup>st</sup>") or isotope prefix ("<sup>14</sup>C") won't match, so both fall
    through unchanged - already correct as plain concatenation.
    """
    return _EXPONENT_RE.sub(r"^\1", xml_string)


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
    clean_numeric_citations: bool = False,
    clean_xrefs_in_brackets: bool = False,
    clear_empty_brackets: bool = False,
    fix_exponentials: bool = False,
):
    """
    Flatten a list of XML elements into cleaned-up passages, one string per passage. With
    return_xml=True, keep_tags spans are preserved as inline markup (e.g. "some
    <sup>1</sup>H text"); with return_xml=False, the result is plain, unescaped text.

    Args:
        elements: an XML element, or a list of XML elements, to be processed
        ignore_tags: tags whose covered text is dropped
        split_tags: tags that create passage boundaries
        keep_tags: tags whose spans are preserved while building each passage
        return_xml: return marked-up XML strings if True, plain unescaped text if False
        trim_buggy_sentences: trim overly long, unbroken runs of text (see _trim_buggy_sentences)
        clean_numeric_citations: drop a numeric bibr citation marker outright, regardless of context
            (see _clean_numeric_citations). Runs before clean_xrefs_in_brackets.
        clean_xrefs_in_brackets: drop bracket-wrapped xref clutter (see _blank_bracketed_xrefs)
        clear_empty_brackets: remove any "(...)"/"[...]"/"{...}" left containing no word
            characters, e.g. from clean_numeric_citations/clean_xrefs_in_brackets, or from an
            unrelated ignore_tag (like ext-link) that happened to be parenthesised (see
            _remove_brackets_without_words)
        fix_exponentials: with return_xml=False, recover a digit-preceded numeric "<sup>" as
            "^N" (see _fix_exponentials) - requires "sup" in keep_tags, and has no effect
            when return_xml=True since the tag is already preserved as real markup then
    """
    if not isinstance(elements, list):
        elements = [elements]

    results = []
    for elem in elements:
        text, spans = tree_to_spans(elem)
        text = _cleanup_pmc_text(text)
        if clean_numeric_citations:
            text, spans = _clean_numeric_citations(text, spans)
        if clean_xrefs_in_brackets:
            text, spans = _blank_bracketed_xrefs(text, spans)
        for passage in spans_to_passages(text, spans, ignore_tags, split_tags, keep_tags):
            passage_text = passage["text"]
            if trim_buggy_sentences:
                passage_text = _trim_buggy_sentences(passage_text)

            tree = spans_to_tree(passage_text, passage["spans"])
            xml_string = _tree_to_xml_string(tree)

            if not return_xml and fix_exponentials:
                xml_string = _fix_exponentials(xml_string)

            result_text = xml_string if return_xml else _strip_markup(xml_string)
            # Collapse whitespace after markup is stripped, not before: a blanked xref
            # inside a kept tag (e.g. clean_numeric_citations blanking "<sup><xref>1</xref></sup>"
            # to "<sup> </sup>") can leave two spaces that are only adjacent once the tag
            # itself is gone, so collapsing earlier would miss them.
            result_text = _collapse_whitespace(result_text)

            if clear_empty_brackets:
                result_text = _remove_brackets_without_words(result_text)

            results.append(result_text)

    return results
