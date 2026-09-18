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

## Measured decisions and operations

Measurements were collected on one Samsung Galaxy A05 over USB on September 18,
2026 (UTC), using the POC and Jev through Vercel AI Gateway. The framework smoke
checks are reported separately below.

### Jev decisions

Four consecutive scroll decisions had the following API latencies and estimated
input-token costs. The initial app-launch decision is excluded from this group.

| Decision | API latency | Estimated cost |
| --- | --- | --- |
| Scroll 1 | 343 ms | $0.000079506 |
| Scroll 2 | 519 ms | $0.000049350 |
| Scroll 3 | 345 ms | $0.000051156 |
| Scroll 4 | 434 ms | $0.000052626 |
| **Median latency / mean cost** | **389.5 ms** | **$0.0000581595** |

At the same average token usage and input rate, **1,000 similar decisions would
cost approximately $0.05816**. This is a linear cost projection, not a measured
1,000-decision run. A later request hit a provider rate limit, so the run ended
after four scrolls. The 1,196 ms initial launch decision cost an estimated
$0.000028812; including it, the five successful requests averaged 567.4 ms and
$0.000052290 per decision. No sustained request rate was measured.

### Android operations and complete task

A completed Settings → Display navigation task produced:

| Metric | Result | Measurement boundary |
| --- | --- | --- |
| Launch Settings | 88 ms | Device action execution only |
| Tap the navigation target | 170 ms | Device action execution only |
| Jev inference | 2.626 s total | Four API decisions |
| Complete navigation task | 6.571 s | Observation, inference, validation, and execution; excludes startup/key entry |
| Estimated task cost | $0.000306894 | 7,307 input tokens across four decisions |
| Estimated cost per decision | $0.0000767235 | Task cost divided by four API decisions |
| Estimated cost per executed action | $0.000153447 | Task cost amortized over two executed Android actions |

The four decisions included a stale tap that was skipped and a terminal DONE
choice, as well as the two executed actions. The per-action cost therefore
includes all inference needed for the task. The 88 ms and 170 ms figures measure
only execution after a decision: they are not full observe/decide/act cycle times.

### Cost calculation

Estimated inference cost is `reported input tokens × $0.042 / 1,000,000`.
Per-scroll costs above are the differences between consecutive cumulative cost
entries. The four scroll decisions used 5,539 input tokens in total:

```text
5,539 × $0.042 / 1,000,000 = $0.000232638
$0.000232638 / 4 decisions = $0.0000581595 per decision
```

These estimates use the configured input-token rate for the trials, not a balance
lookup or invoice. The samples do not establish model reliability or performance
on other workloads. Raw device logs and UI content are not distributed.

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
