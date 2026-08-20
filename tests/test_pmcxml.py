from io import StringIO

import pytest

from bioconverters.main import docs2bioc

from .util import fetch_xml


@pytest.fixture(scope='module')
def table_article():
    article = fetch_xml('PMC3203921', 'pmc')  # has a table to be processed in it
    return article


@pytest.fixture(scope='module')
def formula_article():
    article = fetch_xml('PMC2939780', 'pmc')
    return article


@pytest.fixture(scope='module')
def citation_offset_article():
    article = fetch_xml('PMC8466798', 'pmc')
    return article


def test_convert_pmc_with_table_drops_table_content(table_article):
    file = StringIO(table_article)
    all_passages = []
    for doc in docs2bioc(file, 'pmcxml', trim_sentences=False):
        all_passages.extend(doc.passages)
    all_text = " ".join(p.text for p in all_passages)
    # "ATP binding region" only appears inside the table body, which is now dropped entirely
    assert "ATP binding region" not in all_text


def test_citation_offset_article_parses(citation_offset_article):
    # Regression fixture for https://github.com/jakelever/biotext/issues/9 -
    # the offset-math bug it guarded against no longer applies since citation
    # marking was removed, but it's cheap insurance to confirm this real
    # article still parses without raising.
    file = StringIO(citation_offset_article)
    list(docs2bioc(file, 'pmcxml', trim_sentences=False))
