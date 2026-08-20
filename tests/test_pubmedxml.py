from io import StringIO

import pytest

from bioconverters.main import docs2bioc

from .util import fetch_xml


@pytest.fixture(scope='module')
def doc():
    article = fetch_xml('20628391', 'pubmed')  # has a table to be processed in it
    file = StringIO(article)
    return list(docs2bioc(file, 'pubmedxml', trim_sentences=False))[0]


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
