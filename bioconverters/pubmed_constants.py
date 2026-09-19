# AbstractText's content model (see pubmed_*.dtd) is (%text; | mml:math | DispFormula)*, so a
# MathML formula can appear inline as bare <mml:math>, or block-level wrapped in <DispFormula>
# (whose own content model is just (mml:math), so ignoring DispFormula alone already blanks a
# wrapped formula's content too - the standalone-<mml:math> entry below is only needed for the
# unwrapped, inline case).
#
# xml.etree.ElementTree expands a namespaced tag like "mml:math" to Clark notation
# ("{namespace-uri}localname") once it sees the element's xmlns:mml declaration, so the ignore
# set needs the expanded form, not the literal "mml:math" prefix string - confirmed against a
# real PMC/PubMed MathML-bearing article (a raw "mml:math"/"tex-math" string check on
# PMC_IGNORE_TAGS - the PMC equivalent of this file - never matches for the same reason).
_MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML"

PUBMED_IGNORE_TAGS = {
	"DispFormula",
	"{%s}math" % _MATHML_NAMESPACE,
}

PUBMED_SPLIT_TAGS = set()

PUBMED_KEEP_TAGS = {
	"i",
	"b",
	"u",
	"sup",
	"sub",
}
