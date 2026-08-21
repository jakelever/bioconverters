from io import StringIO

import pytest

from bioconverters import parse_pmcxml, pmcxml2bioc, pmcxml2txt
from bioconverters.pmcxml import _apply_pmc_xlink_fix

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

    # single-rid citation gets retagged to <citation> with its pmid/doi attributes, and a
    # count of 1
    assert 'pmid="111"' in text
    assert 'doi="10.1/one"' in text
    assert 'count="1"' in text
    assert '>1</citation>' in text

    # multi-rid (grouped) citation merges values from each referenced ref, "|"-joined, and
    # counts how many rids were bundled together
    assert 'pmid="222|333"' in text
    assert 'count="2"' in text
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


def test_clean_xrefs_in_brackets_default_false_keeps_dangling_reference():
    # parse_pmcxml defaults clean_xrefs_in_brackets to False (unlike pmcxml2txt)
    docs = list(parse_pmcxml(StringIO(_PARENTHETICAL_XREF_XML), inject_citations=False))
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    assert 'shown in (Table 3) below' in text


def test_clean_xrefs_in_brackets_true_drops_standalone_parenthetical_reference():
    docs = list(
        parse_pmcxml(
            StringIO(_PARENTHETICAL_XREF_XML),
            inject_citations=False,
            clean_xrefs_in_brackets=True,
        )
    )
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    assert 'shown in below' in text
    assert 'third row' in text  # unrelated plain-text mention still survives


_SQUARE_BRACKET_XREF_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>Results were reported previously <xref ref-type="fig" rid="f1">[1]</xref>. See Figure 1 for details.</p></body>
</article>'''


def test_clean_xrefs_in_brackets_true_drops_own_content_in_square_brackets():
    # the xref's own content "[1]" is dropped outright, regardless of surrounding context
    # (no parentheses needed, unlike the "(Table 1)" case)
    docs = list(
        parse_pmcxml(
            StringIO(_SQUARE_BRACKET_XREF_XML),
            inject_citations=False,
            clean_xrefs_in_brackets=True,
        )
    )
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    # collapsed whitespace leaves a single space where "[1]" used to be
    assert 'reported previously .' in text
    assert 'Figure 1' in text  # unrelated, unbracketed xref still survives


def test_clean_xrefs_in_brackets_false_keeps_own_content_in_square_brackets():
    docs = list(parse_pmcxml(StringIO(_SQUARE_BRACKET_XREF_XML), inject_citations=False))
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    assert 'reported previously [1].' in text


_TXT_XML = '''<article>
    <front><article-meta>
        <article-id pub-id-type="pmid">42</article-id>
        <article-id pub-id-type="pmc">PMC42</article-id>
        <title-group><article-title>A Great Title</article-title></title-group>
        <abstract><p>An abstract sentence.</p></abstract>
    </article-meta></front>
    <body><p>Body text here.</p></body>
</article>'''


def test_pmcxml2txt_joins_default_sections_with_separator():
    texts = list(pmcxml2txt(StringIO(_TXT_XML)))
    assert texts == ['A Great Title\n\nAn abstract sentence.\n\nBody text here.']


def test_pmcxml2txt_sections_filters_and_orders():
    texts = list(pmcxml2txt(StringIO(_TXT_XML), sections=('article', 'title')))
    assert texts == ['Body text here.\n\nA Great Title']


def test_pmcxml2txt_custom_passage_separator():
    texts = list(pmcxml2txt(StringIO(_TXT_XML), sections=('title', 'abstract'), passage_separator=' | '))
    assert texts == ['A Great Title | An abstract sentence.']


def test_pmcxml2txt_include_metadata_prepends_header():
    texts = list(pmcxml2txt(StringIO(_TXT_XML), sections=('title',), include_metadata=True))
    assert texts == ['pmid: 42\npmcid: PMC42\n\nA Great Title']


def test_pmcxml2txt_inject_citations_defaults_to_false():
    import inspect

    assert inspect.signature(pmcxml2txt).parameters['inject_citations'].default is False


_MALFORMED_ARTICLE_ID_XML = '''<article>
    <front><article-meta>
        <article-id>NoTypeAttribute</article-id>
        <article-id pub-id-type="pmid"></article-id>
    </article-meta></front>
    <body><p>Text.</p></body>
