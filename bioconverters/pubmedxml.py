import calendar
import html
import re
import xml.etree.ElementTree as etree
from typing import Iterable, Iterator, Optional, TextIO, Tuple, Union

try:
    # python 3.8+
    from typing import TypedDict  # type: ignore
except ImportError:
    from typing_extensions import TypedDict

import bioc

from .pubmed_constants import PUBMED_IGNORE_TAGS, PUBMED_KEEP_TAGS, PUBMED_SPLIT_TAGS
from .utils import (
    _extract_passages,
    _format_metadata_header,
    _remove_brackets_from_titles,
    _remove_brackets_without_words,
)

_DateTuple = Tuple[Optional[int], Optional[int], Optional[int]]

_MONTH_NAME_TO_NUMBER = {m: i for i, m in enumerate(calendar.month_name)}
_MONTH_NAME_TO_NUMBER.update({m: i for i, m in enumerate(calendar.month_abbr)})


class PubMedArticle(TypedDict):
    pmid: str
    pmcid: str
    doi: str
    pub_year: Optional[int]
    pub_month: Optional[int]
    pub_day: Optional[int]
    title: Iterable[str]
    abstract: str
    journal: str
    journal_iso: str
    authors: Iterable[str]
    chemicals: str
    mesh_headings: str
    supplementary_mesh: str
    publication_types: str


def _get_journal_date_for_medline_file(elem: etree.Element, pmid: Union[str, int]) -> _DateTuple:
    """
    Scrapes the Journal Date from the Medline XML element tree.

    Args:
        elem: XML element to be scraped/parsed
        pmid: Pubmed ID of the article, only used for reporting errors
    """
    year_regex = re.compile(r"(18|19|20)\d\d")

    # Try to extract the publication date
    pub_date_field = elem.find("./MedlineCitation/Article/Journal/JournalIssue/PubDate")
    assert pub_date_field is not None, "Couldn't find PubDate field for PMID=%s" % pmid

    medline_date_field = pub_date_field.find("./MedlineDate")
    pub_date_field_year = pub_date_field.find("./Year")
    pub_date_field_month = pub_date_field.find("./Month")
    pub_date_field_day = pub_date_field.find("./Day")

    pub_year, pub_month, pub_day = None, None, None
    if medline_date_field is not None:
        regex_search = re.search(year_regex, medline_date_field.text)
        if regex_search:
            pub_year = regex_search.group()
        month_search = [c for c in _MONTH_NAME_TO_NUMBER if c and c in medline_date_field.text]
        if len(month_search) > 0:
            pub_month = month_search[0]
    else:
        if pub_date_field_year is not None:
            pub_year = pub_date_field_year.text
        if pub_date_field_month is not None:
            pub_month = pub_date_field_month.text
        if pub_date_field_day is not None:
            pub_day = pub_date_field_day.text

    if pub_year is not None:
        pub_year = int(pub_year)
        if not (pub_year > 1700 and pub_year < 2100):
            pub_year = None

    if pub_month is not None:
        if pub_month in _MONTH_NAME_TO_NUMBER:
            pub_month = _MONTH_NAME_TO_NUMBER[pub_month]  # type: ignore
        pub_month = int(pub_month)
    if pub_day is not None:
        pub_day = int(pub_day)

    return pub_year, pub_month, pub_day


