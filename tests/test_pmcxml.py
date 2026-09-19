from io import StringIO

import pytest

from bioconverters import PMCMeta, parse_pmcxml, pmcxml2bioc, pmcxml2tagged, pmcxml2txt
from bioconverters.pmcxml import _apply_pmc_xlink_fix

from .util import fetch_xml


@pytest.fixture(scope='module')
def table_article():
    article = fetch_xml('PMC3203921', 'pmc')  # has a table to be processed in it
    return article


@pytest.fixture(scope='module')
def formula_article():
    # has MathML formulas (<mml:math>), each wrapped in a <disp-formula>/<inline-formula> -
    # confirmed by inspecting the raw XML, since PMC's search API doesn't support finding
    # articles by content like this directly
    article = fetch_xml('PMC9000000', 'pmc')
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


def test_convert_pmc_with_mathml_formula_drops_formula_content(formula_article):
    # every <mml:math> in this real article is wrapped in <disp-formula>/<inline-formula>, both
    # already-correct (unprefixed, unaffected by the Clark-notation bug fixed here) ignore_tags
    # entries, so this doesn't exercise the fix itself (see test_bare_mathml_is_dropped for
    # that) - it's a real-world sanity check that formula-heavy content still parses cleanly and
    # doesn't leak raw LaTeX/MathML source into the output
    file = StringIO(formula_article)
    all_passages = []
    for doc in pmcxml2bioc(file):
        all_passages.extend(doc.passages)
    all_text = " ".join(p.text for p in all_passages)
    assert '\\documentclass' not in all_text
    assert 'mml:m' not in all_text
    assert '<mml' not in all_text


_BARE_MATHML_XML = '''<article xmlns:mml="http://www.w3.org/1998/Math/MathML">
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>Before <mml:math><mml:mi>ZZFORMULAZZ</mml:mi></mml:math> after.</p></body>
</article>'''


def test_bare_mathml_is_dropped():
    # JATS allows <mml:math> directly inside <p> (and several other elements), not just wrapped
    # in <disp-formula>/<inline-formula> - this is the case the Clark-notation fix actually
    # covers, since a bare <mml:math> isn't blanked by ignoring those two wrapper tags
    results = list(pmcxml2txt(StringIO(_BARE_MATHML_XML), sections=('article',)))
    _, text = results[0]
    assert 'ZZFORMULAZZ' not in text
    assert text == 'Before after.'


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
    docs = list(
        parse_pmcxml(
            StringIO(_CITATION_XML),
            inject_citations=True,
            clean_numeric_citations=False,
            return_xml=True,
        )
    )
    text = ' '.join(docs[0].article)

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


def test_inject_citations_keeps_citation_attributes_but_strips_other_kept_tags():
    xml = '''<article>
        <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
        <body><p>the <italic toggle="yes">ABC1</italic> protein <xref ref-type="bibr" rid="r1">1</xref>.</p></body>
        <back><ref-list>
            <ref id="r1"><element-citation><pub-id pub-id-type="pmid">111</pub-id></element-citation></ref>
        </ref-list></back>
    </article>'''
    docs = list(
        parse_pmcxml(
            StringIO(xml),
            keep_tags={'italic'},
            inject_citations=True,
            clean_numeric_citations=False,
            return_xml=True,
        )
    )
    text = ' '.join(docs[0].article)

    # citation injection's own attributes (pmid/count) are preserved...
    assert 'pmid="111"' in text
    assert 'count="1"' in text
    # ...but an unrelated kept tag's source-XML attribute (toggle) is stripped
    assert '<italic>ABC1</italic>' in text
    assert 'toggle' not in text


