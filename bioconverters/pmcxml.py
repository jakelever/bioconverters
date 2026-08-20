import calendar
import io
import re
import xml.etree.ElementTree as etree
from typing import Iterable, Iterator, Optional, TextIO, Union

try:
    # python 3.8+
    from typing import TypedDict  # type: ignore
except ImportError:
    from typing_extensions import TypedDict

import bioc

from .pmc_tags import PMC_ALLOWED_SUBSECTIONS, PMC_IGNORE_TAGS, PMC_KEEP_TAGS, PMC_SPLIT_TAGS
from .utils import _extract_passages, _remove_brackets_from_titles

_MONTH_NAME_TO_NUMBER = {m: i for i, m in enumerate(calendar.month_name)}
_MONTH_NAME_TO_NUMBER.update({m: i for i, m in enumerate(calendar.month_abbr)})

_TAG_RE = re.compile(r"<[^>]+>")


class TextSource(TypedDict):
    title: Iterable[dict]
    subtitle: Iterable[dict]
    abstract: Iterable[dict]
    article: Iterable[dict]
    back: Iterable[dict]
    floating: Iterable[dict]


class PmcMeta(TypedDict):
    pmid: str
    pmcid: str
    doi: str
    pub_year: Optional[str]
    pub_month: Optional[Union[str, int]]
    pub_day: Optional[str]
    journal: str
    journal_iso: str


class PMCArticle(PmcMeta):
    text_sources: TextSource


def _extract_pmc_passages(elements, keep_tags):
    return _extract_passages(elements, PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, keep_tags)


def _assign_subsections(text_sources: TextSource) -> None:
    """
    Walk each group of passages in document order, tagging each with the most recently seen
    subsection heading (e.g. "methods", "discussion") from PMC_ALLOWED_SUBSECTIONS, if any.
    Matches against the passage's tag-stripped text, since a heading might have keep_tags
    markup embedded (e.g. an italicized word) that would otherwise prevent an exact match.
    """
    for passages in text_sources.values():
        subsection = None
        for passage in passages:
            plain_text = _TAG_RE.sub("", passage["text"])
            subsection_check = plain_text.lower().strip("01234567890. ")
            if subsection_check in PMC_ALLOWED_SUBSECTIONS:
                subsection = subsection_check
            passage["subsection"] = subsection


def _extract_article_content(article_elem: etree.Element, keep_tags) -> TextSource:
    """
    Given the XML element representing the top-level of the scientific article, extract all the text sources
    """
    # Extract the title and subtitle of the paper
    title = article_elem.findall(
        "./front/article-meta/title-group/article-title"
    ) + article_elem.findall("./front-stub/title-group/article-title")
    assert len(title) <= 1
    subtitle = article_elem.findall(
        "./front/article-meta/title-group/subtitle"
    ) + article_elem.findall("./front-stub/title-group/subtitle")

    title_text = [
        {"text": _remove_brackets_from_titles(t)} for t in _extract_pmc_passages(title, keep_tags)
    ]
    subtitle_text = [
        {"text": _remove_brackets_from_titles(t)} for t in _extract_pmc_passages(subtitle, keep_tags)
    ]

    # Extract the abstract from the paper
    abstract = article_elem.findall("./front/article-meta/abstract") + article_elem.findall(
        "./front-stub/abstract"
    )

    text_sources: TextSource = {
        "title": title_text,
        "subtitle": subtitle_text,
        "abstract": [{"text": t} for t in _extract_pmc_passages(abstract, keep_tags)],
        # Extract the full text from the paper as well as supplementaries and floating blocks of text
        "article": [
            {"text": t} for t in _extract_pmc_passages(article_elem.findall("./body"), keep_tags)
        ],
        "back": [{"text": t} for t in _extract_pmc_passages(article_elem.findall("./back"), keep_tags)],
        "floating": [
            {"text": t}
            for t in _extract_pmc_passages(article_elem.findall("./floats-group"), keep_tags)
        ],
    }

    _assign_subsections(text_sources)

    return text_sources