def _get_pubmed_entry_date(elem: etree.Element) -> _DateTuple:
    pub_date_fields = elem.findall("./PubmedData/History/PubMedPubDate")
    all_dates = {}
    for pub_date_field in pub_date_fields:
        assert "PubStatus" in pub_date_field.attrib
        pub_date_field_year = pub_date_field.find("./Year")
        pub_date_field_month = pub_date_field.find("./Month")
        pub_date_field_day = pub_date_field.find("./Day")
        pub_year = int(pub_date_field_year.text)
        pub_month = int(pub_date_field_month.text)
        pub_day = int(pub_date_field_day.text)

        date_type = pub_date_field.attrib["PubStatus"]
        if pub_year > 1700 and pub_year < 2100:
            all_dates[date_type] = (pub_year, pub_month, pub_day)

    if len(all_dates) == 0:
        return None, None, None

    if "pubmed" in all_dates:
        pub_year, pub_month, pub_day = all_dates["pubmed"]
    elif "entrez" in all_dates:
        pub_year, pub_month, pub_day = all_dates["entrez"]
    elif "medline" in all_dates:
        pub_year, pub_month, pub_day = all_dates["medline"]
    else:
        pub_year, pub_month, pub_day = list(all_dates.values())[0]

    return pub_year, pub_month, pub_day


_pub_type_skips = {
    "Research Support, N.I.H., Intramural",
    "Research Support, Non-U.S. Gov't",
    "Research Support, U.S. Gov't, P.H.S.",
    "Research Support, N.I.H., Extramural",
    "Research Support, U.S. Gov't, Non-P.H.S.",
    "English Abstract",
}
_doi_regex = re.compile(r"^[0-9\.]+\/.+[^\/]$")


def _format_mesh_field(prefix: str, mesh_id: str, major_topic_yn: str, name: str) -> str:
    for value in (mesh_id, major_topic_yn, name):
        assert "|" not in value and "~" not in value, "Found delimiter in %s" % value
    return "%s|%s|%s|%s" % (prefix, mesh_id, major_topic_yn, name)