</article>'''


def test_malformed_article_ids_are_skipped():
    # an article-id with no pub-id-type attribute, or with no text, is ignored rather
    # than crashing or being picked up under the wrong key
    docs = list(parse_pmcxml(StringIO(_MALFORMED_ARTICLE_ID_XML), inject_citations=False))
    assert docs[0]['pmid'] == ''


_SEASON_PUBDATE_XML = '''<article>
    <front><article-meta>
        <article-id pub-id-type="pmid">1</article-id>
        <pub-date><season>Mar-Apr</season><year>2020</year></pub-date>
    </article-meta></front>
    <body><p>Text.</p></body>
</article>'''


def test_pub_month_resolved_from_season_field():
    # some PMC articles give the month as a "season" range (e.g. "Mar-Apr") instead of a
    # plain <month> field - the first recognized month name/abbreviation found in it is used
    docs = list(parse_pmcxml(StringIO(_SEASON_PUBDATE_XML), inject_citations=False))
    assert docs[0]['pub_month'] == 3


_UNMATCHED_SEASON_NO_YEAR_XML = '''<article>
    <front><article-meta>
        <article-id pub-id-type="pmid">1</article-id>
        <pub-date><season>Winter</season></pub-date>
    </article-meta></front>
    <body><p>Text.</p></body>
</article>'''


def test_pub_date_with_no_year_and_unmatched_season_stays_none():
    # a <pub-date> with no <year> at all, and a <season> that contains no recognizable
    # month name/abbreviation, should leave both fields as None rather than crashing
    docs = list(parse_pmcxml(StringIO(_UNMATCHED_SEASON_NO_YEAR_XML), inject_citations=False))
    assert docs[0]['pub_year'] is None
    assert docs[0]['pub_month'] is None


_REF_LIST_EDGE_CASES_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>See <xref ref-type="bibr" rid="r2">a</xref> and <xref ref-type="bibr" rid="r3">b</xref>.</p></body>
    <back><ref-list>
        <ref><element-citation><pub-id pub-id-type="pmid">999</pub-id></element-citation></ref>
        <ref id="r2"><element-citation><pub-id>no-type-attribute</pub-id><pub-id pub-id-type="doi"></pub-id></element-citation></ref>
        <ref id="r3"><element-citation><pub-id pub-id-type="pmid">333</pub-id></element-citation></ref>
    </ref-list></back>
</article>'''


def test_citation_lookup_skips_unidentifiable_refs():
    # a <ref> with no id attribute is skipped entirely (can never be cited by rid), and a
    # <ref> whose pub-id elements contribute nothing usable (missing pub-id-type or text)
    # is simply absent from the lookup - citing it still retags to <citation>, just with no
    # pmid/doi attributes added, rather than crashing
    docs = list(parse_pmcxml(StringIO(_REF_LIST_EDGE_CASES_XML)))
    text = ' '.join(p['text'] for p in docs[0]['text_sources']['article'])
    # r2 gets retagged (ref-type="bibr") but has no pmid/doi attribute added, since nothing
    # in its ref-list entry was usable
    assert '<citation ref-type="bibr" rid="r2" count="1">a</citation>' in text
    # r3, a normal ref, is unaffected by r2's edge cases
    assert 'pmid="333"' in text


def test_apply_pmc_xlink_fix_accepts_file_path(tmp_path):
    # source may be a path string rather than an already-open file handle
    content = '<article xmlns:xlink="http://www.w3.org/1999/xlink"><body/></article>'
    path = tmp_path / 'test.xml'
    path.write_text(content, encoding='utf-8')
    assert _apply_pmc_xlink_fix(str(path)).read() == content


