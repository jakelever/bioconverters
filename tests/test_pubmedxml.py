from io import StringIO

import pytest

from bioconverters import (
    Chemical,
    MeshHeading,
    MeshQualifier,
    PublicationType,
    SupplementaryMeshConcept,
    parse_pubmedxml,
    pubmedxml2bioc,
    pubmedxml2txt,
)

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


def test_pubmedxml2bioc_sections_filters_and_orders():
    docs = list(pubmedxml2bioc(StringIO(_TXT_XML), sections=('abstract',)))
    sections_seen = [p.infons['section'] for p in docs[0].passages]
    assert sections_seen == ['abstract']


def test_pubmedxml2bioc_sections_default_matches_pubmedxml2txt():
    import inspect

    assert (
        inspect.signature(pubmedxml2bioc).parameters['sections'].default
        == inspect.signature(pubmedxml2txt).parameters['sections'].default
        == ('title', 'abstract')
    )


def test_pubmedxml2txt_custom_passage_separator():
    texts = list(pubmedxml2txt(StringIO(_TXT_XML), passage_separator=' | '))
    assert texts == ['A Test Title | An abstract sentence.']


def test_pubmedxml2txt_include_metadata_prepends_header():
    texts = list(pubmedxml2txt(StringIO(_TXT_XML), sections=('title',), include_metadata=True))
    assert texts == ['pmid: 99\nyear: 2020\nmonth: 5\nday: 1\njournal: Journal of Testing\n\nA Test Title']


def _pubmed_article_xml(inner: str) -> str:
    return f'''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal>
                    <JournalIssue><PubDate><Year>2020</Year><Month>5</Month><Day>1</Day></PubDate></JournalIssue>
                </Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
            {inner}
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''


def test_journal_date_parsed_from_medline_date_field():
    # some PubDate fields give a free-text "MedlineDate" (e.g. "2019 Mar-Apr") instead of
    # separate Year/Month/Day elements
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><MedlineDate>2019 Mar-Apr</MedlineDate></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['year'] == 2019
    assert docs[0].infons['month'] == 3


def test_journal_date_medline_date_with_no_recognizable_year_or_month():
    # a MedlineDate string with no digits matching the year pattern and no recognizable
    # month name/abbreviation leaves both fields as None rather than crashing
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><MedlineDate>Unknown</MedlineDate></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['year'] is None
    assert docs[0].infons['month'] is None


def test_journal_date_out_of_range_year_is_dropped():
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><Year>1500</Year></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['year'] is None
    assert docs[0].infons['month'] is None


@pytest.mark.parametrize(
    'history_xml,expected_year',
    [
        # falls back to "entrez" when there's no "pubmed" status
        ('<PubMedPubDate PubStatus="entrez"><Year>2018</Year><Month>1</Month><Day>1</Day></PubMedPubDate>'
         '<PubMedPubDate PubStatus="medline"><Year>2019</Year><Month>1</Month><Day>1</Day></PubMedPubDate>', 2018),
        # falls back to whatever's available when neither "pubmed", "entrez" nor "medline" exist
        ('<PubMedPubDate PubStatus="accepted"><Year>2017</Year><Month>1</Month><Day>1</Day></PubMedPubDate>', 2017),
    ],
)
def test_pubmed_entry_date_status_fallbacks(history_xml, expected_year):
    xml = f'''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData>
            <ArticleIdList></ArticleIdList>
            <History>{history_xml}</History>
        </PubmedData>
    </PubmedArticle>'''
    # the journal date is deliberately empty, so it always loses the "which is earlier"
    # comparison and the entry date (and therefore the status-fallback logic under test)
    # is the one that gets used
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['year'] == expected_year


def test_pubmed_entry_date_skips_incomplete_history_entries():
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData>
            <ArticleIdList></ArticleIdList>
            <History>
                <PubMedPubDate PubStatus="pubmed"><Year>2020</Year></PubMedPubDate>
                <PubMedPubDate PubStatus="entrez"><Year>2018</Year><Month>1</Month><Day>1</Day></PubMedPubDate>
            </History>
        </PubmedData>
    </PubmedArticle>'''
    # the "pubmed"-status entry is missing Month/Day, so it's skipped entirely rather than
    # crashing, leaving only the "entrez" entry in play
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['year'] == 2018


