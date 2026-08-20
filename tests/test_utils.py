import textwrap
import xml.etree.ElementTree as etree

import pytest

from bioconverters.pmc_tags import PMC_IGNORE_TAGS, PMC_KEEP_TAGS, PMC_SPLIT_TAGS
from bioconverters.utils import _extract_passages, _remove_brackets_without_words


@pytest.mark.parametrize(
    'test_input,expected',
    [
        (' ((())(', ' ('),
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


def test_extract_figure_label():
    xml_input = '<article><fig id="pone-0026760-g003" position="float"><object-id pub-id-type="doi">10.1371/journal.pone.0026760.g003</object-id><label>Figure 3</label><caption><title>Anchorage-independent growth of ERBB2 mutants.</title></caption><graphic/></fig></article>'
    passages = _extract_passages(
        [etree.fromstring(xml_input)], PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, PMC_KEEP_TAGS
    )
    assert 'Figure 3' in passages
    # the object-id (doi) is an ignore_tag, so its content shouldn't survive
    assert not any('10.1371' in t for t in passages)


def test_extract_title_with_italics():
    xml = '<article><article-title>Activating mutations in <italic>ALK</italic> provide a therapeutic target in neuroblastoma</article-title></article>'
    passages = _extract_passages([etree.fromstring(xml)], PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, PMC_KEEP_TAGS)
    assert len(passages) == 1
    # italic is a keep_tag, so ALK should come through as inline markup in the XML string
    assert (
        'Activating mutations in <italic>ALK</italic> provide a therapeutic target in neuroblastoma'
        == passages[0]
    )


def test_extract_title_without_keep_tags():
    xml = '<article><article-title>Activating mutations in <italic>ALK</italic> provide a therapeutic target in neuroblastoma</article-title></article>'
    passages = _extract_passages([etree.fromstring(xml)], PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, set())
    assert len(passages) == 1
    # with keep_tags empty, the result is just plain text - no markup at all
    assert (
        'Activating mutations in ALK provide a therapeutic target in neuroblastoma'
        == passages[0]
    )


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
    passages = _extract_passages([etree.fromstring(xml)], PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, PMC_KEEP_TAGS)
    text = ' '.join(passages)
    assert 'supplementary Figure S4C' not in text
    assert 'Annals of Oncology' not in text


def test_drops_extlink_urls_and_citation_markers():
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
    passages = _extract_passages([etree.fromstring(xml)], PMC_IGNORE_TAGS, PMC_SPLIT_TAGS, PMC_KEEP_TAGS)
    assert len(passages) == 1
    text = passages[0]
    assert 'program PyMOL' in text
    assert '[14]' not in text
    assert '//www.' not in text
