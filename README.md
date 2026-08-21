# BioConverters Package

[![PyPi](https://img.shields.io/pypi/v/bioconverters.svg)](https://pypi.org/project/bioconverters/) [![License](https://img.shields.io/pypi/l/bioconverters.svg)](https://www.tldrlegal.com/license/mit-license) [![build](https://github.com/jakelever/bioconverters/actions/workflows/tests.yml/badge.svg)](https://github.com/jakelever/bioconverters/actions) [![codecov](https://codecov.io/gh/jakelever/bioconverters/branch/master/graph/badge.svg)](https://codecov.io/gh/jakelever/bioconverters)

The bioconverters package converts PubMed and PMC XML into plain text or BioC format.

## Install

```bash
pip install bioconverters
```

## PubMed

### `pubmedxml2txt` - plain text, one string per article

```python
from bioconverters import pubmedxml2txt

for text in pubmedxml2txt('/path/to/medline.xml', include_metadata=True):
    # text is a single string, e.g. "pmid: 123\njournal: ...\n\nTitle\n\nAbstract..."
    ...
```

Flags: `sections` (default `("title", "abstract")`), `include_metadata` (prepend a pmid/doi/year/journal/authors header), `passage_separator` (default `"\n\n"`).

### `pubmedxml2bioc` - BioC documents

```python
from bioconverters import pubmedxml2bioc

for doc in pubmedxml2bioc('/path/to/medline.xml'):
    # doc is a bioc.BioCDocument, with title/abstract as separate passages
    ...
```

### `parse_pubmedxml` - raw dicts, for everything else

```python
from bioconverters import parse_pubmedxml

for article in parse_pubmedxml('/path/to/medline.xml'):
    # a PubMedArticle dict: pmid, pmcid, doi, pub_year/month/day, title, abstract,
    # journal, journal_iso, authors, chemicals, mesh_headings, supplementary_mesh,
    # publication_types
    ...
```

Use this if you need fields `pubmedxml2txt`/`pubmedxml2bioc` don't expose, like authors, MeSH headings or chemicals.

## PMC

### `pmcxml2txt` - plain text, one string per article/sub-article

```python
from bioconverters import pmcxml2txt

for text in pmcxml2txt('/path/to/pmc.xml', include_metadata=True):
    # text is a single string, e.g. "pmid: 123\njournal: ...\n\nTitle\n\nAbstract...\n\nBody..."
    ...
```

Flags: `sections` (default `("title", "abstract", "article")`, also available: `subtitle`, `back`, `floating`), `include_metadata`, `passage_separator`, `trim_buggy_sentences`, `inject_citations` (default `False` here - see below), `clean_xrefs_in_parentheses`.

### `pmcxml2bioc` - BioC documents

```python
from bioconverters import pmcxml2bioc

for doc in pmcxml2bioc('/path/to/pmc.xml'):
    # doc is a bioc.BioCDocument, with one passage per paragraph/section
    ...
```

### `parse_pmcxml` - raw dicts, with inline markup and citation control

```python
from bioconverters import parse_pmcxml

for article in parse_pmcxml('/path/to/pmc.xml'):
    # a PMCArticle dict: pmid, pmcid, doi, pub_year/month/day, journal, journal_iso,
    # and text_sources - a dict of title/subtitle/abstract/article/back/floating,
    # each a list of {"text": ..., "subsection": ...} passages
    ...
```

Notable flags:
- `keep_tags` - preserve inline markup (bold/italic/sup/sub/etc.) in each passage's text, e.g. `"some <sup>1</sup>H text"`. Pass `set()` for plain text.
- `inject_citations` (default `True`) - resolve each in-text citation's `pmid`/`doi` and retag it to `<citation pmid="...">1</citation>`, kept in the output instead of dropped.
- `clean_xrefs_in_parentheses` (default `True`) - drop a purely-parenthetical reference like `"(Table 1)"` entirely, since it reads as redundant clutter once cross-references are no longer blanked out.

## Notes on text extraction

Text is extracted using [spans_and_trees](https://github.com/jakelever/spans_and_trees). Table content is omitted from extracted text. Overly long, unbroken runs of text are automatically trimmed to a maximum length.

## `inject_citations`

PMC articles cite references with `<xref ref-type="bibr" rid="...">1</xref>`, where `rid` points at a `<ref>` in the back-matter `<ref-list>`. With `inject_citations=True` (the default for `parse_pmcxml`), each of these is resolved against its `<ref>` and retagged to `<citation>`, with the referenced pub-ids (e.g. `pmid`, `doi`) and a `count` of how many references it bundles added as attributes:

```xml
<!-- before -->
<xref ref-type="bibr" rid="r2 r3">2,3</xref>

<!-- after -->
<citation pmid="222|333" count="2">2,3</citation>
```

A grouped citation (multiple `rid`s, e.g. "[2,3]") gets its pub-id values `|`-joined, with `count` telling you how many references were bundled without needing to split them yourself. Citations are kept in the output like this instead of being dropped like other ignored tags - the marker text ("2,3") stays visible either way, so this mainly matters if you want the `pmid`/`doi`/`count` attributes; they don't survive `return_xml=False`'s plain-text output, which is why `pmcxml2bioc` and `pmcxml2txt` both default `inject_citations` to `False` (no point paying for the ref-list lookup if nothing will show it).

## `clean_xrefs_in_parentheses`

Cross-references like `<xref ref-type="fig">Table 1</xref>` are kept in extracted text (fig/table/section labels need to survive for sentences that read them as a word, e.g. "shown in Table 1"). But when a reference is the *entire* content of a parenthetical, e.g. `"(Table 1)"`, it usually reads as redundant clutter rather than as part of the sentence. With `clean_xrefs_in_parentheses=True` (the default), that whole parenthetical is dropped:

```
before: "...reported in various solid cancers (Table 1). Analogous mutations..."
after:  "...reported in various solid cancers. Analogous mutations..."
```

This only fires when the xref fills the parentheses on its own - a mixed reference like `"(see Table 1)"` or a grouped one like `"(Figure 7 and Table 3)"` is left untouched, since the reference reads as part of the sentence in those cases.
