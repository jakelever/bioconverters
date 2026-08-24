from dataclasses import dataclass
from typing import Iterable, Iterator, Optional, Union

_ALL_SECTIONS = ("title", "subtitle", "abstract", "article", "back", "floating")


@dataclass
class PMCArticle:
    """One PMC article or sub-article, as extracted by `parse_pmcxml`."""

    pmid: str
    """PubMed ID, or an empty string if not found."""

    pmcid: str
    """PubMed Central ID, or an empty string if not found."""

    doi: str
    """DOI, or an empty string if not found."""

    pub_year: Optional[str]
    """Publication year, or None if not found."""

    pub_month: Optional[Union[str, int]]
    """Publication month, or None if not found."""

    pub_day: Optional[str]
    """Publication day, or None if not found."""

    journal: str
    """Journal title, or an empty string if not found."""

    journal_iso: str
    """ISO abbreviation of the journal title, or an empty string if not found."""

    title: str
    """Article title, or an empty string if not found."""

    subtitle: str
    """Article subtitle, or an empty string if not present."""

    abstract: Iterable[str]
    """Abstract passages."""

    article: Iterable[str]
    """Body text passages, extracted from the article's `<body>` element."""

    back: Iterable[str]
    """Back-matter text passages (e.g. appendices), extracted from the article's `<back>` element."""

    floating: Iterable[str]
    """Text passages from blocks outside the main flow (e.g. figure/table captions),
    extracted from the article's `<floats-group>` element."""

    def iter_text(self, sections: Iterable[str] = _ALL_SECTIONS) -> Iterator[str]:
        """
        Yield each non-empty passage of text from the given fields, in order.

        Args:
            sections: which of the six text fields to pull text from, and in what order.
                Defaults to all six ("title", "subtitle", "abstract", "article", "back",
                "floating").
        """
        for section in sections:
            value = getattr(self, section)
            texts = (value,) if isinstance(value, str) else value
            for text in texts:
                if text:
                    yield text
