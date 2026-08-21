import textwrap
import xml.etree.ElementTree as etree

import pytest

from bioconverters.pmc_constants import PMC_IGNORE_TAGS, PMC_KEEP_TAGS, PMC_SPLIT_TAGS
from bioconverters.utils import (
    _blank_bracketed_xrefs,
    _clean_numeric_citations,
    _extract_passages,
    _fix_exponentials,
    _remove_brackets_from_titles,
    _remove_brackets_without_words,
)


@pytest.mark.parametrize(
    'test_input,expected',
    [
        (' ((())(', '('),
        ('( [3] [4] )', '( [3] [4] )'),
        ('( [] )', ''),
        ('(Fig. 1)', '(Fig. 1)'),
        ('(Table. 1)', '(Table. 1)'),
        ('( ; )', ''),
        ('( . )', ''),
        ('   }{ \t}{   ', '   }{ \t}{   '),
        ('( [] [ ] )', ''),
    ],
)
def test_remove_brackets_without_words(test_input, expected):
    assert expected == _remove_brackets_without_words(test_input)


def test_remove_brackets_from_titles_strips_brackets_but_keeps_period():
    assert _remove_brackets_from_titles('[A study of things].') == 'A study of things.'


def test_remove_brackets_from_titles_leaves_normal_title_untouched():
    assert _remove_brackets_from_titles('A normal title.') == 'A normal title.'


def test_extract_figure_label():
    xml_input = '<article><fig id="pone-0026760-g003" position="float"><object-id pub-id-type="doi">10.1371/journal.pone.0026760.g003</object-id><label>Figure 3</label><caption><title>Anchorage-independent growth of ERBB2 mutants.</title></caption><graphic/></fig></article>'
    passages = _extract_passages(
        [etree.fromstring(xml_input)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=True,
        trim_buggy_sentences=True,
    )
    assert 'Figure 3' in passages
    # the object-id (doi) is an ignore_tag, so its content shouldn't survive
    assert not any('10.1371' in t for t in passages)


def test_extract_title_with_italics():
    xml = '<article><article-title>Activating mutations in <italic>ALK</italic> provide a therapeutic target in neuroblastoma</article-title></article>'
    passages = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=True,
        trim_buggy_sentences=True,
    )
    assert len(passages) == 1
    # italic is a keep_tag, so ALK should come through as inline markup in the XML string
    assert (
        'Activating mutations in <italic>ALK</italic> provide a therapeutic target in neuroblastoma'
        == passages[0]
    )


def test_extract_title_without_keep_tags():
    xml = '<article><article-title>Activating mutations in <italic>ALK</italic> provide a therapeutic target in neuroblastoma</article-title></article>'
    passages = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        set(),
        return_xml=True,
        trim_buggy_sentences=True,
    )
    assert len(passages) == 1
    # with keep_tags empty, the result is just plain text - no markup at all
    assert (
        'Activating mutations in ALK provide a therapeutic target in neuroblastoma'
        == passages[0]
    )


def test_extract_title_return_xml_false_strips_markup():
    xml = '<article><article-title>Activating mutations in <italic>ALK</italic> provide a therapeutic target in neuroblastoma</article-title></article>'
    passages = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=False,
        trim_buggy_sentences=True,
    )
    assert len(passages) == 1
    # return_xml=False strips markup even though italic is a keep_tag
    assert (
        'Activating mutations in ALK provide a therapeutic target in neuroblastoma'
        == passages[0]
    )


def test_return_xml_true_keeps_valid_xml_escaping():
    xml = '<article><p>Coffee &amp; Tea, P&lt;0.05</p></article>'
    passages = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=True,
        trim_buggy_sentences=True,
    )
    assert len(passages) == 1
    # special characters stay properly XML-escaped
    assert passages[0] == 'Coffee &amp; Tea, P&lt;0.05'


def test_return_xml_false_unescapes_entities():
    xml = '<article><p>Coffee &amp; Tea, P&lt;0.05</p></article>'
    passages = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=False,
        trim_buggy_sentences=True,
    )
    assert len(passages) == 1
    # entities get decoded back to their literal characters
    assert passages[0] == 'Coffee & Tea, P<0.05'