def parse_pubmedxml(
    source: Union[str, TextIO],
) -> Iterable[PubMedArticle]:
    """
    Args:
        source: path to the MEDLINE xml file
    """
    for event, elem in etree.iterparse(source, events=("start", "end", "start-ns", "end-ns")):
        if event == "end" and elem.tag == "PubmedArticle":  # MedlineCitation'):
            # Try to extract the pmid_id
            pmid_field = elem.find("./MedlineCitation/PMID")
            assert pmid_field is not None
            pmid = pmid_field.text

            journal_year, journal_month, journal_day = _get_journal_date_for_medline_file(elem, pmid)
            entry_year, entry_month, entry_day = _get_pubmed_entry_date(elem)

            j_comparison = tuple(
                9999 if d is None else d for d in [journal_year, journal_month, journal_day]
            )
            e_comparison = tuple(
                9999 if d is None else d for d in [entry_year, entry_month, entry_day]
            )
            if (
                j_comparison < e_comparison
            ):  # The PubMed entry has been delayed for some reason so let's try the journal data
                pub_year, pub_month, pub_day = journal_year, journal_month, journal_day
            else:
                pub_year, pub_month, pub_day = entry_year, entry_month, entry_day

            # Extract the authors
            author_elems = elem.findall("./MedlineCitation/Article/AuthorList/Author")
            authors = []
            for author_elem in author_elems:
                forename = author_elem.find("./ForeName")
                lastname = author_elem.find("./LastName")
                collectivename = author_elem.find("./CollectiveName")

                name = None
                if (
                    forename is not None
                    and lastname is not None
                    and forename.text is not None
                    and lastname.text is not None
                ):
                    name = "%s %s" % (forename.text, lastname.text)
                elif lastname is not None and lastname.text is not None:
                    name = lastname.text
                elif forename is not None and forename.text is not None:
                    name = forename.text
                elif collectivename is not None and collectivename.text is not None:
                    name = collectivename.text
                else:
                    raise RuntimeError("Unable to find authors in Pubmed citation (PMID=%s)" % pmid)
                authors.append(name)

            chemicals = []
            chemical_elems = elem.findall("./MedlineCitation/ChemicalList/Chemical/NameOfSubstance")
            for chemical_elem in chemical_elems:
                chem_id = chemical_elem.attrib["UI"]
                name = chemical_elem.text
                chemicals.append("%s|%s" % (chem_id, name))
            chemicals_txt = "\t".join(chemicals)

            mesh_headings = []
            mesh_elems = elem.findall("./MedlineCitation/MeshHeadingList/MeshHeading")
            for mesh_elem in mesh_elems:
                descriptor_elem = mesh_elem.find("./DescriptorName")
                mesh_heading = _format_mesh_field(
                    "Descriptor",
                    descriptor_elem.attrib["UI"],
                    descriptor_elem.attrib["MajorTopicYN"],
                    descriptor_elem.text,
                )

                qualifier_elems = mesh_elem.findall("./QualifierName")
                for qualifier_elem in qualifier_elems:
                    mesh_heading += "~" + _format_mesh_field(
                        "Qualifier",
                        qualifier_elem.attrib["UI"],
                        qualifier_elem.attrib["MajorTopicYN"],
                        qualifier_elem.text,
                    )

                mesh_headings.append(mesh_heading)
            mesh_headings_txt = "\t".join(mesh_headings)

            supplementary_concepts = []
            concept_elems = elem.findall("./MedlineCitation/SupplMeshList/SupplMeshName")
            for concept_elem in concept_elems:
                concept_id = concept_elem.attrib["UI"]
                concept_type = concept_elem.attrib["Type"]
                concept_name = concept_elem.text
                supplementary_concepts.append("%s|%s|%s" % (concept_id, concept_type, concept_name))
            supplementary_concepts_txt = "\t".join(supplementary_concepts)

            doi_elems = elem.findall("./PubmedData/ArticleIdList/ArticleId[@IdType='doi']")
            dois = [
                doi_elem.text
                for doi_elem in doi_elems
                if doi_elem.text and _doi_regex.match(doi_elem.text)
            ]

            doi = None
            if dois:
                doi = dois[0]  # We'll just use DOI the first one provided

            pmc_elems = elem.findall("./PubmedData/ArticleIdList/ArticleId[@IdType='pmc']")
            assert len(pmc_elems) <= 1, "Found more than one PMCID with PMID: %s" % pmid
            pmcid = None
            if len(pmc_elems) == 1:
                pmcid = pmc_elems[0].text

            pub_type_elems = elem.findall(
                "./MedlineCitation/Article/PublicationTypeList/PublicationType"
            )
            pub_type = [e.text for e in pub_type_elems if e.text not in _pub_type_skips]
            pub_type_txt = "|".join(pub_type)

            # Extract the title of paper
            title = elem.findall("./MedlineCitation/Article/ArticleTitle")
            title_passages = _extract_passages(
                title,
                PUBMED_IGNORE_TAGS,
                PUBMED_SPLIT_TAGS,
                PUBMED_KEEP_TAGS,
                return_xml=False,
                trim_buggy_sentences=True,
            )
            title_text = [_remove_brackets_from_titles(t) for t in title_passages]
            title_text = [html.unescape(t) for t in title_text]
            title_text = [_remove_brackets_without_words(t) for t in title_text]

            # Extract the abstract from the paper
            abstract = elem.findall("./MedlineCitation/Article/Abstract/AbstractText")
            abstract_passages = _extract_passages(
                abstract,
                PUBMED_IGNORE_TAGS,
                PUBMED_SPLIT_TAGS,
                PUBMED_KEEP_TAGS,
                return_xml=False,
                trim_buggy_sentences=True,
            )
            abstract_text = [html.unescape(t) for t in abstract_passages]
            abstract_text = [_remove_brackets_without_words(t) for t in abstract_text]

            journal_title_fields = elem.findall("./MedlineCitation/Article/Journal/Title")
            journal_title_iso_fields = elem.findall(
                "./MedlineCitation/Article/Journal/ISOAbbreviation"
            )

            journal_title, journal_iso_title = "", ""
            assert len(journal_title_fields) <= 1, "Error with pmid=%s" % pmid
            assert len(journal_title_iso_fields) <= 1, "Error with pmid=%s" % pmid
            if journal_title_fields:
                journal_title = journal_title_fields[0].text
            if journal_title_iso_fields:
                journal_iso_title = journal_title_iso_fields[0].text

            yield PubMedArticle(
                {
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "doi": doi,
                    "pub_year": pub_year,
                    "pub_month": pub_month,
                    "pub_day": pub_day,
                    "title": title_text,
                    "abstract": abstract_text,
                    "journal": journal_title,
                    "journal_iso": journal_iso_title,
                    "authors": authors,
                    "chemicals": chemicals_txt,
                    "mesh_headings": mesh_headings_txt,
                    "supplementary_mesh": supplementary_concepts_txt,
                    "publication_types": pub_type_txt,
                }
            )

            # Important: clear the current element from memory to keep memory usage low
            elem.clear()