def test_strip_tag_attributes_false_keeps_kept_tags_attributes():
    # strip_tag_attributes=False opts out of the stripping exercised above: an ordinary kept
    # tag's source-XML attribute (toggle) survives, same as citation injection's own always-kept
    # attributes (pmid/count)
    xml = '''<article>
        <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
        <body><p>the <italic toggle="yes">ABC1</italic> protein <xref ref-type="bibr" rid="r1">1</xref>.</p></body>
        <back><ref-list>
            <ref id="r1"><element-citation><pub-id pub-id-type="pmid">111</pub-id></element-citation></ref>
        </ref-list></back>
    </article>'''
    docs = list(
        parse_pmcxml(
            StringIO(xml),
            keep_tags={'italic'},
            inject_citations=True,
            clean_numeric_citations=False,
            return_xml=True,
            strip_tag_attributes=False,
        )
    )
    text = ' '.join(docs[0].article)

    assert 'pmid="111"' in text
    assert 'count="1"' in text
    assert '<italic toggle="yes">ABC1</italic>' in text


def test_inject_citations_and_clean_numeric_citations_together_raises():
    with pytest.raises(AssertionError):
        list(parse_pmcxml(StringIO(_CITATION_XML), inject_citations=True, clean_numeric_citations=True))


def test_inject_citations_false_drops_citations_like_before():
    docs = list(parse_pmcxml(StringIO(_CITATION_XML), inject_citations=False, return_xml=True))
    text = ' '.join(docs[0].article)
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
    docs = list(
        parse_pmcxml(
            StringIO(_SUBARTICLE_CITATION_XML),
            inject_citations=True,
            clean_numeric_citations=False,
            return_xml=True,
        )
    )
    assert len(docs) == 2
    sub_doc = docs[1]
    assert sub_doc.pmid == '2'
    text = ' '.join(sub_doc.article)
    assert 'pmid="111"' in text
    assert '>1</citation>' in text


_PARENTHETICAL_XREF_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>Expression levels are shown in (<xref ref-type="fig" rid="f1">Table 3</xref>) below. See Table 3, third row, for details.</p></body>
</article>'''


def test_clean_xrefs_in_brackets_default_drops_standalone_parenthetical_reference():
    docs = list(parse_pmcxml(StringIO(_PARENTHETICAL_XREF_XML), inject_citations=False))
    text = ' '.join(docs[0].article)
    assert 'shown in below' in text
    assert 'third row' in text  # unrelated plain-text mention still survives


def test_clean_xrefs_in_brackets_false_keeps_dangling_reference():
    docs = list(
        parse_pmcxml(
            StringIO(_PARENTHETICAL_XREF_XML),
            inject_citations=False,
            clean_xrefs_in_brackets=False,
        )
    )
    text = ' '.join(docs[0].article)
    assert 'shown in (Table 3) below' in text


def test_pmcxml2bioc_clean_xrefs_in_brackets_false_keeps_dangling_reference():
    docs = list(pmcxml2bioc(StringIO(_PARENTHETICAL_XREF_XML), clean_xrefs_in_brackets=False))
    text = ' '.join(p.text for p in docs[0].passages)
    assert 'shown in (Table 3) below' in text


_SQUARE_BRACKET_XREF_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>Results were reported previously <xref ref-type="bibr" rid="r1">[1]</xref>. See Figure 1 for details.</p></body>
</article>'''


def test_clean_numeric_citations_default_drops_own_content_in_square_brackets():
    # the bibr citation's own content "[1]" is dropped outright, regardless of surrounding
    # context (no parentheses needed, unlike the "(Table 1)" case)
    docs = list(parse_pmcxml(StringIO(_SQUARE_BRACKET_XREF_XML), inject_citations=False))
    text = ' '.join(docs[0].article)
    # the citation sits directly before a sentence-ending period, so that period is pulled
    # back over the gap rather than leaving a dangling "previously ."
    assert 'reported previously.' in text
    assert 'reported previously .' not in text
    assert 'Figure 1' in text  # unrelated, unbracketed xref still survives


def test_clean_numeric_citations_false_keeps_own_content_in_square_brackets():
    docs = list(
        parse_pmcxml(
            StringIO(_SQUARE_BRACKET_XREF_XML),
            inject_citations=False,
            clean_numeric_citations=False,
        )
    )
    text = ' '.join(docs[0].article)
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
    results = list(pmcxml2txt(StringIO(_TXT_XML)))
    texts = [text for _, text in results]
    assert texts == ['A Great Title\n\nAn abstract sentence.\n\nBody text here.']


