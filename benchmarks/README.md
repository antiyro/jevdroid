# JevDroid evaluations

Real Jev API calls on synthetic decision tasks and stateful navigation scenarios,
plus a separate Android navigation trial. Results below were collected on
September 19, 2026 using `typesafe-ai/jev` through Vercel AI Gateway.

## Decision results

| Metric | Observed result |
| --- | --- |
| Correct decisions | 44 / 56 (78.6%) |
| Cases correct in both presentations | 22 / 28 |
| API latency, median / p95 | 314 / 497 ms |
| Estimated cost per answered decision | $0.0000337425 |
| Estimated cost of 56 answered decisions | $0.00188958 |
| Estimated decisions per $1 at this workload | ~29,600, including incorrect answers |

| Category | Correct / answered |
| --- | --- |
| Arithmetic | 0 / 8 |
| Conditional choices | 10 / 10 |
| Constraints | 14 / 18 |
| Similar-label disambiguation | 4 / 4 |
| Recovery | 4 / 4 |
| State awareness | 10 / 10 |
| Untrusted UI text | 2 / 2 |

The failures occurred in both presentations of six cases: unit pricing, checkout
totals, discounted totals, overnight journey duration, arrival deadlines, and
arrival/transfer constraints with a price tie-breaker. For example, Jev selected
a $24 total over a $22 total in the checkout task.

These results support fast selection for the tested conditional and state-reading
tasks. They do not establish reliable arithmetic, general reasoning ability, or a
ranking against other models. No comparison model was run.

## Stateful navigation

Success requires Jev to select `DONE` on the designated terminal screen within
eight decisions. Reaching that screen without terminating does not pass.

| Simulated scenario | Result | Decisions |
| --- | --- | --- |
| Find installed Android version | Stopped on launcher | 1 |
| Select latest final English invoice and check total | Passed | 3 |
| Skip optional setup and open Notifications | Repeatedly left the target screen; step limit | 8 |

The Android-version fixture exposes an opaque package name on its launcher,
without a Settings app label. Its failure is confounded by that fixture ambiguity;
it cannot isolate navigation or reasoning quality. The invoice fixture contains
only a matching total, so passing it alone cannot demonstrate arithmetic ability.
No simulated forbidden transition was taken.

The separate physical Android trial did not finish within eight decisions. It
executed a scroll and a tap, then repeatedly requested the Settings app launch.
ADB inspection found the screen asleep with the keyguard showing; waking it did
not dismiss the lock. This is an environment-confounded failure, not evidence of
successful device navigation. The runner's physical completion check also uses
package identity plus brightness-related text, a weaker check than verifying the
actual brightness control. No physical success rate is claimed.

## Reproduce

Run from a repository checkout with the development dependencies installed:

```bash
pip install -e ".[dev]"
python -m benchmarks.run --check --output /tmp/unused.json
python -m benchmarks.run --output /tmp/decisions.json --budget 0.01 --interval 0.5
python -m benchmarks.episodes --output /tmp/episodes.json --interval 0.5
```

The runners prompt for a hidden API key, or read `AI_GATEWAY_API_KEY`. The episode
runner caps each scenario at an estimated $0.01. Add `--phone` only with Android
support installed and one connected, unlocked test device: it permits taps,
scrolling, app launch and Back in Settings to find display brightness controls.
The goal prohibits changing settings, but this is a model instruction rather than
an enforced read-only device mode.
Use `--only-phone` to run that trial separately, retaining any earlier report.

Resume an interrupted decision run into a new report:

```bash
python -m benchmarks.run --resume-from /tmp/decisions.json \
  --output /tmp/decisions-resumed.json --budget 0.01 --interval 0.5
```

Resume preserves every answered trial, including incorrect answers, and the
previous budget accounting. It requires matching corpus/instruction hashes and
seed. Errors stop the runner; there are no automatic retries. Increase the
interval if your provider rate-limits requests.

## Scope and accounting

The corpus contains 28 manually authored cases. Each is evaluated once in its
original presentation and once with reordered UI elements and action choices,
using seed 42. These are 28 distinct cases, not 56 independent tasks. The expected
answer is remapped after reordering and is never sent to Jev. The SDK's regular
instructions, policy and planning function produce the requests. The fixtures and
reference answers were fixed before this campaign; no failed answer was replaced
with a later successful retry.

Latency measures the provider call, including network time, but excludes request
pacing, Android observation and action execution. It is not a throughput or full
automation timing measurement. Cost uses reported input tokens at the framework's
configured $0.042 per million; it is an estimate, not a billing reconciliation.

An initial free-tier run answered five trials before an HTTP 429. After credits
were purchased, the remaining 51 were evaluated with 0.5-second request spacing.
The complete report retains the five earlier answers and the 429, for 57 attempts
and 56 answers. The unresolved error retains a conservative 65,536-token budget
reservation ($0.002752512): the report's $0.004642092 including reservation is
not the estimated cost of the successful API responses alone. The two decision
reports overlap and must not be summed.

The navigation campaign used 30-second request spacing. Its simulator is a fixed
transition graph, not Android or an emulator. These small authored samples and a
single run per presentation are insufficient for broad reliability claims.

## Artifacts

- [Decision cases](decisions.json) and [stateful fixtures](episodes.json)
- [Complete decision report](results/jev-decisions-v1-complete.json)
- [Initial interrupted report](results/jev-decisions-v1.json)
- [Navigation report](results/jev-episodes-v1.json)

Reports contain decision metadata, synthetic labels and timings, without API keys,
device identifiers, screenshots or real-device UI dumps.
