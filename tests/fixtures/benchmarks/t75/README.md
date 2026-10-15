# T75 live conversion smoke

`live-conversion-azz.json` retains one actual configured LLM response from
2026-10-15 (UTC timestamp and exact canonical source hash in the record).
The source is canonical line 147 from the retained real AZZ 2026 10-K fixture
`../t69/v2-6eca22455a84.json.gz`, whose SHA-256 is recorded.

Source assignment, eligibility and ranking were **controlled**, with no live JEV
calls. Only selected-bundle LLM conversion was live: one HTTP request, requested
`openai/gpt-5.6-luna`, returned `gpt-5.6-luna`, 2,034 input and 705 output tokens,
zero repair requests. Its two proposals passed deterministic source/span/sign and
fixed-concept checks. Unknown year/unit/scale/attribution remained null with
limitations. This source-only controlled selection deliberately supplies no
context; the returned values do **not** establish current-year financial accuracy.
This is adapter/validation compatibility evidence, not T77 quality or latency
acceptance and not an end-to-end replacement-pipeline run.

The run used temporary isolated storage that was removed on exit. The application
V2 namespace was untouched. The record contains the safe exact wire body, typed
raw proposals, actual model/usage and deterministic diagnostics. Traced transport
used the existing redactor, retry owner and one configured HTTP attempt. No
credential values are stored. Requested/returned model mismatch intentionally
prevents reusable cache insertion until actual identity can be pinned.

Default tests replay this saved response without external I/O. Controlled failure,
repair and SDK wire tests use synthetic outputs separately.
