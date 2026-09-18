# CLI reference

All commands support `--help`. `jevdroid --version` prints the package version.

| Command | Effect | Calls Jev? |
| --- | --- | --- |
| `doctor` | Find ADB and list connected device states | No |
| `inspect` | Print the active accessibility observation locally | No |
| `benchmark --samples 10` | Measure sequential accessibility reads | No |
| `demo` | Run a deterministic fake navigation task | No |
| `run GOAL --package PACKAGE` | Execute a bounded agent task | Yes |
| `scroll --package PACKAGE --count 5` | Execute a bounded scrolling task | Yes |

`inspect`, `benchmark`, `run`, and `scroll` accept `--serial` when more than one
device is attached. Diagnostic output may contain your serial number or visible
UI text; do not post it publicly without reviewing it.

## Run and scroll options

| Option | Default | Purpose |
| --- | --- | --- |
| `--package` | Required | Allowed application package |
| `--provider` | `vercel` | `vercel` or `typesafe` |
| `--model` | Provider default | Jev model ID override |
| `--max-steps` | `20` | Hard ceiling on decisions, including skipped actions |
| `--budget` | `0.10` | Local estimated USD ceiling |
| `--input-price` | `0.042` | Estimated USD per million input tokens |
| `--trace` | Off | Path for a new metadata-only JSONL trace |
| `--json` | Off | JSON lines for decisions, actions, and final result |

Navigation supports `--allow-taps`, `--allow-back`, and `--allow-checkable`
(requires taps). All are off by default. Scroll supports `--count` (default 5)
and `--pause` (default 0.5 seconds between gestures, excluding inference time).
The count must fit inside `--max-steps`; allow extra decisions for launching or waiting.

The hidden interactive prompt is preferred for local experiments. Noninteractive
jobs use `AI_GATEWAY_API_KEY` or `TYPESAFE_API_KEY`. JevDroid does not load `.env`
automatically, accept key arguments, or write credentials to disk.

## Result and exit codes

- `0`: `completed` gesture count, `model_done`, or successful diagnostic/demo.
- `2`: incomplete run, model stop, limit, cancellation during a run, or operational
  error returned by the agent. Inspect the final status.
- `1`: setup, credential, configuration, or local I/O error.
- `130`: interrupt before/after the agent loop.

Argument parsing errors also use exit code 2. JSON mode's final event contains
status and counts but no free-form error body. A nonzero exit requires attention;
it is never automatically retried.
