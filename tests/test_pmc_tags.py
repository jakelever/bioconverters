from bioconverters.pmc_tags import PMC_IGNORE_TAGS, PMC_KEEP_TAGS, PMC_SPLIT_TAGS


class TestPmcTags:
    def test_ignore_tags(self):
        assert 'table' in PMC_IGNORE_TAGS
        assert 'table-wrap' in PMC_IGNORE_TAGS
        assert 'xref' in PMC_IGNORE_TAGS
        assert 'ext-link' in PMC_IGNORE_TAGS
        assert 'graphic' in PMC_IGNORE_TAGS

    def test_split_tags(self):
        assert 'p' in PMC_SPLIT_TAGS
        assert 'title' in PMC_SPLIT_TAGS
        assert 'sec' in PMC_SPLIT_TAGS

    def test_keep_tags(self):
        assert 'bold' in PMC_KEEP_TAGS
        assert 'italic' in PMC_KEEP_TAGS
        assert 'sup' in PMC_KEEP_TAGS
