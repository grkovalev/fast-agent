# Two-company fact-source acceptance

`aapl-20240928.htm.gz` is the complete, unchanged Apple 2024 10-K, accession
`0000320193-24-000123`, acquired with the configured SEC client on 2026-10-14.
Gzip uses mtime=0. `provenance.json` records the original decompressed HTML hash,
URL and acquisition time. `company_facts.json` retains unmodified same-accession
records for net income, diluted EPS and diluted shares, including comparative
periods and all returned units. Its fixture hash and the full parsed response's
hash (`json.dumps(response, sort_keys=True)`) are separate.

The gate also uses unchanged Microsoft 2024 fixtures in `../t62` and `../t61`.
Both companies have four net-income, two EPS and two share-count occurrences
for each of the 2024 and 2023 fiscal periods: 32 verified occurrences total.

| Company / metric | Canonical rows (both years) | 2024 displayed cell | Display scale |
| --- | --- | --- | --- |
| Apple net income | 123, 132, 207, 249 | 93,736 | Millions (6) |
| Apple diluted EPS | 126, 255 | 6.08 | Per share (0) |
| Apple diluted shares | 129, 253 | 15,408,095 | Thousands (3) |
| Microsoft net income | 826, 840, 902, 1102 | 88,136 | Millions (6) |
| Microsoft diluted EPS | 829, 1108 | 11.80 | Per share (0) |
| Microsoft diluted shares | 832, 1105 | 7,469 | Millions (6) |

The audit checks raw concept/context/entity/dimensionless period and unit,
exact Decimal transformation, visible statement scale captions, canonical quote,
distinct comparative cells, sanitized cell locator and line anchor. Saved Facts,
Evaluate and full mapping routes are checked without network or mapper calls.
Unscaled net-income findings, exact EPS findings and missing share findings are
controlled acceptance inputs using real quotes, not recorded model outputs.
A deliberately incompatible EUR comparator verifies an unavailable mapping with
diagnostics and no source link; it is not an actual SEC fact. Existing T62/T63
gates retain hidden-only, ambiguous, unsaved historical and source-disagreement
coverage. No new PRE/NUM archive was acquired for Apple; exact Inline mapping is
independent of optional presentation enrichment.

Apple places statement scale captions in `div/span` elements outside tables.
They survive in sanitized HTML and are audited directly, but some are absent from
canonical numbered lines and nearby header previews. Recorded Inline scale remains
exact. This acceptance does not change source numbering or claim complete caption
coverage in those previews. The user confirmed cell/year/scale visibility on the
running UI on 2026-10-14; no itemized visual observations were supplied.