def test_trim_buggy_sentences_false_leaves_long_runs_untouched():
    long_run = "x" * 100000
    xml = f'<article><p>{long_run}</p></article>'
    trimmed = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=False,
        trim_buggy_sentences=True,
    )
    untrimmed = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=False,
        trim_buggy_sentences=False,
    )
    assert len(trimmed[0]) < 100000
    assert len(untrimmed[0]) == 100000


def test_drops_extlink_supplementary_text():
    # ext-link content is always dropped now (no supplementary figure/table exception)
    xml = textwrap.dedent(
        '''\
        <?xml version="1.1" encoding="utf8" ?>
         <article xmlns:ali="http://www.niso.org/schemas/ali/1.0/"
            xmlns:xlink="http://www.w3.org/1999/xlink"
            xmlns:mml="http://www.w3.org/1998/Math/MathML" article-type="research-article">
            <p>
                Introduction of the <italic>NTRK3</italic> G623R mutation to the <italic>ETV6-NTRK3</italic> construct (Ba/F3-ETV6-NTRK3 G623R) conferred reduced sensitivity to entrectinib, increasing the IC<sub>50</sub> value in the proliferation assays more than 250-fold (2 to 507 nM) relative to the Ba/F3-ETV6-NTRK3 cells (Figure <xref ref-type="fig" rid="MDW042F3">3</xref>E). The <italic>NTRK3</italic> G623R mutation conferred even greater loss of sensitivity to the other tested Trk inhibitors, TSR-011 (Tesaro) and LOXO-101 (LOXO), eliciting IC<sub>50</sub> proliferation values of &gt;1000 nM (<ext-link ext-link-type="uri" xlink:href="http://annonc.oxfordjournals.org/lookup/suppl/doi:10.1093/annonc/mdw042/-/DC1">supplementary Figure S4C, available at <italic>Annals of Oncology</italic> online</ext-link>).
            </p>
        </article>'''
    )
    passages = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=True,
        trim_buggy_sentences=True,
    )
    text = ' '.join(passages)
    assert 'supplementary Figure S4C' not in text
    assert 'Annals of Oncology' not in text


def test_drops_extlink_urls_but_keeps_xref_text():
    xml = textwrap.dedent(
        '''\
    <?xml version="1.1" encoding="utf8" ?>
    <article xmlns:ali="http://www.niso.org/schemas/ali/1.0/"
        xmlns:xlink="http://www.w3.org/1999/xlink"
        xmlns:mml="http://www.w3.org/1998/Math/MathML" article-type="research-article">
    <p>
        Crystal  Protein Data Bank (
        <ext-link ext-link-type="uri" xlink:href="http://www.pdb.org">www.pdb.org</ext-link>
        ). Crystal structures of complexes with  program PyMOL (
        <ext-link ext-link-type="uri" xlink:href="http://www.pymol.org">www.pymol.org</ext-link>
        )
        <xref rid="pone.0026760-Yun1" ref-type="bibr">[14]</xref>
        ,
        <xref rid="pone.0026760-Yun2" ref-type="bibr">[16]</xref>
        ,
        <xref rid="pone.0026760-Stamos1" ref-type="bibr">[23]</xref>
        –
        <xref rid="pone.0026760-Qiu1" ref-type="bibr">[25]</xref>
        .
    </p>
    </article>'''
    )
    passages = _extract_passages(
        [etree.fromstring(xml)],
        PMC_IGNORE_TAGS,
        PMC_SPLIT_TAGS,
        PMC_KEEP_TAGS,
        return_xml=True,
        trim_buggy_sentences=True,
    )
    assert len(passages) == 1
    text = passages[0]
    assert 'program PyMOL' in text
    assert '//www.' not in text
    # citation markers are no longer blanked at this level - xref is not blanket-ignored,
    # so its text content survives here; dropping citation markers is now pmcxml.py's
    # inject_citations feature (see test_pmcxml.py), not something _extract_passages does
    # on its own
    assert '[14]' in text


