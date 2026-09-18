"""Native Python adapters for TypeSafe and Vercel's evaluation protocol."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Self

import httpx

from jevdroid.errors import ProviderError
from jevdroid.models import Action, Decision

ProviderName = Literal["vercel", "typesafe"]
ENDPOINTS = {
    "vercel": "https://ai-gateway.vercel.sh/v4/ai/evaluation-model",
    "typesafe": "https://api.typesafe.ai/v1/systemone",
}
MODELS = {"vercel": "typesafe-ai/jev", "typesafe": "jev-1.13.0"}


class JevProvider:
    """Persistent HTTP client, explicit timeout, no implicit retries or redirects.

    Vercel's evaluation API is experimental. Its adapter is isolated here and
    contract-tested against the request shape in the official AI SDK.
    """

    def __init__(
        self,
        api_key: str,
        *,
        provider: ProviderName = "vercel",
        model: str | None = None,
        timeout: float = 20,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if provider not in ENDPOINTS:
            raise ValueError("Unknown Jev provider.")
        if not api_key.strip():
            raise ValueError("An API key is required.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive.")
        self.provider = provider
        self.model = model or MODELS[provider]
        headers = {"Authorization": f"Bearer {api_key.strip()}", "User-Agent": "jevdroid/0.1.0"}
        if provider == "vercel":
            headers.update(
                {
                    "ai-model-id": self.model,
                    "ai-evaluation-model-specification-version": "4",
                    "ai-gateway-protocol-version": "0.0.1",
                    "ai-gateway-auth-method": "api-key",
                }
            )
        self._client = httpx.Client(
            headers=headers,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.headers.pop("Authorization", None)
        self._client.close()

    def decide(
        self, state: Mapping[str, Any], actions: Sequence[Action], instructions: str
    ) -> Decision:
        if not actions or len({a.id for a in actions}) != len(actions):
            raise ValueError("Actions must be nonempty and have unique IDs.")
        payload: dict[str, Any] = {
            "state": dict(state),
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": {a.id: a.description for a in actions},
                }
            },
        }
        if self.provider == "typesafe":
            payload["model"] = self.model
        try:
            response = self._client.post(ENDPOINTS[self.provider], json=payload)
        except httpx.HTTPError:
            raise ProviderError(
                "Inference connection failed or timed out; no retry was sent."
            ) from None
        if response.status_code != 200:
            messages = {
                401: "API key rejected.",
                402: "Provider credits required.",
                403: "Provider access denied; check account access and billing.",
                429: "Provider rate limit reached; no automatic retry was sent.",
            }
            raise ProviderError(
                messages.get(response.status_code, "Inference request failed."),
                status=response.status_code,
            )
        try:
            data = response.json()
            answer = data["answers"]["action"]
            if answer["type"] != "choice" or not isinstance(answer["choice"], str):
                raise ValueError()
            usage = data["usage"]
            tokens = usage["inputTokens" if self.provider == "vercel" else "input_tokens"]
            if type(tokens) is not int or tokens < 0:
                raise ValueError()
            confidence = answer.get("confidence")
            if confidence is not None and (
                type(confidence) not in (int, float) or not 0 <= confidence <= 1
            ):
                raise ValueError()
            # The engine settles usage before rejecting an out-of-policy choice.
            return Decision(answer["choice"], tokens, self.model, confidence)
        except (KeyError, TypeError, ValueError, AttributeError, json.JSONDecodeError):
            raise ProviderError("Malformed inference response; no action was executed.") from None