def test_pmcxml2txt_sections_filters_and_orders():
    results = list(pmcxml2txt(StringIO(_TXT_XML), sections=('article', 'title')))
    texts = [text for _, text in results]
    assert texts == ['Body text here.\n\nA Great Title']


def test_pmcxml2txt_custom_passage_separator():
    results = list(pmcxml2txt(StringIO(_TXT_XML), sections=('title', 'abstract'), passage_separator=' | '))
    texts = [text for _, text in results]
    assert texts == ['A Great Title | An abstract sentence.']


def test_pmcxml2txt_yields_metadata_alongside_text():
    (meta, text), = list(pmcxml2txt(StringIO(_TXT_XML), sections=('title',)))
    assert isinstance(meta, PMCMeta)
    assert meta.pmid == '42'
    assert meta.pmcid == 'PMC42'
    assert text == 'A Great Title'


def test_pmcxml2txt_has_no_include_metadata_param():
    # metadata is always returned now, as the first element of the (meta, text) tuple - there's
    # no longer a flag to opt in/out of it
    import inspect

    assert 'include_metadata' not in inspect.signature(pmcxml2txt).parameters


def test_pmcxml2txt_has_no_inject_citations_param():
    # plain text output can't show the injected pmid/doi attributes anyway - see
    # test_inject_citations_has_no_effect_on_pmcxml2bioc for the same reasoning on pmcxml2bioc
    import inspect

    assert 'inject_citations' not in inspect.signature(pmcxml2txt).parameters


def test_flag_defaults_are_consistent_across_pmc_functions():
    import inspect

    for func in (parse_pmcxml, pmcxml2txt, pmcxml2bioc):
        params = inspect.signature(func).parameters
        assert params['trim_buggy_sentences'].default is True
        assert params['clean_numeric_citations'].default is True
        assert params['clean_xrefs_in_brackets'].default is True
        assert params['clear_empty_brackets'].default is True
        assert params['fix_exponentials'].default is True
    assert inspect.signature(parse_pmcxml).parameters['inject_citations'].default is False
    assert inspect.signature(parse_pmcxml).parameters['return_xml'].default is False


def test_pmcxml2bioc_sections_default_includes_all_six_groups():
    import inspect

    default_sections = inspect.signature(pmcxml2bioc).parameters['sections'].default
    assert set(default_sections) == {'title', 'subtitle', 'abstract', 'article', 'back', 'floating'}


def test_pmcxml2txt_sections_default_matches_pmcxml2bioc():
    import inspect

    assert (
        inspect.signature(pmcxml2txt).parameters['sections'].default
        == inspect.signature(pmcxml2bioc).parameters['sections'].default
    )


def test_pmcxml2bioc_sections_filters_and_orders_passages():
    docs = list(pmcxml2bioc(StringIO(_TXT_XML), sections=('abstract',)))
    sections_seen = [p.infons['section'] for p in docs[0].passages]
    assert sections_seen == ['abstract']


_EXPONENTIAL_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id></article-meta></front>
    <body><p>The speed of light is 3x10<sup>8</sup> m/s, first measured in the 1<sup>st</sup> century by <sup>14</sup>C dating pioneers.</p></body>
</article>'''


def test_fix_exponentials_true_converts_exponent_via_pmcxml2txt():
    results = list(pmcxml2txt(StringIO(_EXPONENTIAL_XML), sections=('article',), fix_exponentials=True))
    _, text = results[0]
    assert '3x10^8 m/s' in text
    # ordinal and isotope notation are untouched
    assert '1st century' in text
    assert '14C dating' in text


def test_fix_exponentials_false_leaves_exponent_glued_via_pmcxml2txt():
    results = list(pmcxml2txt(StringIO(_EXPONENTIAL_XML), sections=('article',), fix_exponentials=False))
    _, text = results[0]
    assert '3x108 m/s' in text
    assert '^' not in text


_TAGGED_XML = '''<article>
    <front><article-meta><article-id pub-id-type="pmid">1</article-id>
    <title-group><article-title>the <italic toggle="yes">ABC1</italic> gene</article-title></title-group>
    </article-meta></front>
    <body><p>the <italic toggle="yes">ABC1</italic> protein <xref ref-type="bibr" rid="r1">1</xref> is active.</p></body>
    <back><ref-list>
        <ref id="r1"><element-citation><pub-id pub-id-type="pmid">111</pub-id></element-citation></ref>
    </ref-list></back>
