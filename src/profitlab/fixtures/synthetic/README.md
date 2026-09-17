All files are synthetic; DEMO is not a real SEC issuer. Four annual calendar years 2022–2025. The two-years scenario uses only 2024 and 2025.

Expected annual common income (USD millions): 100, 120, 150, 180. Diluted EPS (USD/share): 1.00, 1.25, 1.60, 2.00. Diluted shares (millions): 100, 96, 93.75, 90. Gold JSON is test-only at tests/fixtures/synthetic/gold.json. No runtime service reads gold.

`chunk-context.html` is synthetic size/boundary test material appended only to
2025 sources in T06 demos. It contains 25 prose blocks, a 160-row table and an
1,800-row table. Its illustrative values are not financial extraction gold.

T10 adds amended-filing variants `restatement.html` and `split-adjusted.html`.
They include explicit comparative fiscal intervals and table/row/year adjustment
labels. The conflict scenario changes only the amendment's main 2025 EPS from
2.00 to 2.25 without an adjustment label. These are synthetic source inputs, not
gold numbers passed to selection. Split-adjusted GAAP remains distinct from
non-GAAP adjusted earnings.

T11 `losses` transforms saved synthetic common income/EPS rows before parsing:
2022 -100/-1.00, 2023 -50/-0.50, 2024 0/0.00, 2025 180/2.00
(income USD millions, EPS USD/share). This exercises loss narrowing and
zero-to-profit transitions without network calls or runtime gold answers.
