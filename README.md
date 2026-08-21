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

Flags: `sections` (default `("title", "abstract", "article")`, also available: `subtitle`, `back`, `floating`), `include_metadata`, `passage_separator`, `trim_buggy_sentences`, `inject_citations` (default `False` here - see below), `clean_xrefs_in_brackets` (default `True` here - see below).

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
- `clean_xrefs_in_brackets` (default `False` here, unlike `pmcxml2txt`) - drop a reference that's wrapped in `[...]` or `(...)` on its own, since it reads as redundant clutter once cross-references are no longer blanked out - see below.

## Notes on text extraction

Text is extracted using [spans_and_trees](https://github.com/jakelever/spans_and_trees). Table content is omitted from extracted text. Overly long, unbroken runs of text are automatically trimmed to a maximum length (controlled by the `trim_buggy_sentences` flag).

## Cleaning up text with `clean_xrefs_in_brackets`

The text can contain some extra apparent clutter such as cross-references in parentheses and citations in square brackets. The `clean_xrefs_in_brackets` argument removes both, which can be a good idea for easier text processing. This is the default for `pmcxml2txt` and not for other methods.

Removing square brackets:

```
before: "...preferentially the active conformation[14]. Figure 5..."
after:  "...preferentially the active conformation . Figure 5..."
```

Removing cross-references wrapped in parentheses or square brackets:

```
before: "...reported in various solid cancers (Table 1). Analogous mutations..."
after:  "...reported in various solid cancers. Analogous mutations..."
```

This also handles a "double-wrapped" reference, where the xref's own bracketed content sits inside a further wrapper (e.g. `"([1])"`), by dropping the whole outer wrapper rather than leaving a dangling empty `"()"` behind.

The wrapper case only fires when the xref fills it on its own and the punctuation matches on both sides (both round or both square) - a mixed reference like `"(see Table 1)"`, a grouped one like `"(Figure 7 and Table 3)"`, or mismatched punctuation like `"[Table 1)"` is left untouched, since none of those read as a bare wrapper around the reference.

## Keeping some formatting

Some XML tags convey meaningful information and text looks horrible without the formatting they provide. For instance, a PMC article may contain `"3x10<sup>8</sup> m/s"`. If we remove those tags, it becomes `"3x108 m/s"` which is obviously wrong.

There are two options:

1. If you want plain text, tags are stripped automatically. But the `fix_exponentials` flag (default `True` for the `*2txt`/`*2bioc` methods) tries to spot cases where an exponential can be nicely cleaned up to `"3x10^8 m/s"`.
2. Or work with a modified XML format that keeps some of the formatting tags. `parse_pmcxml` does this, controlled by the `return_xml` boolean flag and `keep_tags`, which defaults to the `pmc_constants.PMC_KEEP_TAGS` list of tags. This list includes `<sup>`, `<sub>` and others.

## Getting citation info with `inject_citations`

PMC articles cite references with `<xref ref-type="bibr" rid="...">1</xref>`, where `rid` points at a `<ref>` in the back-matter `<ref-list>`. With `inject_citations=True` (the default for `parse_pmcxml`), the information is pulled from the bibliography so no cross-referencing is needed! The default is `False` for the other methods.

The referenced pub-ids (e.g. `pmid`, `doi`) and a `count` of how many references are added as attributes:

```xml
<!-- before -->
<xref ref-type="bibr" rid="r2 r3">2,3</xref>

<!-- after -->
<citation pmid="222|333" count="2">2,3</citation>
```

A grouped citation (multiple `rid`s, e.g. "[2,3]") gets its pub-id values `|`-joined, with `count` telling you how many references were bundled without needing to split them yourself.
