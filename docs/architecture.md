# Architecture

JevDroid separates observation, capability policy, inference, and execution. The
core imports neither UIAutomator2 nor provider-specific SDKs. Frozen dataclasses
describe screens, elements, actions, decisions, and run results.

| Module | Responsibility |
| --- | --- |
| `models` | Immutable domain values and validated run configuration |
| `interfaces` | Structural protocols for devices, providers, and event sinks |
| `sdk` | Public `JevDroid` session: connect, observe, decide, act, and run |
| `planning` | Shared bounded Jev decision primitive and `PlannedAction` |
| `android` | Authorized device selection, XML parser, standard ADB and persistent RPC |
| `policy` | Build action choices from host permissions and current package |
| `providers` | Persistent HTTP adapters with no inference retries |
| `budget` | Reserve maximum request cost, then settle actual token usage |
| `engine` | Observe, choose, validate, execute, count, and stop |
| `trace` | Opt-in, exclusive-create metadata traces |
| `cli` | Local diagnostics, runs, scrolling, and an offline demo |

## Run lifecycle

1. Read Android's accessibility hierarchy. With taps enabled, require two
   consecutive matching parsed observations. Persistent RPC polling has a
   two-second deadline; standard ADB checks up to three dumps.
2. Generate available actions from the package allowlist and capabilities.
3. Bound the serialized state size and reserve estimated maximum request cost.
4. Ask Jev one `choice` question using the supplied action IDs.
5. Settle reported input tokens. Reject malformed usage or unavailable action IDs.
6. Before a tap, read a stable fresh screen and require an exact match. Before a
   swipe or back action, require the same foreground package.
7. Execute the host-created action. Emit metadata and update gesture counts.
8. Stop on a model terminal choice, count limit, budget limit, repetition, error,
   cancellation, or maximum number of decisions.

## Execution boundaries

The host enforces permitted packages and action types. The model receives no
arbitrary command or coordinate interface. Package names are validated; launcher
activities are resolved locally and must belong to the requested package.

These are capability boundaries, not semantic guarantees. Enabling taps permits
clicking eligible elements, including controls whose effects the model may
misinterpret. Password-marked XML subtrees and hidden nodes are excluded, but
ordinary text may still be private. Treat visible text as untrusted input.

Android does not provide an atomic compare-and-click operation here. The screen
can change between validation and input. Stable snapshots reduce this race but
cannot eliminate it. An overlay inside the same package may also change swipe
behavior. RPC failure or cancellation can occur after the device received input;
such operations are not retried or counted as confirmed execution.

Scrolling tolerates changing video captions; it validates the package rather
than requiring an identical tree. A completed scroll task confirms issued and
successfully returned gestures, not new content, playback, or feed advancement.

## Extending the framework

Implement `Device.snapshot(stable=False) -> Screen` and
`Device.execute(action, screen) -> None` to supply another transport. Implement
`Provider.decide(state, actions, instructions) -> Decision` for another decision
service or an offline evaluator. Raise `JevDroidError` subclasses for operational
failures. Keep provider errors free of credentials and UI content.

The caller owns injected device and provider lifetimes; `JevProvider` is a context
manager. `JevDroid.connect()` manages the provider it creates automatically.
`Agent.run()` returns `RunResult` for expected operational failures. Configuration
and programming errors raise exceptions. Event sinks execute synchronously and
their unexpected failures propagate, preventing further actions.

## Provider compatibility

TypeSafe uses `POST https://api.typesafe.ai/v1/systemone`, a model in the body,
typed `questions`, and `usage.input_tokens`. Its request shape was checked against
`typesafe-sdk 0.6.0` in the original POC.

Vercel uses `POST https://ai-gateway.vercel.sh/v4/ai/evaluation-model`,
`ai-model-id: typesafe-ai/jev`, `ai-evaluation-model-specification-version: 4`,
`ai-gateway-protocol-version: 0.0.1`, `ai-gateway-auth-method: api-key`,
and `usage.inputTokens`. The request contract was checked against the official
[`GatewayEvaluationModel` implementation](https://github.com/vercel/ai/blob/main/packages/gateway/src/gateway-evaluation-model.ts)
in `@ai-sdk/gateway 4.0.86` / `ai 7.0.106`. This endpoint is experimental; the
native Python adapter is not an official Vercel Python SDK. No provider source
code is vendored.

HTTPX uses a 20-second timeout per network operation, disables redirects and
environment proxy configuration, and sends no automatic retry. The XML polling
deadline does not interrupt an in-flight UIAutomator2 RPC. These are not a strict
wall-clock deadline for the whole run.
