import re
import unicodedata

from spans_and_trees import spans_to_passages, tree_to_spans


# Remove empty brackets (that could happen if the contents have been removed already
# e.g. for citation ( [] [] ) -> ( ) -> nothing
def remove_brackets_without_words(text: str) -> str:
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
def remove_brackets_from_titles(title_text: str) -> str:
    title_text = title_text.strip()
    if title_text[0] == "[" and title_text[-2:] == "].":
        title_text = title_text[1:-2] + "."
    return title_text


def cleanup_pmc_text(text: str) -> str:
    """
    Clean up common Unicode problems (control/separator characters, dash variants)
    without changing the length of the string, so offsets remain valid.
    """
    orig_text = str(text)

    # Remove some "control-like" characters (left/right separator)
    text = text.replace("\u2028", " ").replace("\u2029", " ")
    text = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in text)
    text = "".join(ch if unicodedata.category(ch)[0] != "Z" else " " for ch in text)

    dash_characters = ["-", "­", "‐", "‑", "‒", "–", "—", "⁃", "⁓"]
    for dc in dash_characters:
        text = text.replace(dc, "-")

    assert len(text) == len(orig_text)

    return text


def collapse_whitespace(text: str) -> str:
    """
    Collapse runs of whitespace (including newlines from pretty-printed source XML) into
    a single space and strip the ends.
    """
    return re.sub(r"\s+", " ", text).strip()


def trim_sentence_lengths(text: str) -> str:
    """
    Trim sentences to a maximum length, to avoid issues with buggy sentences in some PMC articles
    """
    MAXLENGTH = 90000
    return ".".join(line[:MAXLENGTH] for line in text.split("."))


def extract_passages(elements, ignore_tags, split_tags, keep_tags):
    """
    Flatten a list of XML elements into cleaned-up text passages.

    Args:
        elements: an XML element, or a list of XML elements, to be processed
        ignore_tags: tags whose covered text is dropped
        split_tags: tags that create passage boundaries
        keep_tags: tags whose spans are retained (offset-adjusted) on the returned passages
    """
    if not isinstance(elements, list):
        elements = [elements]

    results = []
    for elem in elements:
        text, spans = tree_to_spans(elem)
        for passage in spans_to_passages(text, spans, ignore_tags, split_tags, keep_tags):
            t = cleanup_pmc_text(passage["text"])
            t = collapse_whitespace(t)
            t = remove_brackets_without_words(t)
            t = collapse_whitespace(t)
            passage["text"] = t
            if t:
                results.append(passage)

    return results