</article>'''


def test_pmcxml2tagged_keeps_markup_citations_and_strips_source_attributes():
    results = list(pmcxml2tagged(StringIO(_TAGGED_XML), sections=('title', 'article')))
    meta, text = results[0]

    assert isinstance(meta, PMCMeta)
    assert meta.pmid == '1'
    # formatting tags are kept, but their source-XML attributes (toggle) are stripped
    assert '<italic>ABC1</italic>' in text
    assert 'toggle' not in text
    # the in-text citation is resolved and kept, with its injected pmid attribute
    assert '<citation' in text
    assert 'pmid="111"' in text
    # numeric citation cleanup can't run alongside injection, so nothing eats the marker first
    assert 'xref' not in text


def test_pmcxml2tagged_strip_tag_attributes_false_keeps_source_attributes():
    results = list(
        pmcxml2tagged(StringIO(_TAGGED_XML), sections=('article',), strip_tag_attributes=False)
    )
    _, text = results[0]
    assert '<italic toggle="yes">ABC1</italic>' in text


def test_pmcxml2tagged_keep_tags_defaults_to_pmc_keep_tags():
    import inspect

    from bioconverters.pmc_constants import PMC_KEEP_TAGS

    assert inspect.signature(pmcxml2tagged).parameters['keep_tags'].default == PMC_KEEP_TAGS


def test_pmcxml2tagged_has_no_inject_citations_or_clean_numeric_citations_params():
    # both are forced (inject_citations=True, clean_numeric_citations=False) since the whole
    # point of this wrapper is resolved, kept citations - exposing either would let a caller
    # recreate the combination parse_pmcxml explicitly rejects
    import inspect

    params = inspect.signature(pmcxml2tagged).parameters
    assert 'inject_citations' not in params
    assert 'clean_numeric_citations' not in params


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
    assert docs[0].pmid is None


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
    assert docs[0].pub_month == 3


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
    assert docs[0].pub_year is None
    assert docs[0].pub_month is None


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
    docs = list(
        parse_pmcxml(
            StringIO(_REF_LIST_EDGE_CASES_XML),
            inject_citations=True,
            clean_numeric_citations=False,
            return_xml=True,
        )
    )
    text = ' '.join(docs[0].article)
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
    assert sub_doc.pmid == '1'
    assert sub_doc.pmcid == 'PMC1'
    assert sub_doc.doi == '10.1/parent'
    assert sub_doc.pub_year == '2021'
    assert sub_doc.pub_month == '6'
    assert sub_doc.pub_day == '15'
    assert sub_doc.journal == 'Parent Journal'


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
    assert sub_doc.pmid == '1'  # inherited, since the sub-article has no article-id
    assert sub_doc.pub_year == '2022'  # kept, not overwritten with the parent's 2021
    assert sub_doc.journal == 'Sub Journal'  # kept, not overwritten with "Parent Journal"


def test_pmcxml2bioc_raises_runtime_error_on_malformed_xml():
    with pytest.raises(RuntimeError):
        list(pmcxml2bioc(StringIO('<article><body><p>Unclosed')))


_NO_METADATA_XML = '<article><body><p>Just some text.</p></body></article>'


def test_pmcxml2txt_metadata_fields_empty_when_absent_from_source():
    (meta, text), = list(pmcxml2txt(StringIO(_NO_METADATA_XML), sections=('article',)))
    assert meta.pmid is None
    assert meta.pmcid == ''
    assert meta.doi == ''
    assert meta.pub_year is None
    assert text == 'Just some text.'