def test_pubmed_entry_date_drops_out_of_range_entry_and_uses_medline_status():
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData>
            <ArticleIdList></ArticleIdList>
            <History>
                <PubMedPubDate PubStatus="received"><Year>1500</Year><Month>1</Month><Day>1</Day></PubMedPubDate>
                <PubMedPubDate PubStatus="medline"><Year>2016</Year><Month>1</Month><Day>1</Day></PubMedPubDate>
            </History>
        </PubmedData>
    </PubmedArticle>'''
    # the "received" entry's year (1500) is out of the plausible range and dropped, leaving
    # only the "medline"-status entry (no "pubmed"/"entrez" present) to fall back to
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['year'] == 2016


@pytest.mark.parametrize(
    'author_xml,expected_name',
    [
        ('<Author><LastName>Smith</LastName></Author>', 'Smith'),
        ('<Author><ForeName>Jo</ForeName></Author>', 'Jo'),
        ('<Author><CollectiveName>Some Consortium</CollectiveName></Author>', 'Some Consortium'),
    ],
)
def test_author_name_fallbacks(author_xml, expected_name):
    xml = f'''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
                <AuthorList>{author_xml}</AuthorList>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['authors'] == expected_name


def test_author_with_no_usable_name_raises():
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
                <AuthorList><Author><Initials>J</Initials></Author></AuthorList>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    with pytest.raises(RuntimeError):
        list(pubmedxml2bioc(StringIO(xml)))


def test_supplementary_mesh_concepts_extracted():
    xml = _pubmed_article_xml(
        '<SupplMeshList><SupplMeshName UI="C1" Type="Disease">Test Concept</SupplMeshName></SupplMeshList>'
    )
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['supplementary_mesh'] == 'C1|Disease|Test Concept'


def test_supplementary_mesh_concepts_are_structured_objects():
    xml = _pubmed_article_xml(
        '<SupplMeshList><SupplMeshName UI="C1" Type="Disease">Test Concept</SupplMeshName></SupplMeshList>'
    )
    doc = list(parse_pubmedxml(StringIO(xml)))[0]
    assert doc.supplementary_mesh == [SupplementaryMeshConcept(ui='C1', type='Disease', name='Test Concept')]


def test_chemicals_are_structured_objects_with_registry_number():
    xml = _pubmed_article_xml(
        '''<ChemicalList>
            <Chemical>
                <RegistryNumber>0</RegistryNumber>
                <NameOfSubstance UI="D000068877">Some Protein</NameOfSubstance>
            </Chemical>
        </ChemicalList>'''
    )
    doc = list(parse_pubmedxml(StringIO(xml)))[0]
    assert doc.chemicals == [Chemical(ui='D000068877', name='Some Protein', registry_number='0')]


def test_pubmedxml2bioc_chemicals_infons_includes_registry_number():
    xml = _pubmed_article_xml(
        '''<ChemicalList>
            <Chemical>
                <RegistryNumber>0</RegistryNumber>
                <NameOfSubstance UI="D000068877">Some Protein</NameOfSubstance>
            </Chemical>
        </ChemicalList>'''
    )
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['chemicals'] == 'D000068877|0|Some Protein'


_MESH_HEADING_XML = _pubmed_article_xml(
    '''<MeshHeadingList>
        <MeshHeading>
            <DescriptorName UI="D009369" MajorTopicYN="Y">Neoplasms</DescriptorName>
            <QualifierName UI="Q000378" MajorTopicYN="N">genetics</QualifierName>
            <QualifierName UI="Q000276" MajorTopicYN="Y">metabolism</QualifierName>
        </MeshHeading>
        <MeshHeading>
            <DescriptorName UI="D006801" MajorTopicYN="N">Humans</DescriptorName>
        </MeshHeading>
    </MeshHeadingList>'''
)


def test_mesh_qualifiers_are_nested_under_their_descriptor():
    doc = list(parse_pubmedxml(StringIO(_MESH_HEADING_XML)))[0]
    assert doc.mesh_headings == [
        MeshHeading(
            ui='D009369',
            name='Neoplasms',
            major_topic=True,
            qualifiers=[
                MeshQualifier(ui='Q000378', name='genetics', major_topic=False),
                MeshQualifier(ui='Q000276', name='metabolism', major_topic=True),
            ],
        ),
        MeshHeading(ui='D006801', name='Humans', major_topic=False, qualifiers=[]),
    ]


def test_pubmedxml2bioc_mesh_headings_infons_nests_qualifiers_under_descriptor():
    docs = list(pubmedxml2bioc(StringIO(_MESH_HEADING_XML)))
    assert docs[0].infons['mesh_headings'] == (
        'Descriptor|D009369|Y|Neoplasms~Qualifier|Q000378|N|genetics~Qualifier|Q000276|Y|metabolism'
        '\tDescriptor|D006801|N|Humans'
    )


