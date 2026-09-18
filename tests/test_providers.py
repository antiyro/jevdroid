import json

import httpx
import pytest

from jevdroid import Action, ActionKind
from jevdroid.errors import ProviderError
from jevdroid.providers import JevProvider

ACTIONS = (Action("DONE", ActionKind.DONE, "Already complete"),)


@pytest.mark.parametrize(
    "provider,token_key,endpoint",
    [
        ("vercel", "inputTokens", "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"),
        ("typesafe", "input_tokens", "https://api.typesafe.ai/v1/systemone"),
    ],
)
def test_wire_contract_and_persistent_client(provider, token_key, endpoint):
    requests = []

    def handler(request):
        requests.append(request)
        assert str(request.url) == endpoint
        assert request.headers["Authorization"] == "Bearer fixture-key"
        body = json.loads(request.content)
        assert body["questions"]["action"] == {
            "type": "choice",
            "instructions": "choose",
            "criteria": {"DONE": "Already complete"},
        }
        assert "fixture-key" not in request.content.decode()
        if provider == "vercel":
            assert request.headers["ai-model-id"] == "typesafe-ai/jev"
            assert request.headers["ai-evaluation-model-specification-version"] == "4"
            assert request.headers["ai-gateway-protocol-version"] == "0.0.1"
            assert request.headers["ai-gateway-auth-method"] == "api-key"
            assert "model" not in body
        else:
            assert body["model"] == "jev-1.13.0"
        return httpx.Response(
            200,
            json={
                "answers": {"action": {"type": "choice", "choice": "DONE"}},
                "usage": {token_key: 123},
            },
        )

    with JevProvider(
        "fixture-key", provider=provider, transport=httpx.MockTransport(handler)
    ) as client:
        for _ in range(2):
            assert client.decide({"sample": True}, ACTIONS, "choose").input_tokens == 123
    assert len(requests) == 2
    assert client._client.is_closed
    assert "Authorization" not in client._client.headers


@pytest.mark.parametrize("status", [301, 401, 402, 403, 429, 500])
def test_errors_never_retry_redirect_or_leak_response(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"error": "fixture-key private device text"},
            headers={"Location": "https://other.invalid"},
        )

    with JevProvider("fixture-key", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as error:
            client.decide({}, ACTIONS, "choose")
    assert error.value.status == status and len(calls) == 1
    assert "fixture-key" not in str(error.value) and "private" not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"answers": {}},
        {
            "answers": {"action": {"type": "choice", "choice": "DONE"}},
            "usage": {"inputTokens": True},
        },
        {
            "answers": {"action": {"type": "choice", "choice": "DONE", "confidence": 3}},
            "usage": {"inputTokens": 10},
        },
    ],
)
def test_malformed_response(body):
    with JevProvider(
        "fixture-key", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ) as client:
        with pytest.raises(ProviderError):
            client.decide({}, ACTIONS, "choose")


def test_timeout_is_redacted():
    def handler(request):
        raise httpx.ReadTimeout("fixture-key secret", request=request)

    with JevProvider("fixture-key", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="timed out") as error:
            client.decide({}, ACTIONS, "choose")
    assert "secret" not in str(error.value)