def test_apply_pmc_xlink_fix_leaves_content_unchanged_when_no_article_tag_found():
    # 'xlink' appears somewhere in the document, but there's no <article...> tag to patch
    content = '<!-- mentions xlink here --><root><body/></root>'
    assert _apply_pmc_xlink_fix(StringIO(content)).read() == content


def test_apply_pmc_xlink_fix_adds_missing_namespace():
    content = '<article article-type="research-article"><body xlink:href="foo"/></article>'
    result = _apply_pmc_xlink_fix(StringIO(content)).read()
    assert result.startswith('<article xmlns:xlink="http://www.w3.org/1999/xlink"')


_SUBARTICLE_NO_OWN_METADATA_XML = '''<article>
    <front>
        <journal-meta><journal-title-group><journal-title>Parent Journal</journal-title></journal-title-group></journal-meta>
        <article-meta>
            <article-id pub-id-type="pmid">1</article-id>
            <article-id pub-id-type="pmc">PMC1</article-id>
            <article-id pub-id-type="doi">10.1/parent</article-id>
            <pub-date><year>2021</year><month>6</month><day>15</day></pub-date>
        </article-meta>
    </front>
    <body><p>Main finding.</p></body>
    <sub-article>
        <front-stub/>
        <body><p>Sub-article finding.</p></body>
    </sub-article>
</article>'''


def test_subarticle_without_own_metadata_inherits_all_of_parents():
    docs = list(parse_pmcxml(StringIO(_SUBARTICLE_NO_OWN_METADATA_XML), inject_citations=False))
    assert len(docs) == 2
    sub_doc = docs[1]
    assert sub_doc['pmid'] == '1'
    assert sub_doc['pmcid'] == 'PMC1'
    assert sub_doc['doi'] == '10.1/parent'
    assert sub_doc['pub_year'] == '2021'
    assert sub_doc['pub_month'] == '6'
    assert sub_doc['pub_day'] == '15'
    assert sub_doc['journal'] == 'Parent Journal'


_SUBARTICLE_WITH_OWN_DATE_AND_JOURNAL_XML = '''<article>
    <front>
        <journal-meta><journal-title-group><journal-title>Parent Journal</journal-title></journal-title-group></journal-meta>
        <article-meta>
            <article-id pub-id-type="pmid">1</article-id>
            <pub-date><year>2021</year></pub-date>
        </article-meta>
    </front>
    <body><p>Main finding.</p></body>
    <sub-article>
        <front-stub>
            <pub-date><year>2022</year></pub-date>
            <journal-title-group><journal-title>Sub Journal</journal-title></journal-title-group>
        </front-stub>
        <body><p>Sub finding.</p></body>
    </sub-article>
</article>'''


def test_subarticle_with_own_date_and_journal_keeps_them():
    # a sub-article that HAS its own pub-date/journal keeps them rather than being
    # overwritten by the parent's - only genuinely missing fields get inherited
    docs = list(parse_pmcxml(StringIO(_SUBARTICLE_WITH_OWN_DATE_AND_JOURNAL_XML), inject_citations=False))
    assert len(docs) == 2
    sub_doc = docs[1]
    assert sub_doc['pmid'] == '1'  # inherited, since the sub-article has no article-id
    assert sub_doc['pub_year'] == '2022'  # kept, not overwritten with the parent's 2021
    assert sub_doc['journal'] == 'Sub Journal'  # kept, not overwritten with "Parent Journal"


def test_pmcxml2bioc_raises_runtime_error_on_malformed_xml():
    with pytest.raises(RuntimeError):
        list(pmcxml2bioc(StringIO('<article><body><p>Unclosed')))


_NO_METADATA_XML = '<article><body><p>Just some text.</p></body></article>'


def test_pmcxml2txt_include_metadata_omits_header_when_all_fields_empty():
    texts = list(
        pmcxml2txt(StringIO(_NO_METADATA_XML), sections=('article',), include_metadata=True)
    )
    assert texts == ['Just some text.']
