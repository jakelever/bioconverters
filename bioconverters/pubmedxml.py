import calendar
import html
import re
import xml.etree.ElementTree as etree
from typing import Iterable, Iterator, Optional, TextIO, Tuple, Union

import bioc

from .pubmed_constants import PUBMED_IGNORE_TAGS, PUBMED_KEEP_TAGS, PUBMED_SPLIT_TAGS
from .pubmed_types import (
    Chemical,
    MeshHeading,
    MeshQualifier,
    PublicationType,
    PubMedArticle,
    PubMedMeta,
    SupplementaryMeshConcept,
)
from .utils import (
    _extract_passages,
    _remove_brackets_from_titles,
    _remove_brackets_without_words,
)

_DateTuple = Tuple[Optional[int], Optional[int], Optional[int]]

_MONTH_NAME_TO_NUMBER = {m: i for i, m in enumerate(calendar.month_name)}
_MONTH_NAME_TO_NUMBER.update({m: i for i, m in enumerate(calendar.month_abbr)})


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
    if medline_date_field is not None and medline_date_field.text:
        medline_date_text = medline_date_field.text
        regex_search = re.search(year_regex, medline_date_text)
        if regex_search:
            pub_year = regex_search.group()
        month_search = [c for c in _MONTH_NAME_TO_NUMBER if c and c in medline_date_text]
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
        if (
            pub_date_field_year is None
            or pub_date_field_month is None
            or pub_date_field_day is None
            or pub_date_field_year.text is None
            or pub_date_field_month.text is None
            or pub_date_field_day.text is None
        ):
            # Skip malformed/incomplete PubMedPubDate entries rather than crashing
            continue
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


def parse_pubmedxml(
    source: Union[str, TextIO],
    return_xml: bool = False,
    keep_tags=set(),
    clear_empty_brackets: bool = True,
    fix_exponentials: bool = True,
) -> Iterable[PubMedArticle]:
    """
    Args:
        source: path to the MEDLINE xml file
        return_xml: return the title/abstract text as a marked-up XML string if True, or as
            plain, unescaped text with any markup stripped if False (default).
        keep_tags: with return_xml=True, tags whose markup is preserved inline (e.g. "i",
            "b", "sup") - has no effect when return_xml=False. Defaults to an empty set (no
            markup kept). Pass `pubmed_constants.PUBMED_KEEP_TAGS` for the common formatting
            tags (i, b, u, sup, sub).
        clear_empty_brackets: remove any "(...)"/"[...]"/"{...}" left containing no word
            characters.
        fix_exponentials: recover a digit-preceded numeric `<sup>` as "^N" instead of losing
            it to plain concatenation, e.g. `"10<sup>8</sup>"` -> "10^8". Same default as
            pubmedxml2txt/pubmedxml2bioc. Requires "sup" to be preserved, which happens
            automatically regardless of keep_tags.
    """
    effective_keep_tags = keep_tags | {"sup"} if fix_exponentials else keep_tags
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
            chemical_elems = elem.findall("./MedlineCitation/ChemicalList/Chemical")
            for chemical_elem in chemical_elems:
                substance_elem = chemical_elem.find("./NameOfSubstance")
                chemicals.append(
                    Chemical(
                        ui=substance_elem.attrib["UI"],
                        name=substance_elem.text,
                        registry_number=chemical_elem.find("./RegistryNumber").text,
                    )
                )

            mesh_headings = []
            mesh_elems = elem.findall("./MedlineCitation/MeshHeadingList/MeshHeading")
            for mesh_elem in mesh_elems:
                descriptor_elem = mesh_elem.find("./DescriptorName")
                qualifiers = [
                    MeshQualifier(
                        ui=qualifier_elem.attrib["UI"],
                        name=qualifier_elem.text,
                        major_topic=qualifier_elem.attrib["MajorTopicYN"] == "Y",
                    )
                    for qualifier_elem in mesh_elem.findall("./QualifierName")
                ]
                mesh_headings.append(
                    MeshHeading(
                        ui=descriptor_elem.attrib["UI"],
                        name=descriptor_elem.text,
                        major_topic=descriptor_elem.attrib["MajorTopicYN"] == "Y",
                        qualifiers=qualifiers,
                    )
                )

            supplementary_concepts = [
                SupplementaryMeshConcept(
                    ui=concept_elem.attrib["UI"],
                    type=concept_elem.attrib["Type"],
                    name=concept_elem.text,
                )
                for concept_elem in elem.findall("./MedlineCitation/SupplMeshList/SupplMeshName")
            ]

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
            publication_types = [
                PublicationType(ui=e.attrib["UI"], name=e.text)
                for e in pub_type_elems
                if e.text not in _pub_type_skips
            ]

            # Extract the title of paper - the DTD requires exactly one ArticleTitle per Article
            title = elem.findall("./MedlineCitation/Article/ArticleTitle")
            assert len(title) == 1, "Expected exactly one ArticleTitle for PMID=%s" % pmid
            title_passages = _extract_passages(
                title,
                PUBMED_IGNORE_TAGS,
                PUBMED_SPLIT_TAGS,
                effective_keep_tags,
                return_xml=return_xml,
                trim_buggy_sentences=True,
                fix_exponentials=fix_exponentials,
            )
            title_text = _remove_brackets_from_titles(title_passages[0])
            if not return_xml:
                # html.unescape catches named entities (e.g. &alpha;) that XML unescaping
                # alone doesn't - only safe on plain text, since unescaping "&amp;" etc. back
                # to "&" inside return_xml=True's own markup would corrupt it
                title_text = html.unescape(title_text)
            if clear_empty_brackets:
                title_text = _remove_brackets_without_words(title_text)

            # Extract the abstract from the paper
            abstract = elem.findall("./MedlineCitation/Article/Abstract/AbstractText")
            abstract_passages = _extract_passages(
                abstract,
                PUBMED_IGNORE_TAGS,
                PUBMED_SPLIT_TAGS,
                effective_keep_tags,
                return_xml=return_xml,
                trim_buggy_sentences=True,
                fix_exponentials=fix_exponentials,
            )
            abstract_text = (
                abstract_passages if return_xml else [html.unescape(t) for t in abstract_passages]
            )
            if clear_empty_brackets:
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
                pmid=pmid,
                pmcid=pmcid,
                doi=doi,
                pub_year=pub_year,
                pub_month=pub_month,
                pub_day=pub_day,
                title=title_text,
                abstract=abstract_text,
                journal=journal_title,
                journal_iso=journal_iso_title,
                authors=authors,
                chemicals=chemicals,
                mesh_headings=mesh_headings,
                supplementary_mesh=supplementary_concepts,
                publication_types=publication_types,
            )

            # Important: clear the current element from memory to keep memory usage low
            elem.clear()