_PUBLICATION_TYPE_XML = '''<PubmedArticle>
    <MedlineCitation>
        <PMID>99</PMID>
        <Article>
            <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
            <ArticleTitle>A Test Title</ArticleTitle>
            <PublicationTypeList>
                <PublicationType UI="D016428">Journal Article</PublicationType>
                <PublicationType UI="D013485">Research Support, N.I.H., Extramural</PublicationType>
            </PublicationTypeList>
        </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
</PubmedArticle>'''


def test_publication_types_are_structured_and_skip_list_still_applies():
    # generic NLM support-type labels (e.g. "Research Support, N.I.H., Extramural") are
    # still excluded, same as before this was restructured into objects
    doc = list(parse_pubmedxml(StringIO(_PUBLICATION_TYPE_XML)))[0]
    assert doc.publication_types == [PublicationType(ui='D016428', name='Journal Article')]


def test_pubmedxml2bioc_publication_types_infons_includes_ui():
    docs = list(pubmedxml2bioc(StringIO(_PUBLICATION_TYPE_XML)))
    assert docs[0].infons['publication_types'] == 'D016428|Journal Article'


def test_journal_title_missing_defaults_to_empty_string():
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    docs = list(pubmedxml2bioc(StringIO(xml)))
    assert docs[0].infons['journal'] == ''


def test_pubmedxml2txt_include_metadata_omits_header_when_all_fields_empty():
    # an empty <PMID> element has .text == None, same as every other optional field here,
    # so the metadata header ends up fully empty and should be omitted entirely
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID></PMID>
            <Article>
                <Journal><JournalIssue><PubDate></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    texts = list(pubmedxml2txt(StringIO(xml), sections=('title',), include_metadata=True))
    assert texts == ['A Test Title']


def test_pubmedxml2txt_drops_abstract_passage_left_empty_by_bracket_cleanup():
    # an AbstractText whose entire content is a bracket group with nothing else reduces to
    # "" after cleanup, and should be dropped rather than yielded as an empty passage
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title</ArticleTitle>
                <Abstract>
                    <AbstractText>Real content.</AbstractText>
                    <AbstractText>( )</AbstractText>
                </Abstract>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    texts = list(pubmedxml2txt(StringIO(xml), sections=('abstract',)))
    assert texts == ['Real content.']


def test_pubmedxml2txt_clear_empty_brackets_false_keeps_bracket_only_content():
    xml = '''<PubmedArticle>
        <MedlineCitation>
            <PMID>99</PMID>
            <Article>
                <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
                <ArticleTitle>A Test Title ( )</ArticleTitle>
                <Abstract>
                    <AbstractText>Real content ( ).</AbstractText>
                </Abstract>
            </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
    </PubmedArticle>'''
    texts = list(
        pubmedxml2txt(StringIO(xml), sections=('title', 'abstract'), clear_empty_brackets=False)
    )
    assert texts == ['A Test Title ( )\n\nReal content ( ).']


def test_fix_exponentials_defaults():
    import inspect

    assert inspect.signature(parse_pubmedxml).parameters['fix_exponentials'].default is True
    assert inspect.signature(pubmedxml2txt).parameters['fix_exponentials'].default is True
    assert inspect.signature(pubmedxml2bioc).parameters['fix_exponentials'].default is True


_EXPONENTIAL_XML = '''<PubmedArticle>
    <MedlineCitation>
        <PMID>99</PMID>
        <Article>
            <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
            <ArticleTitle>A Test Title</ArticleTitle>
            <Abstract><AbstractText>The speed of light is 3x10<sup>8</sup> m/s, first measured in the 1<sup>st</sup> century by <sup>14</sup>C dating pioneers.</AbstractText></Abstract>
        </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList></ArticleIdList></PubmedData>
</PubmedArticle>'''


def test_fix_exponentials_true_converts_exponent_via_pubmedxml2txt():
    texts = list(pubmedxml2txt(StringIO(_EXPONENTIAL_XML), sections=('abstract',), fix_exponentials=True))
    text = texts[0]
    assert '3x10^8 m/s' in text
    assert '1st century' in text
    assert '14C dating' in text


def test_fix_exponentials_false_leaves_exponent_glued_via_pubmedxml2txt():
    texts = list(pubmedxml2txt(StringIO(_EXPONENTIAL_XML), sections=('abstract',), fix_exponentials=False))
    text = texts[0]
    assert '3x108 m/s' in text
    assert '^' not in text
