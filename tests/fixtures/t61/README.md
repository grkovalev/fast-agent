# T61 saved SEC presentation data

Real Microsoft 2024 annual filing, accession `0000950170-24-087843`, filed
2024-07-30. Downloaded from SEC on 2026-10-13 using configured contact metadata.
URLs, retrieval times, source/fixture hashes and hash formats are recorded in
`provenance.json`.

- SUB: the original submission row.
- PRE/NUM: every same-accession row for NetIncomeLoss, EarningsPerShareDiluted,
  and WeightedAverageNumberOfDilutedSharesOutstanding, retaining comparative
  years, equity dimensions, and repeated statement presentations. TSV field
  order and values are unchanged; line endings are LF.
- Company Facts: original values for the supported concepts and same accession,
  projected from the live company dataset. JSON is pretty-printed.
- Index: the complete real SEC filing directory JSON, pretty-printed.

The quarterly ZIP itself is not checked in. Tests package these saved rows into
an in-memory ZIP to exercise the actual bounded parser and HTTP/storage path.
Controlled second taxonomy years, duplicates, missing data, failures, and corrupted
cache bytes are introduced by tests and are not represented as real SEC records.

NUM EPS uses `USD`, while Company Facts uses `USD/shares`. T61 deliberately records
missing presentation provenance rather than inferring a unit conversion. These
statement locations are supporting concept provenance, not verified canonical
filing lines or individual numeric-cell mappings.