def _format_chemical_for_infons(chemical: Chemical) -> str:
    return "%s|%s|%s" % (chemical.ui, chemical.registry_number, chemical.name)


def _format_mesh_heading_for_infons(heading: MeshHeading) -> str:
    parts = ["Descriptor|%s|%s|%s" % (heading.ui, "Y" if heading.major_topic else "N", heading.name)]
    parts += [
        "Qualifier|%s|%s|%s" % (q.ui, "Y" if q.major_topic else "N", q.name) for q in heading.qualifiers
    ]
    return "~".join(parts)


def _format_supplementary_mesh_for_infons(concept: SupplementaryMeshConcept) -> str:
    return "%s|%s|%s" % (concept.ui, concept.type, concept.name)


def _format_publication_type_for_infons(pub_type: PublicationType) -> str:
    return "%s|%s" % (pub_type.ui, pub_type.name)


def pubmedxml2bioc(
    source: Union[str, TextIO],
    sections: Iterable[str] = ("title", "abstract"),
    clear_empty_brackets: bool = True,
    fix_exponentials: bool = True,
) -> Iterable[bioc.BioCDocument]:
    """
    Args:
        source: path to the MEDLINE xml file
        sections: which of "title"/"abstract" to include, and in what order.
        clear_empty_brackets: see parse_pubmedxml.
        fix_exponentials: see parse_pubmedxml.
    """
    for pm_doc in parse_pubmedxml(
        source, clear_empty_brackets=clear_empty_brackets, fix_exponentials=fix_exponentials
    ):
        bioc_doc = bioc.BioCDocument()
        bioc_doc.id = pm_doc.pmid
        bioc_doc.infons["title"] = pm_doc.title
        bioc_doc.infons["pmid"] = pm_doc.pmid
        bioc_doc.infons["pmcid"] = pm_doc.pmcid
        bioc_doc.infons["doi"] = pm_doc.doi
        bioc_doc.infons["year"] = pm_doc.pub_year
        bioc_doc.infons["month"] = pm_doc.pub_month
        bioc_doc.infons["day"] = pm_doc.pub_day
        bioc_doc.infons["journal"] = pm_doc.journal
        bioc_doc.infons["journal_iso"] = pm_doc.journal_iso
        bioc_doc.infons["authors"] = ", ".join(pm_doc.authors)
        bioc_doc.infons["chemicals"] = "\t".join(_format_chemical_for_infons(c) for c in pm_doc.chemicals)
        bioc_doc.infons["mesh_headings"] = "\t".join(
            _format_mesh_heading_for_infons(h) for h in pm_doc.mesh_headings
        )
        bioc_doc.infons["supplementary_mesh"] = "\t".join(
            _format_supplementary_mesh_for_infons(s) for s in pm_doc.supplementary_mesh
        )
        bioc_doc.infons["publication_types"] = "\t".join(
            _format_publication_type_for_infons(p) for p in pm_doc.publication_types
        )

        offset = 0
        for section in sections:
            value = getattr(pm_doc, section)
            texts = (value,) if isinstance(value, str) else value
            for text_source in texts:
                if not text_source:
                    continue
                passage = bioc.BioCPassage()
                passage.infons["section"] = section
                passage.text = text_source
                passage.offset = offset
                offset += len(text_source)
                bioc_doc.add_passage(passage)

        yield bioc_doc


