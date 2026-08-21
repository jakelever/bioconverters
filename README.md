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

Flags: `sections` (default `("title", "abstract", "article")`, also available: `subtitle`, `back`, `floating`), `include_metadata`, `passage_separator`, `trim_buggy_sentences`, `inject_citations`, `clean_numeric_citations`, `clean_xrefs_in_brackets`, `clear_empty_brackets`, `fix_exponentials` (cleanup flags described below).

### `pmcxml2bioc` - BioC documents

```python
from bioconverters import pmcxml2bioc

for doc in pmcxml2bioc('/path/to/pmc.xml'):
    # doc is a bioc.BioCDocument, with one passage per paragraph/section
    ...
```

### `parse_pmcxml` - raw dicts, with optional inline markup and citation control

```python
from bioconverters import parse_pmcxml

for article in parse_pmcxml('/path/to/pmc.xml'):
    # a PMCArticle dict: pmid, pmcid, doi, pub_year/month/day, journal, journal_iso,
    # and text_sources - a dict of title/subtitle/abstract/article/back/floating,
    # each a list of {"text": ..., "subsection": ...} passages
    ...
```

`parse_pmcxml` shares its defaults with `pmcxml2txt`/`pmcxml2bioc`, so behavior is consistent regardless of entry point. Notable flags:
- `return_xml` (default `False`) - return each passage's text as a marked-up XML string instead of plain text. Pair with `keep_tags` to control which tags survive, e.g. `"some <sup>1</sup>H text"`.
- `keep_tags` - which tags' markup is preserved inline when `return_xml=True`. Defaults to `pmc_constants.PMC_KEEP_TAGS` (`<sup>`, `<sub>`, `<italic>`, etc).
- `inject_citations` (default `False`) - resolve each in-text citation's `pmid`/`doi` and retag it to `<citation pmid="...">1</citation>`, kept in the output instead of dropped. Can't be combined with `clean_numeric_citations`.
- `clean_numeric_citations`, `clean_xrefs_in_brackets`, `clear_empty_brackets` (all default `True`) - see "Cleaning up text" below.

## Notes on text extraction

Text is extracted using [spans_and_trees](https://github.com/jakelever/spans_and_trees). Table content is omitted from extracted text. Overly long, unbroken runs of text are automatically trimmed to a maximum length (controlled by the `trim_buggy_sentences` flag).

## Cleaning up text

When turning PMC XML into plain text, we need to do some tidying to remove potential artefacts.

### Removing numeric citations with `clean_numeric_citations`

In-text citation markers (`<xref ref-type="bibr">`) are meaningless once printed as plain numbers, and can even glue onto the preceding word if the source XML has no separating space. The `clean_numeric_citations` argument (default `True`) blanks any bibr xref whose own text is just a number or numbers, bracketed or not (e.g. `"1"`, `"[1,2,3]"`, `"[1-3]"`), regardless of what surrounds it:

```
before: "...active in tuberculosis<sup>1</sup> and other diseases..."
after:  "...active in tuberculosis and other diseases..."
```

An author-date citation like `"Smith et al., 2020"` is left untouched, since it's still informative without the full reference resolved. `clean_numeric_citations` can't be combined with `inject_citations` (see below) - one deletes bibr citations, the other enriches them.

### Removing cross-references wrapped in parentheses with `clean_xrefs_in_brackets`

A cross-reference such as a figure or table is often the sole content of a `(...)`/`[...]` wrapper, which reads as redundant clutter once it's no longer resolvable. The `clean_xrefs_in_brackets` argument (default `True`) drops the reference together with its wrapper:

```
before: "...reported in various solid cancers (Table 1). Analogous mutations..."
after:  "...reported in various solid cancers. Analogous mutations..."
```

This only fires when the reference fills the wrapper on its own and the punctuation matches on both sides (both round or both square) - a mixed reference like `"(see Table 1)"`, a grouped one like `"(Figure 7 and Table 3)"`, or mismatched punctuation like `"[Table 1)"` is left untouched.

### Tidying up empty brackets with `clear_empty_brackets`

Blanking out a citation or cross-reference, or dropping an unrelated tag (e.g. `<ext-link>`) that happened to sit inside parentheses, can leave an empty wrapper behind. The `clear_empty_brackets` argument (default `True`) removes any `(...)`/`[...]`/`{...}` left containing no word characters:

```
before: "...as predicted by the tool (<ext-link>miRDB</ext-link>)..."
after:  "...as predicted by the tool..."
```

### Tidying up extra spaces

Whitespace is always collapsed to single spaces, so line breaks and indentation from the source XML, as well as any spaces left behind by blanked-out content, don't show up as irregular spacing in the final text. This isn't controlled by a flag.

## Handling lost formatting

Some XML tags convey meaningful information and text looks horrible without the formatting they provide. For instance, a PMC article may contain `"3x10<sup>8</sup> m/s"`. If we remove those tags, it becomes `"3x108 m/s"` which is obviously wrong.

There are two options:

1. If you want plain text, tags are stripped automatically. But the `fix_exponentials` flag (default `True`) tries to spot cases where an exponential can be nicely cleaned up (e.g. to `"3x10^8 m/s"`).
2. Work with a modified XML format that keeps some of the formatting tags, by passing `return_xml=True` to `parse_pmcxml`. Which tags survive is controlled by `keep_tags`, which defaults to the `pmc_constants.PMC_KEEP_TAGS` list of tags. This list includes `<sup>`, `<sub>` and others.

## Getting citation info with `inject_citations`

This relates to getting XML format (with `return_xml=True`). PMC articles cite references with `<xref ref-type="bibr" rid="...">1</xref>`, where `rid` points at a `<ref>` in the back-matter `<ref-list>`. With `inject_citations=True` (default `False`), the information is pulled from the bibliography so no cross-referencing is needed.

The referenced pub-ids (e.g. `pmid`, `doi`) and a `count` of how many references are added as attributes:

```xml
<!-- before -->
<xref ref-type="bibr" rid="r2 r3">2,3</xref>

<!-- after -->
<citation pmid="222|333" count="2">2,3</citation>
```

A grouped citation (multiple `rid`s, e.g. "[2,3]") gets its pub-id values `|`-joined, with `count` telling you how many references were bundled without needing to split them yourself.
