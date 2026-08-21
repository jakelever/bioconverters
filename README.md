# BioConverters Package

![PyPi](https://img.shields.io/pypi/v/bioconverters.svg) ![build](https://github.com/jakelever/bioconverters/workflows/build/badge.svg?branch=master) [![codecov](https://codecov.io/gh/jakelever/bioconverters/branch/master/graph/badge.svg)](https://codecov.io/gh/jakelever/bioconverters)

The bioconverters packages contains functions for converting PubMed and PMC style XML into BioC format.

## Getting Started

Install with pip

```bash
pip install bioconverters
```

Now you are ready to start converting files. Assuming you already have a file containing PMC formatted XML

```python
from bioconverters import pmcxml2bioc

for doc in pmcxml2bioc('/path/to/pmc/xml/file.xml'):
    # do stuff with bioc doc
```

## Notes on text extraction

Text is extracted using [spans_and_trees](https://github.com/jakelever/spans_and_trees). Table content, in-text citation markers, and cross-references are omitted from extracted text. Overly long, unbroken runs of text are automatically trimmed to a maximum length.

`pmcxml2bioc` returns plain text. For inline formatting (bold/italic/sup/sub/etc.) preserved as markup, use `parse_pmcxml` directly, which returns `PMCArticle` dicts and accepts a `keep_tags` parameter:

```python
from bioconverters import parse_pmcxml

for doc in parse_pmcxml('/path/to/pmc/xml/file.xml'):
    # each passage's text may contain inline tags, e.g. "some <sup>1</sup>H text"
    ...
```

If you just want plain text (no BioC structure), use `pmcxml2txt`/`pubmedxml2txt`, which yield one string per article - the title/abstract/body passages joined together, with an optional metadata header:

```python
from bioconverters import pmcxml2txt

for text in pmcxml2txt('/path/to/pmc/xml/file.xml', include_metadata=True):
    # text is a single string, e.g. "pmid: 123\njournal: ...\n\nTitle\n\nAbstract...\n\nBody..."
    ...
```
