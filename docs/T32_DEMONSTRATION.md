# T32 live demonstration

This is a bounded operational demonstration, not a population-accuracy claim.
All rows below are persisted V2 `mode=live` runs using SEC primary filing HTML;
their accession, source hash, stage output, provider activity, and comparison
records remain inspectable in the local workspace.

## Measured filings

| Ticker | Accession | Lines | Retained source | Findings latency | Evaluation latency | Provider usage | Outcome |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| MSFT | 0001193125-26-323660 | 1,970 | 10.61% | 2.46s | 9.30s | 16,241 in / 3,636 out | 3 scale-aware equivalents; 0 deterministic exact matches |
| FIX | 0001104659-26-017530 | 1,595 | 4.11% | 10.31s | 15.22s | 14,751 in / 2,583 out | 2 structured-fact misses; 1 ambiguous duplicate |
| FLR | 0001124198-26-000007 | 772 | 21.40% | 10.43s | 14.57s | 8,366 in / 1,326 out | 2 scale-aware equivalents; 2 ambiguous duplicates |
| LILA | 0001712184-26-000023 | 1,793 | 44.11% | 13.91s | 21.91s | 43,737 in / 4,332 out | 2 scale-aware equivalents; 1 unsupported comparison |
| DSGN | 0001193125-26-098491 | 1,501 | 0.96% | 17.12s | 20.65s | 2,694 in / 866 out | 2 invalid finding proposals rejected; 2 structured-fact misses |
| GDOT | 0001386278-26-000015 | 1,054 | 38.02% | 16.67s | 21.00s | 13,282 in / 1,894 out | 1 miss and 1 additional visible value |
| MFAN | 0001055160-26-000004 | 1,411 | 36.39% | 18.76s | 27.03s | 28,882 in / 3,610 out | 3 scale-aware equivalents; 1 ambiguous duplicate |
| SPGI | 0000064040-26-000013 | 1,194 | 38.16% | 12.76s | 18.44s | 18,884 in / 2,978 out | 2 scale-aware equivalents; 1 ambiguous duplicate |

The deterministic exact-match count was zero in these runs. That is a result to
inspect, not a success proxy: scale-aware Jev verdicts remain distinct, and the
misses/unsupported/ambiguous records are visible rather than repaired.

## Setup and two-minute verification

Set a real SEC contact plus Jev and LLM credentials in `.env`, then run:

```sh
uv run profitlab serve
```

Open `http://127.0.0.1:8000/v2/runs/v2-da452efc7988`. In the stage rail:

1. Open **Source** and confirm the SEC accession/provenance and numbered visible
   lines. Use a source link to open the preserved HTML anchor.
2. Open **Section score**, then **Chunk score**, and inspect a selected item and
   its source range.
3. Open **Findings**, follow an exact quote, and confirm the quote is highlighted
   on its one canonical core line.
4. Open **Facts** and then **Evaluate**. Confirm facts begin only after Findings,
   then inspect an explicit scale-aware equivalence, miss, or ambiguity.
5. Refresh the page. A completed stage stays persisted. For an interrupted run,
   use **Resume**; it continues from completed checkpoints rather than repeating
   them.

To inspect the XBRL isolation boundary, open a Jev request from **Section score**
or **Chunk score**. It contains only visible canonical text/navigation metadata;
it contains no `us-gaap:`, `contextRef`, `unitRef`, structured facts, or evaluation
records. The source viewer likewise represents sanitized visible HTML, not Inline
XBRL metadata.

## Fault evidence and limitations

- `ENSC` (`v2-20609e139c5f`) is a persisted live source failure; no later stage
  fabricated output.
- DSGN rejected two malformed/invalid finding proposals; none became findings.
- A live MSFT finding-type classification exceeded the 30,000-character context
  bound. The quote-validated finding remained published as `unresolved`, and the
  pipeline resumed through Facts/Evaluation. This is intentionally a bounded
  provider-overload outcome, not silent truncation.
- Durable cancellation/restart and invalid-quote paths are covered by the focused
  local contracts. No claim is made that this small, non-random sample estimates
  broad retrieval accuracy.