def test_extract_passages_accepts_single_element_not_just_list():
    # elements may be passed as a single Element rather than wrapped in a list
    elem = etree.fromstring('<article><p>Some text.</p></article>')
    passages = _extract_passages(
        elem, PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, PMC_KEEP_TAGS, return_xml=False,
        trim_buggy_sentences=True,
    )
    assert passages == ['Some text.']


def test_extract_passages_skips_passages_left_empty_by_ignore_tags():
    # a passage entirely made of ignored content (here, a table) is blanked down to nothing
    # by spans_to_passages itself (it drops any passage whose stripped text is blank), so
    # no empty string should surface in the results
    xml = '<article><p>Real text.</p><p><table><tr><td>1</td></tr></table></p></article>'
    passages = _extract_passages(
        [etree.fromstring(xml)], PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, PMC_KEEP_TAGS,
        return_xml=False, trim_buggy_sentences=True,
    )
    assert passages == ['Real text.']


def test_blank_bracketed_xrefs_drops_standalone_reference():
    text = 'The results are shown in (Table 1) below.'
    start = text.index('Table 1')
    spans = [(start, len('Table 1'), 'xref', {})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert len(new_text) == len(text)
    assert new_text == 'The results are shown in           below.'
    assert kept_spans == []


def test_blank_bracketed_xrefs_drops_standalone_reference_in_square_brackets():
    # a bare (non-bracketed-content) xref surrounded by "[...]" in the text is dropped just
    # like the "(...)" case, wrapper included
    text = 'The results are shown in [Table 1] below.'
    start = text.index('Table 1')
    spans = [(start, len('Table 1'), 'xref', {})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert len(new_text) == len(text)
    assert new_text == 'The results are shown in           below.'
    assert kept_spans == []


def test_blank_bracketed_xrefs_keeps_mismatched_surrounding_punctuation():
    # "[" ... ")" is not a matching pair, so this is left untouched entirely (unlike the
    # matched "(...)"/"[...]" cases)
    text = 'The results are shown in [Table 1) below.'
    start = text.index('Table 1')
    spans = [(start, len('Table 1'), 'xref', {})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert new_text == text
    assert kept_spans == spans


def test_blank_bracketed_xrefs_drops_double_wrapped_reference():
    # the xref's own content is already "[1]", and that's further wrapped in "(...)" - the
    # whole outer range is blanked so no dangling empty "()" is left behind
    text = 'As reported previously ([1]).'
    start = text.index('[1]')
    spans = [(start, len('[1]'), 'xref', {})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert len(new_text) == len(text)
    assert new_text == text.replace('([1])', ' ' * len('([1])'))
    assert kept_spans == []


def test_blank_bracketed_xrefs_drops_double_wrapped_reference_in_square_brackets():
    text = 'As reported previously [[1]].'
    start = text.index('[1]')
    spans = [(start, len('[1]'), 'xref', {})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert new_text == text.replace('[[1]]', ' ' * len('[[1]]'))
    assert kept_spans == []


def test_blank_bracketed_xrefs_keeps_mixed_prose():
    text = 'The results are shown in (see Table 1) below.'
    start = text.index('Table 1')
    spans = [(start, len('Table 1'), 'xref', {})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert new_text == text
    assert kept_spans == spans


def test_blank_bracketed_xrefs_keeps_grouped_references():
    text = 'See (Figure 7 and Table 3) for details.'
    fig_start = text.index('Figure 7')
    table_start = text.index('Table 3')
    spans = [
        (fig_start, len('Figure 7'), 'xref', {}),
        (table_start, len('Table 3'), 'xref', {}),
    ]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert new_text == text
    assert kept_spans == spans


def test_blank_bracketed_xrefs_passes_through_non_xref_spans():
    text = 'A (parenthetical) note.'
    start = text.index('parenthetical')
    spans = [(start, len('parenthetical'), 'italic', {})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert new_text == text
    assert kept_spans == spans


def test_blank_bracketed_xrefs_keeps_own_bracketed_content_now_handled_by_clean_numeric_citations():
    # own-content-bracketed xrefs are no longer this function's job - that's _clean_numeric_citations
    text = 'Results were reported previously [1].'
    start = text.index('[1]')
    spans = [(start, len('[1]'), 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _blank_bracketed_xrefs(text, spans)

    assert new_text == text
    assert kept_spans == spans


def test_fix_exponentials_converts_digit_preceded_sup_to_caret():
    assert _fix_exponentials('10<sup>8</sup> m/s') == '10^8 m/s'


def test_fix_exponentials_handles_negative_exponent():
    assert _fix_exponentials('10<sup>-8</sup> m/s') == '10^-8 m/s'


def test_fix_exponentials_handles_multi_digit_base():
    assert _fix_exponentials('299<sup>2</sup>') == '299^2'


def test_fix_exponentials_leaves_ordinal_suffix_untouched():
    # sup content isn't numeric, so this falls through unchanged
    assert _fix_exponentials('1<sup>st</sup> place') == '1<sup>st</sup> place'


def test_fix_exponentials_leaves_isotope_notation_untouched():
    # sup content is numeric, but nothing precedes it with a digit
    assert _fix_exponentials('<sup>14</sup>C labeling') == '<sup>14</sup>C labeling'


def test_fix_exponentials_leaves_non_numeric_preceding_text_untouched():
    assert _fix_exponentials('see note<sup>3</sup>') == 'see note<sup>3</sup>'


def test_fix_exponentials_matches_sup_with_attributes():
    assert _fix_exponentials('10<sup id="x">8</sup> m/s') == '10^8 m/s'


def test_fix_exponentials_handles_multiple_occurrences():
    assert _fix_exponentials('10<sup>8</sup> and 10<sup>-3</sup>') == '10^8 and 10^-3'


def test_clean_numeric_citations_drops_bare_numeric_citation():
    text = 'Results were reported previously 1.'
    start = text.index('1.')
    spans = [(start, 1, 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert len(new_text) == len(text)
    assert new_text == 'Results were reported previously  .'
    assert kept_spans == []


def test_clean_numeric_citations_drops_bracketed_numeric_citation():
    text = 'Results were reported previously [1].'
    start = text.index('[1]')
    spans = [(start, len('[1]'), 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert len(new_text) == len(text)
    assert new_text == 'Results were reported previously    .'
    assert kept_spans == []


def test_clean_numeric_citations_drops_bracketed_multiple_ids():
    text = 'As shown before [1,2,3].'
    start = text.index('[1,2,3]')
    spans = [(start, len('[1,2,3]'), 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert len(new_text) == len(text)
    assert new_text == text.replace('[1,2,3]', ' ' * len('[1,2,3]'))
    assert kept_spans == []


def test_clean_numeric_citations_drops_ranged_citation():
    text = 'As shown before [1-3].'
    start = text.index('[1-3]')
    spans = [(start, len('[1-3]'), 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert new_text == text.replace('[1-3]', ' ' * len('[1-3]'))
    assert kept_spans == []


def test_clean_numeric_citations_ignores_surrounding_context():
    # unlike _blank_bracketed_xrefs, no surrounding context is needed or checked - this is
    # what catches a citation glued directly onto a word with nothing separating them at all
    text = 'As shown before (see [1] for details).'
    start = text.index('[1]')
    spans = [(start, len('[1]'), 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert new_text == 'As shown before (see     for details).'
    assert kept_spans == []


def test_clean_numeric_citations_drops_citation_glued_directly_to_word():
    text = 'This was shown in tuberculosis1/HIV co-infected patients.'
    start = text.index('1/HIV')
    spans = [(start, 1, 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert new_text == 'This was shown in tuberculosis /HIV co-infected patients.'
    assert kept_spans == []


def test_clean_numeric_citations_leaves_non_bibr_xref_untouched():
    text = 'See Table [1] for details.'
    start = text.index('[1]')
    spans = [(start, len('[1]'), 'xref', {'ref-type': 'table'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert new_text == text
    assert kept_spans == spans


def test_clean_numeric_citations_leaves_author_date_citation_untouched():
    text = 'This was previously shown (Smith et al., 2020).'
    start = text.index('Smith et al., 2020')
    spans = [(start, len('Smith et al., 2020'), 'xref', {'ref-type': 'bibr'})]

    new_text, kept_spans = _clean_numeric_citations(text, spans)

    assert new_text == text
    assert kept_spans == spans
