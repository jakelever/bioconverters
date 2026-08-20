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

    # single-rid citation gets retagged to <citation> with its pmid/doi attributes
    assert 'pmid="111"' in text
    assert 'doi="10.1/one"' in text
    assert '>1</citation>' in text

    # multi-rid (grouped) citation merges values from each referenced ref, "|"-joined
    assert 'pmid="222|333"' in text
    assert '>2,3</citation>' in text

    # non-bibr xrefs (e.g. figure references) are unaffected by citation injection - they
    # stay plain "xref" (never retagged to <citation>), and their text content (e.g. "Figure
    # 1") now survives as readable plain text since xref is no longer blanket-ignored
    assert 'ref-type="fig"' not in text
    assert 'Figure 1' in text

    # xref never survives as such - either retagged to <citation> or dropped
    assert '<xref' not in text


def test_inject_citations_false_drops_citations_like_before():
    docs = list(parse_pmcxml(StringIO(_CITATION_XML), inject_citations=False))
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    assert '<xref' not in text
    assert '<citation' not in text
    assert 'pmid=' not in text


def test_inject_citations_has_no_effect_on_pmcxml2bioc():
    # pmcxml2bioc explicitly disables citation injection, so its plain-text output is
    # unaffected regardless of what inject_citations would otherwise do
    docs = list(pmcxml2bioc(StringIO(_CITATION_XML)))
    text = ' '.join(p.text for doc in docs for p in doc.passages)
    assert '<xref' not in text
    assert '<citation' not in text
    assert 'pmid=' not in text


_SUBARTICLE_CITATION_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>Main finding.</p></body>
    <back><ref-list>
        <ref id="r1"><element-citation><pub-id pub-id-type="pmid">111</pub-id></element-citation></ref>
    </ref-list></back>
    <sub-article>
        <front-stub><article-id pub-id-type="pmid">2</article-id></front-stub>
        <body><p>Sub-article finding <xref ref-type="bibr" rid="r1">1</xref>.</p></body>
    </sub-article>
</article>'''


def test_inject_citations_resolves_against_parent_ref_list_for_subarticles():
    # sub-articles typically don't carry their own <ref-list> and cite the parent's -
    # injection runs once on the whole document, so this should still resolve correctly
    docs = list(parse_pmcxml(StringIO(_SUBARTICLE_CITATION_XML)))
    assert len(docs) == 2
    sub_doc = docs[1]
    assert sub_doc['pmid'] == '2'
    text = ' '.join(p['text'] for p in sub_doc['text_sources']['article'])
    assert 'pmid="111"' in text
    assert '>1</citation>' in text


_PARENTHETICAL_XREF_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>Expression levels are shown in (<xref ref-type="fig" rid="f1">Table 3</xref>) below. See Table 3, third row, for details.</p></body>
</article>'''


def test_clean_xrefs_in_parentheses_default_drops_standalone_reference():
    docs = list(parse_pmcxml(StringIO(_PARENTHETICAL_XREF_XML), inject_citations=False))
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    assert 'shown in below' in text
    assert 'third row' in text  # unrelated plain-text mention still survives


def test_clean_xrefs_in_parentheses_false_keeps_dangling_reference():
    docs = list(
        parse_pmcxml(
            StringIO(_PARENTHETICAL_XREF_XML),
            inject_citations=False,
            clean_xrefs_in_parentheses=False,
        )
    )
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    assert 'shown in (Table 3) below' in text