def _field_text(elem, tag):
    field = elem.find(f"./{tag}")
    if field is None:
        return None
    return field.text.strip().replace("\n", " ")


def _get_meta_info_for_pmc_article(article_elem) -> PmcMeta:
    # Attempt to extract the PubMed ID, PubMed Central ID and DOI
    id_map = {}
    article_id = article_elem.findall("./front/article-meta/article-id") + article_elem.findall(
        "./front-stub/article-id"
    )
    for a in article_id:
        if not a.text or "pub-id-type" not in a.attrib:
            continue
        pub_id_type = a.attrib["pub-id-type"]
        if pub_id_type == "pmc":
            pub_id_type = "pmcid"
        id_map[pub_id_type] = a.text.strip().replace("\n", " ")

    pmid_text = id_map.get("pmid", "")
    pmcid_text = id_map.get("pmcid", "")
    doi_text = id_map.get("doi", "")

    # Attempt to get the publication date, preferring whichever pub-date element is most complete
    pubdates = article_elem.findall("./front/article-meta/pub-date") + article_elem.findall(
        "./front-stub/pub-date"
    )
    pub_year, pub_month, pub_day = None, None, None
    if pubdates:
        most_complete, completeness = None, 0
        for pubdate in pubdates:
            year_value = _field_text(pubdate, "year")
            if year_value is not None:
                pub_year = year_value

            season_value = _field_text(pubdate, "season")
            if season_value is not None:
                month_search = [c for c in _MONTH_NAME_TO_NUMBER if c and c in season_value]
                if month_search:
                    pub_month = _MONTH_NAME_TO_NUMBER[month_search[0]]

            month_value = _field_text(pubdate, "month")
            if month_value is not None:
                pub_month = month_value

            day_value = _field_text(pubdate, "day")
            if day_value is not None:
                pub_day = day_value

            this_completeness = sum(x is not None for x in [pub_year, pub_month, pub_day])
            if this_completeness > completeness:
                most_complete = pub_year, pub_month, pub_day
                completeness = this_completeness
        pub_year, pub_month, pub_day = most_complete

    journal = (
        article_elem.findall("./front/journal-meta/journal-title")
        + article_elem.findall("./front/journal-meta/journal-title-group/journal-title")
        + article_elem.findall("./front-stub/journal-title-group/journal-title")
    )
    assert len(journal) <= 1
    journal_text = " ".join(_extract_pmc_passages(journal, set()))

    journal_iso_text = ""
    journal_iso = article_elem.findall("./front/journal-meta/journal-id") + article_elem.findall(
        "./front-stub/journal-id"
    )
    for field in journal_iso:
        if field.attrib.get("journal-id-type") == "iso-abbrev":
            journal_iso_text = field.text

    return PmcMeta(
        {
            "pmid": pmid_text,
            "pmcid": pmcid_text,
            "doi": doi_text,
            "pub_year": pub_year,
            "pub_month": pub_month,
            "pub_day": pub_day,
            "journal": journal_text,
            "journal_iso": journal_iso_text,
        }
    )


def _apply_pmc_xlink_fix(source: Union[str, TextIO]) -> TextIO:
    """
    Hacky fix to add the xlink namespace to the article document if it uses it and has not defined it.
    A small number of PMC documents need this for the XML parser to successfully load it.
    """
    if isinstance(source, str):
        with open(source, encoding='utf-8') as f:
            content = f.read()
    else:
        content = source.read()

    if 'xlink' in content:
        article_tag = re.search(r'<article.*?>', content).group()
        if 'xmlns:xlink=' not in article_tag:
            new_article_tag = article_tag.replace(
                '<article ', '<article xmlns:xlink="http://www.w3.org/1999/xlink" ', 1
            )
            content = content.replace(article_tag, new_article_tag, 1)

    return io.StringIO(content)


