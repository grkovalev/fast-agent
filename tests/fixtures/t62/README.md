# T62 retained primary filing

`msft-20240630.htm.gz` contains the complete, unchanged Microsoft 2024 primary
Inline XBRL filing (accession `0000950170-24-087843`). Downloaded through the
configured SEC client on 2026-10-13. `provenance.json` records the source URL,
retrieval time, and SHA-256 of the **decompressed original HTML bytes**.
Gzip is a deterministic storage encoding (mtime=0), not a source transformation.

Company Facts and supporting SEC PRE/NUM/SUB data are the real same-accession
projections in `../t61`. The mapping gate checks annual net income, diluted EPS,
and diluted shares, including comparative 2023 cells. Selected 2024 occurrences:

| Metric | Canonical lines | Visible cells | Scale |
| --- | --- | --- | --- |
| Net income | 826, 840, 902, 1102 | 88,136 | 6 |
| Diluted EPS | 829, 1108 | 11.80 | 0 |
| Diluted shares | 832, 1105 | 7,469 | 6 |

Line numbers are from the existing `visible-html-1` canonicalizer; each exact
cell also retains a distinct sanitized DOM locator and verified line anchor.
EPS maps without a PRE match: the T61 literal-unit mismatch does not constrain
Inline XBRL mapping.

Negative sign/comma-decimal, hidden-only, unsupported continuations/formats,
dimensions, altered source bytes/text/HTML, and projection overflow are controlled
test cases. They are not represented as real SEC records or live pipeline results.

Numeric transform definitions used by the bounded mapper:
[XBRL Transformation Registry 4](https://www.xbrl.org/Specification/inlineXBRL-transformationRegistry/REC-2020-02-12/inlineXBRL-transformationRegistry-REC-2020-02-12.html),
[Registry 3](https://www.xbrl.org/Specification/inlineXBRL-transformationRegistry/REC-2015-02-26/inlineXBRL-transformationRegistry-REC-2015-02-26.html).
The mapper supports dot/comma decimals and zero transforms in recognized registry
namespaces. Unknown transforms and numeric continuation attributes stay unresolved.