def pubmedxml2bioc(
    source: Union[str, TextIO],
) -> Iterable[bioc.BioCDocument]:
    """
    Args:
        source: path to the MEDLINE xml file
    """
    for pm_doc in parse_pubmedxml(source):
        bioc_doc = bioc.BioCDocument()
        bioc_doc.id = pm_doc["pmid"]
        bioc_doc.infons["title"] = " ".join(pm_doc["title"])
        bioc_doc.infons["pmid"] = pm_doc["pmid"]
        bioc_doc.infons["pmcid"] = pm_doc["pmcid"]
        bioc_doc.infons["doi"] = pm_doc["doi"]
        bioc_doc.infons["year"] = pm_doc["pub_year"]
        bioc_doc.infons["month"] = pm_doc["pub_month"]
        bioc_doc.infons["day"] = pm_doc["pub_day"]
        bioc_doc.infons["journal"] = pm_doc["journal"]
        bioc_doc.infons["journal_iso"] = pm_doc["journal_iso"]
        bioc_doc.infons["authors"] = ", ".join(pm_doc["authors"])
        bioc_doc.infons["chemicals"] = pm_doc["chemicals"]
        bioc_doc.infons["mesh_headings"] = pm_doc["mesh_headings"]
        bioc_doc.infons["supplementary_mesh"] = pm_doc["supplementary_mesh"]
        bioc_doc.infons["publication_types"] = pm_doc["publication_types"]

        offset = 0
        for section in ["title", "abstract"]:
            for text_source in pm_doc[section]:
                passage = bioc.BioCPassage()
                passage.infons["section"] = section
                passage.text = text_source
                passage.offset = offset
                offset += len(text_source)
                bioc_doc.add_passage(passage)

        yield bioc_doc


def pubmedxml2txt(
    source: Union[str, TextIO],
    sections: Iterable[str] = ("title", "abstract"),
    include_metadata: bool = False,
    passage_separator: str = "\n\n",
) -> Iterator[str]:
    """
    Convert a MEDLINE XML file into plain text, one string per article.

    Args:
        source: path to the MEDLINE xml file
        sections: which of "title"/"abstract" to include, and in what order.
        include_metadata: prepend a "label: value" header block (pmid, pmcid, doi, year,
            month, day, journal, authors) before the text, separated by passage_separator
            like any other passage. Fields that are empty/missing are omitted.
        passage_separator: string used to join the header (if any), and every extracted
            passage, into the single returned string.

    Returns:
        An iterator over one plain text string per article
    """
    for pm_doc in parse_pubmedxml(source):
        parts = []
        if include_metadata:
            header = _format_metadata_header(
                {
                    "pmid": pm_doc["pmid"],
                    "pmcid": pm_doc["pmcid"],
                    "doi": pm_doc["doi"],
                    "year": pm_doc["pub_year"],
                    "month": pm_doc["pub_month"],
                    "day": pm_doc["pub_day"],
                    "journal": pm_doc["journal"],
                    "authors": "; ".join(pm_doc["authors"]) if pm_doc["authors"] else None,
                }
            )
            if header:
                parts.append(header)

        for section in sections:
            for text_source in pm_doc[section]:
                if text_source:
                    parts.append(text_source)

        yield passage_separator.join(parts)
