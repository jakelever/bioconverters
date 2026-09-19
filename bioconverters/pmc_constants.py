# xml.etree.ElementTree expands a namespaced tag like "mml:math" to Clark notation
# ("{namespace-uri}localname") once it sees the element's xmlns:mml declaration, so the ignore
# set needs the expanded form below, not a literal "mml:math" prefix string (which is what
# this used to say, and never matched anything as a result - confirmed against a real PMC
# article with MathML formulas). disp-formula/inline-formula already cover a formula wrapped
# in one of those, since ignoring a tag blanks its whole span, descendants included - the
# standalone entry below is for a bare <mml:math>, which JATS also allows directly inside <p>
# and several other elements, not just the two formula wrappers.
_MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML"

PMC_IGNORE_TAGS = {
	"table",
	"table-wrap",
	"disp-formula",
	"inline-formula",
	"ref-list",
	"bio",
	"ack",
	"graphic",
	"media",
	"tex-math",
	"{%s}math" % _MATHML_NAMESPACE,
	"object-id",
	"ext-link",
}

PMC_SPLIT_TAGS = {
	"table",
	"table-wrap",
	"title",
	"p",
	"sec",
	"break",
	"def-item",
	"list-item",
	"caption",
}

PMC_KEEP_TAGS = {
	"sup",
	"sub",
	"italic",
	"bold",
	"underline",
	"monospace",
	"sc",
	"overline",
	"strike",
}
