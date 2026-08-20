import re
import unicodedata
import xml.etree.ElementTree as etree

from spans_and_trees import spans_to_passages, spans_to_tree, tree_to_spans


# Remove empty brackets (that could happen if the contents have been removed already
# e.g. for citation ( [] [] ) -> ( ) -> nothing
def _remove_brackets_without_words(text: str) -> str:
    changed = True
    previous_text = text
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


def _trim_buggy_sentences(text) -> etree.Element:
    """
    
    """
    MAXLENGTH = 90000

    trimmed_text = ".".join(segment[:MAXLENGTH] + '.' + ' '*len(segment-MAXLENGTH-1) for segment in text.split("."))
    assert len(trimmed_text) == len(text)

    return trimmed_text


def _extract_passages(elements, ignore_tags, split_tags, keep_tags, return_xml):
    """
    Flatten a list of XML elements into cleaned-up XML strings, one per passage. Each
    string is the passage's plain text with any keep_tags spans preserved as inline
    markup (e.g. "some <sup>1</sup>H text"). With keep_tags empty, this is just plain text.

    Args:
        elements: an XML element, or a list of XML elements, to be processed
        ignore_tags: tags whose covered text is dropped
        split_tags: tags that create passage boundaries
        keep_tags: tags whose spans are preserved as inline markup in the returned strings
    """
    if not isinstance(elements, list):
        elements = [elements]

    results = []
    for elem in elements:
        text, spans = tree_to_spans(elem)
        text = _cleanup_pmc_text(text)
        for passage in spans_to_passages(text, spans, ignore_tags, split_tags, keep_tags):
            passage["text"] = _trim_buggy_sentences(passage["text"])
            
            tree = spans_to_tree(passage["text"], passage["spans"])
            xml_string = etree.tostring(tree, encoding="unicode")
            xml_string = _collapse_whitespace(xml_string)

            if return_xml:
                results.append(xml_string)
            else:
                results.append(_strip_markup(xml_string))

    return results