def parse_pmcxml(
    source: Union[str, TextIO],
    keep_tags=PMC_KEEP_TAGS,
) -> Iterable[PMCArticle]:
    """
    Parse a PMC XML file into a series of PMCArticle dicts (one per article/sub-article).

    Args:
        source: The text or file handle containing the PMC XML
        keep_tags: tags whose markup is preserved inline in each passage's text (e.g. "sup",
            "italic") - pass an empty set for plain text with no markup.
    """
    source = _apply_pmc_xlink_fix(source)

    # Skip to the article element in the file
    for event, elem in etree.iterparse(source, events=("start", "end", "start-ns", "end-ns")):
        if event == "end" and elem.tag == "article":
            meta = _get_meta_info_for_pmc_article(elem)

            # We're going to process the main article along with any subarticles
            # And if any of the subarticles have distinguishing IDs (e.g. PMID), then
            # that'll be used, otherwise the parent article's metadata will be used
            subarticles = [elem] + elem.findall("./sub-article")

            for article_elem in subarticles:
                if article_elem is elem:
                    # This is the main parent article. Just use its metadata
                    sub_meta = meta
                else:
                    # Check if this subarticle has any distinguishing IDs and use them instead
                    sub_meta = _get_meta_info_for_pmc_article(article_elem)
                    if not (sub_meta["pmid"] or sub_meta["pmcid"] or sub_meta["doi"]):
                        sub_meta["pmid"] = meta["pmid"]
                        sub_meta["pmcid"] = meta["pmcid"]
                        sub_meta["doi"] = meta["doi"]
                    if sub_meta["pub_year"] is None:
                        sub_meta["pub_year"] = meta["pub_year"]
                        sub_meta["pub_month"] = meta["pub_month"]
                        sub_meta["pub_day"] = meta["pub_day"]
                    if not sub_meta["journal"]:
                        sub_meta["journal"] = meta["journal"]
                        sub_meta["journal_iso"] = meta["journal_iso"]

                text_sources = _extract_article_content(article_elem, keep_tags)

                yield PMCArticle({**sub_meta, "text_sources": text_sources})

            # Less important here (compared to abstracts) as each article file is not too big
            elem.clear()


def pmcxml2bioc(
    source: Union[str, TextIO],
) -> Iterator[Iterable[bioc.BioCDocument]]:
    """
    Convert a PMC XML file into its Bioc equivalent

    Args:
        source: The text or file handle containing the PMC XML

    Raises:
        RuntimeError: On any parsing errors

    Returns:
        An iterator over the newly generated Bioc documents
    """
    try:
        for pmc_doc in parse_pmcxml(source, keep_tags=set()):
            bioc_doc = bioc.BioCDocument()
            bioc_doc.id = pmc_doc["pmid"]
            bioc_doc.infons["title"] = " ".join(
                p["text"] for p in pmc_doc["text_sources"]["title"]
            )
            bioc_doc.infons["pmid"] = pmc_doc["pmid"]
            bioc_doc.infons["pmcid"] = pmc_doc["pmcid"]
            bioc_doc.infons["doi"] = pmc_doc["doi"]
            bioc_doc.infons["year"] = pmc_doc["pub_year"]
            bioc_doc.infons["month"] = pmc_doc["pub_month"]
            bioc_doc.infons["day"] = pmc_doc["pub_day"]
            bioc_doc.infons["journal"] = pmc_doc["journal"]
            bioc_doc.infons["journal_iso"] = pmc_doc["journal_iso"]

            offset = 0
            for group_name, text_source_group in pmc_doc["text_sources"].items():
                for passage_dict in text_source_group:
                    text_source = passage_dict["text"]

                    passage = bioc.BioCPassage()

                    passage.infons["section"] = group_name
                    passage.infons["subsection"] = passage_dict["subsection"]

                    passage.text = text_source
                    passage.offset = offset

                    offset += len(text_source)
                    bioc_doc.add_passage(passage)

            yield bioc_doc

    except etree.ParseError:
        raise RuntimeError("Parsing error in PMC xml file: %s" % source)
