from dataclasses import dataclass
from typing import Iterable, Iterator, Optional


@dataclass
class Chemical:
    """One `<Chemical>` entry from the article's ChemicalList."""

    ui: str
    """MeSH substance ID (e.g. "D000068877")."""

    name: str
    """Substance name."""

    registry_number: str
    """CAS registry number, or "0" if none is assigned."""


@dataclass
class MeshQualifier:
    """One `<QualifierName>` attached to a MeSH heading's descriptor."""

    ui: str
    """MeSH qualifier ID (e.g. "Q000378")."""

    name: str
    """Qualifier name (e.g. "genetics")."""

    major_topic: bool
    """Whether this qualifier is a major topic of the article (MajorTopicYN="Y")."""


@dataclass
class MeshHeading:
    """One `<MeshHeading>` entry: a descriptor plus any qualifiers refining it."""

    ui: str
    """MeSH descriptor ID (e.g. "D009369")."""

    name: str
    """Descriptor name (e.g. "Neoplasms")."""

    major_topic: bool
    """Whether the descriptor itself is a major topic (MajorTopicYN="Y")."""

    qualifiers: Iterable[MeshQualifier]
    """Qualifiers refining this descriptor, in document order."""


@dataclass
class SupplementaryMeshConcept:
    """One `<SupplMeshName>` entry from the article's SupplMeshList."""

    ui: str
    """Supplementary concept ID (e.g. "C000657245")."""

    type: str
    """One of "Disease", "Protocol", "Organism", "Anatomy", "Population" (DTD-enumerated)."""

    name: str
    """Concept name."""


@dataclass
class PublicationType:
    """One `<PublicationType>` entry from the article's PublicationTypeList."""

    ui: str
    """MeSH publication-type ID (e.g. "D016428")."""

    name: str
    """Publication type name (e.g. "Journal Article")."""


@dataclass
class PubMedMeta:
    """Metadata for a MEDLINE/PubMed article - the text-free subset of `PubMedArticle`'s
    fields (everything but title/abstract), as returned alongside the text by
    `pubmedxml2txt`/`pubmedxml2tagged`."""

    pmid: str
    """PubMed ID."""

    pmcid: Optional[str]
    """PubMed Central ID, or None if not linked."""

    doi: Optional[str]
    """DOI, or None if not found."""

    pub_year: Optional[int]
    """Publication year, or None if not found."""

    pub_month: Optional[int]
    """Publication month, or None if not found."""

    pub_day: Optional[int]
    """Publication day, or None if not found."""

    journal: str
    """Journal title, or an empty string if not found."""

    journal_iso: str
    """ISO abbreviation of the journal title, or an empty string if not found."""

    authors: Iterable[str]
    """Author names, in document order."""

    chemicals: Iterable[Chemical]
    """Chemical substances, in document order."""

    mesh_headings: Iterable[MeshHeading]
    """MeSH headings, each with its own qualifiers nested inside, in document order."""

    supplementary_mesh: Iterable[SupplementaryMeshConcept]
    """Supplementary MeSH concepts, in document order."""

    publication_types: Iterable[PublicationType]
    """Publication types, in document order (excludes generic NLM support-type labels
    like "Research Support, N.I.H., Extramural")."""


@dataclass
class PubMedArticle:
    """One MEDLINE/PubMed article, as extracted by `parse_pubmedxml`."""

    pmid: str
    """PubMed ID."""

    pmcid: Optional[str]
    """PubMed Central ID, or None if not linked."""

    doi: Optional[str]
    """DOI, or None if not found."""

    pub_year: Optional[int]
    """Publication year, or None if not found."""

    pub_month: Optional[int]
    """Publication month, or None if not found."""

    pub_day: Optional[int]
    """Publication day, or None if not found."""

    title: str
    """Article title."""

    abstract: Iterable[str]
    """Abstract passages, one per `<AbstractText>` element."""

    journal: str
    """Journal title, or an empty string if not found."""

    journal_iso: str
    """ISO abbreviation of the journal title, or an empty string if not found."""

    authors: Iterable[str]
    """Author names, in document order."""

    chemicals: Iterable[Chemical]
    """Chemical substances, in document order."""

    mesh_headings: Iterable[MeshHeading]
    """MeSH headings, each with its own qualifiers nested inside, in document order."""

    supplementary_mesh: Iterable[SupplementaryMeshConcept]
    """Supplementary MeSH concepts, in document order."""

    publication_types: Iterable[PublicationType]
    """Publication types, in document order (excludes generic NLM support-type labels
    like "Research Support, N.I.H., Extramural")."""

    def iter_text(self, sections: Iterable[str] = ("title", "abstract")) -> Iterator[str]:
        """
        Yield each non-empty passage of text from the given fields, in order.

        Args:
            sections: which fields to pull text from, and in what order. Defaults to
                ("title", "abstract").
        """
        for section in sections:
            value = getattr(self, section)
            texts = (value,) if isinstance(value, str) else value
            for text in texts:
                if text:
                    yield text
