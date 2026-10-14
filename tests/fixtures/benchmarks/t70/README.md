# T70 real mixed JEV response fixtures

Captured 2026-10-14 through the configured TypeSafe proxy with configured
credentials, pinned `jev-1.13.0`. Input is retained AZZ canonical line 291 from the
T69 archive; its exact hash/range is in `live-mixed-azz.json`.

`live-mixed-azz.json` retains the successful packed request, real response,
redacted transport traces and native usage (491 input/41 output tokens).
Measured executor time 0.2252s; wrapper 0.2475s. It predates the final additional
plan-index/omitted-items fields; request/response fixtures remain exact.

`live-rounded-response.json` retains a preceding real HTTP 200 from redacted
transport diagnostics, including original provider request ID/time. Initial
validation rejected its independent rounding: score 2.12 versus 2.13 calculated
from displayed two-decimal probabilities. Its usage is another 491/41 tokens;
local elapsed measurement was not retained. Rounding validation now accepts it.

One earlier network-enabled attempt raised ProviderFailure without retained body;
its usage is unavailable. Two sandbox network attempts failed before escalation.
These probes are API compatibility evidence, not complete billing totals,
Findings-stage quality acceptance, or comparable latency benchmarks. No paid
calls run in default tests; replay tests are not live measurements.

Official contract/limits verified before probes:
https://docs.typesafe.ai/api and https://docs.typesafe.ai/models.
32 MiB body, 64k request / 32k per-question context, Score 2–10 levels.
No long-context header enabled. Prepared executor uses conservative whole-request
estimates; native usage comes only from the retained response.

- `live-mixed-azz.json` SHA-256 `8c4aeb1108c8cb7aac85f3b75cb21a5b0a74ba4796b60927c18f76b74ed97ddf`.
- `live-rounded-response.json` SHA-256 `5681011d2cec22910a1c2ea0f366ec9bbec927dbb041d432672c307a44c3b0b3`.
