# Performance and cost accounting

## Measure the right boundary

An API decision is not an Android operation. A complete step includes XML reading,
network inference, fresh-screen validation, gesture execution, and possibly an
intentional delay. Application transitions and device load also matter.

`jevdroid benchmark` measures only sequential accessibility reads after device
connection. It excludes connection setup, inference, validation, and input.
Trace decisions report `ui_seconds` and `api_seconds`; execution events report
`validation_seconds` and `action_seconds`. The run result includes total elapsed
time after `Agent.run()` starts, including configured pauses.

## Historical POC observations

The predecessor was exercised on one Samsung Galaxy A05 over USB on September 18,
2026 (UTC). These figures were collected before packaging this framework:

| Observation | Result | Boundary |
| --- | --- | --- |
| Cold ADB hierarchy dump | Approximately 2.71–2.74 s | One observation |
| Persistent UIAutomator2, 10 reads | Median 229.2 ms, range 196–257 ms | Observation only |
| Settings → Display task | 6.57 s | Loop, excluding startup/key entry |
| Same navigation task | 4 decisions, 2 executed actions | One stale tap skipped |
| TikTok scroll decisions | Approximately 0.34–0.52 s | Remote inference only |

The navigation task used 7,307 input tokens, an estimate of $0.000306894 at
$0.042 per million input tokens. The scrolling run stopped after four gestures
because Vercel returned a rate limit. Neither is evidence of sustained throughput
or universal model accuracy. Raw device logs are deliberately not distributed.

## Packaged implementation smoke checks

The packaged implementation was also checked locally: five physical-device XML
reads had a 202.38 ms median, and the native Vercel adapter answered a small
classification request correctly (319 input tokens). A subsequent navigation
smoke test exercised launch, tap, stale-screen rejection, and rate-limit handling;
it stopped on HTTP 429 before completing the navigation goal. These smoke checks
are not a reliability benchmark.

## Budget model

Before each call, reserve `max_request_tokens × input_price_per_million / 1e6`
(65,536 tokens by default). Refuse the call if the reservation exceeds the
remaining local budget. On a valid response, replace the reservation with actual
reported input tokens. Unknown usage retains the reservation and stops the run.

`input_tokens` includes an outstanding reservation, if any; `reserved_tokens`
identifies that unconfirmed portion. The estimate is not an invoice or a balance
lookup. Pricing, fees, discounts, model context, and provider behavior can change.
Review your provider's pricing and configure `--input-price` accordingly.

The byte payload cap helps bound observations but is not a tokenizer or a proof
of token count. Do not lower the maximum token reservation without knowing the
model's limits. If usage exceeds the reservation, account for it and stop; money
already spent cannot be recovered by a local guard.
