from io import StringIO

import pytest

from bioconverters import pubmedxml2bioc, pubmedxml2txt

from .util import fetch_xml


@pytest.fixture(scope='module')
def doc():
    article = fetch_xml('20628391', 'pubmed')  # has a table to be processed in it
    file = StringIO(article)
    return list(pubmedxml2bioc(file))[0]


def test_convert_has_expected_sections(doc):
    # this article has a structured abstract with multiple <AbstractText> sections,
    # each of which becomes its own 'abstract' passage
    sections = [p.infons['section'] for p in doc.passages]
    assert sections[0] == 'title'
    assert all(s == 'abstract' for s in sections[1:])
    assert len(sections) > 2


@pytest.mark.parametrize(
    'infon,value',
    [
        ('year', 2010),
        ('month', 7),
        ('day', 16),
        ('journal', 'British journal of cancer'),
        ('pmcid', 'PMC2939780'),
        ('doi', '10.1038/sj.bjc.6605776'),
        ('journal_iso', 'Br J Cancer'),
        (
            'title',
            'UGT1A and TYMS genetic variants predict toxicity and response of colorectal cancer patients treated with first-line irinotecan and fluorouracil combination therapy.',
        ),
        ('pmid', '20628391'),
    ],
)
def test_metadata_infons(doc, infon, value):
    assert doc.infons[infon] == value


_TXT_XML = '''<PubmedArticle>
    <MedlineCitation>
        <PMID>99</PMID>
        <Article>
            <Journal>
                <JournalIssue><PubDate><Year>2020</Year><Month>5</Month><Day>1</Day></PubDate></JournalIssue>
                <Title>Journal of Testing</Title>
            </Journal>
            <ArticleTitle>A Test Title</ArticleTitle>
            <Abstract><AbstractText>An abstract sentence.</AbstractText></Abstract>
        </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
</PubmedArticle>'''


def test_pubmedxml2txt_joins_default_sections_with_separator():
    texts = list(pubmedxml2txt(StringIO(_TXT_XML)))
    assert texts == ['A Test Title\n\nAn abstract sentence.']


def test_pubmedxml2txt_sections_filters_and_orders():
    texts = list(pubmedxml2txt(StringIO(_TXT_XML), sections=('abstract',)))
    assert texts == ['An abstract sentence.']


def test_pubmedxml2txt_custom_passage_separator():
    texts = list(pubmedxml2txt(StringIO(_TXT_XML), passage_separator=' | '))
    assert texts == ['A Test Title | An abstract sentence.']


def test_pubmedxml2txt_include_metadata_prepends_header():
    texts = list(pubmedxml2txt(StringIO(_TXT_XML), sections=('title',), include_metadata=True))
    assert texts == ['pmid: 99\nyear: 2020\nmonth: 5\nday: 1\njournal: Journal of Testing\n\nA Test Title']
