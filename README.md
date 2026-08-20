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

## Trim Sentences

You can also choose to truncate sentences to a maximum length. This is off by default. To turn this option off use the flag

```python
for doc in pmcxml2bioc('/path/to/pmc/xml/file.xml', trim_sentences=True):
    # do stuff with bioc doc
```

## Notes on text extraction

Text is extracted using [spans_and_trees](https://github.com/jakelever/spans_and_trees). Table content, in-text citation markers, and cross-references are omitted from extracted text. Inline formatting (bold/italic/sup/sub/etc.) is currently flattened to plain text.
