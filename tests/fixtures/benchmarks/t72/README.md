# T72 live source-line assignment smoke evidence

`live-lines-azz.json` retains one real network-enabled execution of the prepared
T72 request builder and assignment service on 2026-10-15. Input is the saved AZZ
canonical filing in the T69 archive; the record includes its exact fixture hash,
source ranges/text, typed plan/result, actual provider response, native usage and
redacted transport provenance. No Company Facts/evaluation data or LLM was used.
The successful command was `.venv/bin/python /tmp/live_t72.py`, with configured
credentials/proxy, isolated temporary repository, one request and a 60-second bound.
The source fixture's canonical hash is in each candidate/request source range.

Official API/model limits were rechecked at https://docs.typesafe.ai/api and
https://docs.typesafe.ai/models before dispatch. Actual model: `jev-1.13.0`;
3,395 input / 124 output tokens; executor elapsed 0.418004 seconds. Initial
sandboxed attempts failed; a temporary trace-sink method error was corrected.
The retained successful network-enabled request required sandbox escalation.

Six independent pairs: annual profit on lines 106/147, diluted EPS on 147/288/289,
and diluted shares on 291. Basic-only EPS is rejected; diluted EPS/shares supported;
the date-only line is rejected. Both concepts on mixed adjusted-calculation row
147 remain uncertain. This is a smoke check, not a labeled quality benchmark,
multi-concept accuracy proof or latency comparison. Tests use controlled answers
separately to prove that several concepts can be supported on one occurrence.
Default tests replay this exact recorded response without paid/network calls.

T69/T70 fixtures remain unchanged. Runtime activation is T76 and final held-out
quality/performance acceptance is T77. External captions absent from canonical
lines remain unavailable to this service.
