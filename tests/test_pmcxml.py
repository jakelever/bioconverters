from io import StringIO

import pytest

from bioconverters import parse_pmcxml, pmcxml2bioc

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
    for doc in pmcxml2bioc(file):
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
    list(pmcxml2bioc(file))


_CITATION_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>Some finding <xref ref-type="bibr" rid="r1">1</xref> and another <xref ref-type="bibr" rid="r2 r3">2,3</xref>. See <xref ref-type="fig" rid="f1">Figure 1</xref>.</p></body>
    <back><ref-list>
        <ref id="r1"><element-citation><pub-id pub-id-type="pmid">111</pub-id><pub-id pub-id-type="doi">10.1/one</pub-id></element-citation></ref>
        <ref id="r2"><element-citation><pub-id pub-id-type="pmid">222</pub-id></element-citation></ref>
        <ref id="r3"><element-citation><pub-id pub-id-type="pmid">333</pub-id></element-citation></ref>
    </ref-list></back>
</article>'''


def test_inject_citations_adds_pmid_doi_attributes():
    docs = list(parse_pmcxml(StringIO(_CITATION_XML)))
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])

    # single-rid citation gets its pmid/doi attributes
    assert 'pmid="111"' in text
    assert 'doi="10.1/one"' in text
    assert '>1</xref>' in text

    # multi-rid (grouped) citation merges values from each referenced ref, "|"-joined
    assert 'pmid="222|333"' in text
    assert '>2,3</xref>' in text

    # non-bibr xrefs (e.g. figure references) are unaffected - still dropped as before
    assert 'ref-type="fig"' not in text
    assert 'Figure 1' not in text

    # the internal placeholder tag never leaks into output
    assert 'citation-ref' not in text


def test_inject_citations_false_drops_citations_like_before():
    docs = list(parse_pmcxml(StringIO(_CITATION_XML), inject_citations=False))
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    assert '<xref' not in text
    assert 'pmid=' not in text


def test_inject_citations_has_no_effect_on_pmcxml2bioc():
    # pmcxml2bioc explicitly disables citation injection, so its plain-text output is
    # unaffected regardless of what inject_citations would otherwise do
    docs = list(pmcxml2bioc(StringIO(_CITATION_XML)))
    text = ' '.join(p.text for doc in docs for p in doc.passages)
    assert '<xref' not in text
    assert 'pmid=' not in text