def _pubmed_article_meta(pm_doc: PubMedArticle) -> PubMedMeta:
    """Slice a PubMedArticle down to just its metadata fields (no title/abstract)."""
    return PubMedMeta(
        pmid=pm_doc.pmid,
        pmcid=pm_doc.pmcid,
        doi=pm_doc.doi,
        pub_year=pm_doc.pub_year,
        pub_month=pm_doc.pub_month,
        pub_day=pm_doc.pub_day,
        journal=pm_doc.journal,
        journal_iso=pm_doc.journal_iso,
        authors=pm_doc.authors,
        chemicals=pm_doc.chemicals,
        mesh_headings=pm_doc.mesh_headings,
        supplementary_mesh=pm_doc.supplementary_mesh,
        publication_types=pm_doc.publication_types,
    )


def pubmedxml2txt(
    source: Union[str, TextIO],
    sections: Iterable[str] = ("title", "abstract"),
    passage_separator: str = "\n\n",
    clear_empty_brackets: bool = True,
    fix_exponentials: bool = True,
) -> Iterator[Tuple[PubMedMeta, str]]:
    """
    Convert a MEDLINE XML file into plain text, one (metadata, text) pair per article.

    Args:
        source: path to the MEDLINE xml file
        sections: which of "title"/"abstract" to include, and in what order.
        passage_separator: string used to join the extracted passages into the single
            returned text string.
        clear_empty_brackets: see parse_pubmedxml.
        fix_exponentials: see parse_pubmedxml.

    Returns:
        An iterator over one (PubMedMeta, text) pair per article
    """
    for pm_doc in parse_pubmedxml(
        source, clear_empty_brackets=clear_empty_brackets, fix_exponentials=fix_exponentials
    ):
        text = passage_separator.join(pm_doc.iter_text(sections))
        yield _pubmed_article_meta(pm_doc), text


def pubmedxml2tagged(
    source: Union[str, TextIO],
    sections: Iterable[str] = ("title", "abstract"),
    passage_separator: str = "\n\n",
    keep_tags=PUBMED_KEEP_TAGS,
    clear_empty_brackets: bool = True,
    fix_exponentials: bool = True,
) -> Iterator[Tuple[PubMedMeta, str]]:
    """
    Convert a MEDLINE XML file into marked-up text, one (metadata, text) pair per article, with
    formatting tags (e.g. `<i>`, `<sup>`) kept inline instead of stripped. A thin wrapper around
    parse_pubmedxml with return_xml=True and keep_tags defaulted to PUBMED_KEEP_TAGS.

    Args:
        source: path to the MEDLINE xml file
        sections: which of "title"/"abstract" to include, and in what order.
        passage_separator: string used to join the extracted passages into the single
            returned text string.
        keep_tags: see parse_pubmedxml. Defaults to `pubmed_constants.PUBMED_KEEP_TAGS`.
        clear_empty_brackets: see parse_pubmedxml.
        fix_exponentials: see parse_pubmedxml.

    Returns:
        An iterator over one (PubMedMeta, marked-up text) pair per article
    """
    for pm_doc in parse_pubmedxml(
        source,
        return_xml=True,
        keep_tags=keep_tags,
        clear_empty_brackets=clear_empty_brackets,
        fix_exponentials=fix_exponentials,
    ):
        text = passage_separator.join(pm_doc.iter_text(sections))
        yield _pubmed_article_meta(pm_doc), text
