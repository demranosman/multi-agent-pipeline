"""LLM Gateway sağlayıcı yönlendirme ve HTTP katmanı testleri (gerçek ağ çağrısı yok)."""

from types import SimpleNamespace
from typing import ClassVar

import httpx
import pytest

import llm_gateway
from llm_gateway import (
    PROVIDER_CATALOG,
    _call_openai_compatible,
    call_llm,
    call_llm_with_model,
    detect_provider,
)

# --- Katalog / yönlendirme tutarlılığı ---------------------------------------

def test_catalog_models_route_to_their_provider():
    """Katalogdaki her model kendi sağlayıcısına yönlenmeli (regresyon)."""
    for provider, models in PROVIDER_CATALOG.items():
        for model in models:
            assert detect_provider(model) == provider, f"{model} yanlış sağlayıcıya gidiyor"


def test_unknown_model_falls_back_to_anthropic():
    # Bilinmeyen model adı sessizce Anthropic'e düşer; bu davranış burada sabitlenir.
    assert detect_provider("bilinmeyen-model") == "anthropic"


# --- OpenAI-uyumlu HTTP katmanı (httpx mock) ---------------------------------

class _FakeResponse:
    def __init__(self, data=None, raises=None):
        self._data = data
        self._raises = raises

    def raise_for_status(self):
        if self._raises:
            raise self._raises

    def json(self):
        return self._data


class _FakeClient:
    response = None
    last: ClassVar[dict] = {}

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None):
        _FakeClient.last = {"url": url, "headers": headers, "json": json}
        return _FakeClient.response


@pytest.fixture
def fake_http(monkeypatch):
    monkeypatch.setattr(llm_gateway.httpx, "Client", _FakeClient)
    _FakeClient.last = {}
    return _FakeClient


def test_openai_compatible_success(fake_http):
    fake_http.response = _FakeResponse({
        "choices": [{"message": {"content": "merhaba"}, "finish_reason": "stop"}]
    })

    text, reason = _call_openai_compatible(
        "sys", "user", "gpt-6-astra", 100, "https://api.openai.com/v1", "sk-test"
    )

    assert (text, reason) == ("merhaba", "stop")
    assert fake_http.last["url"] == "https://api.openai.com/v1/chat/completions"
    assert fake_http.last["headers"]["Authorization"] == "Bearer sk-test"
    assert fake_http.last["json"]["messages"][0]["role"] == "system"


def test_openai_compatible_no_choices(fake_http):
    fake_http.response = _FakeResponse({"choices": []})
    assert _call_openai_compatible("s", "u", "m", 10, "https://x/v1", "k") == ("", "no_choices")


def test_openai_compatible_requires_api_key(fake_http):
    with pytest.raises(ValueError):
        _call_openai_compatible("s", "u", "m", 10, "https://x/v1", "")


def test_openai_compatible_propagates_http_error(fake_http):
    fake_http.response = _FakeResponse(raises=httpx.HTTPError("boom"))
    with pytest.raises(httpx.HTTPError):
        _call_openai_compatible("s", "u", "m", 10, "https://x/v1", "k")


# --- Sağlayıcı yönlendirme (call_llm) ----------------------------------------

def test_call_llm_routes_anthropic(monkeypatch):
    captured = {}

    def fake(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return ("t", "r")

    monkeypatch.setattr(llm_gateway, "_call_anthropic", fake)
    assert call_llm("s", "u", "claude-opus-5-5") == ("t", "r")
    assert captured["args"][2] == "claude-opus-5-5"


def test_call_llm_routes_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
    captured = {}
    monkeypatch.setattr(
        llm_gateway, "_call_openai_compatible",
        lambda **kw: captured.update(kw) or ("t", "r"),
    )

    call_llm("s", "u", "gpt-6-astra")

    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["api_key"] == "sk-o"
    assert captured["model"] == "gpt-6-astra"


def test_call_llm_routes_deepseek(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-d")
    captured = {}
    monkeypatch.setattr(
        llm_gateway, "_call_openai_compatible",
        lambda **kw: captured.update(kw) or ("t", "r"),
    )

    call_llm("s", "u", "deepseek-v4-pro")

    assert captured["base_url"] == "https://api.deepseek.com/v1"
    assert captured["model"] == "deepseek-v4-pro"
    assert captured["api_key"] == "sk-d"


def test_call_llm_routes_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    captured = {}
    monkeypatch.setattr(
        llm_gateway, "_call_openai_compatible",
        lambda **kw: captured.update(kw) or ("t", "r"),
    )

    call_llm("s", "u", "gemini-3.8-flash")

    assert captured["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"


# --- Anthropic SDK katmanı (anthropic mock) ----------------------------------

class _FakeAnthropic:
    content: ClassVar[list] = []
    stop_reason = "end_turn"
    last_kwargs: ClassVar[dict] = {}
    last_headers: ClassVar[dict | None] = None

    def __init__(self, api_key=None, default_headers=None):
        self.api_key = api_key
        _FakeAnthropic.last_headers = default_headers
        _FakeAnthropic.last_kwargs = {}
        outer = self

        class _Messages:
            def create(self, **kwargs):
                _FakeAnthropic.last_kwargs = kwargs
                return SimpleNamespace(content=outer.content, stop_reason=outer.stop_reason)

        self.messages = _Messages()


@pytest.fixture
def fake_anthropic(monkeypatch):
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    _FakeAnthropic.content = []
    return _FakeAnthropic


def test_call_anthropic_joins_only_text_blocks(fake_anthropic):
    fake_anthropic.content = [
        SimpleNamespace(type="text", text="mer"),
        SimpleNamespace(type="tool_use", text="yoksay"),
        SimpleNamespace(type="text", text="haba"),
    ]

    text, reason = llm_gateway._call_anthropic("sys", "user", "claude-opus-5-5", 50)

    assert text == "merhaba"
    assert reason == "end_turn"
    assert fake_anthropic.last_kwargs["model"] == "claude-opus-5-5"
    assert fake_anthropic.last_kwargs["system"] == "sys"


def test_call_anthropic_sends_workspace_header(fake_anthropic, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrk")
    llm_gateway._call_anthropic("s", "u", "claude-opus-5-5", 10)
    assert fake_anthropic.last_headers == {"anthropic-workspace-id": "wrk"}


# --- Sağlayıcı fallback (kredi/ağ hatası) -------------------------------------

_ALL_KEY_ENVS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_FALLBACK_MODELS",
)


@pytest.fixture
def isolated_keys(monkeypatch):
    """Testin gerçek .env anahtarlarından etkilenmemesini sağlar."""
    for key in _ALL_KEY_ENVS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_provider_available_requires_its_own_key(isolated_keys):
    assert llm_gateway.provider_available("openai") is False
    isolated_keys.setenv("OPENAI_API_KEY", "x")
    assert llm_gateway.provider_available("openai") is True
    # OpenAI anahtarı DeepSeek için sayılmaz
    assert llm_gateway.provider_available("deepseek") is False


def test_fallback_models_skips_primary_and_keyless(isolated_keys):
    isolated_keys.setenv("OPENAI_API_KEY", "x")
    assert llm_gateway.fallback_models("claude-opus-5-5") == ["gpt-6-astra"]
    # Zaten OpenAI; başka anahtar yok -> fallback yok
    assert llm_gateway.fallback_models("gpt-6-astra") == []


def test_fallback_models_env_override(isolated_keys):
    isolated_keys.setenv("LLM_FALLBACK_MODELS", "gemini-3.8-flash, deepseek-flash,gemini-3.7-flash")
    assert llm_gateway.fallback_models("claude-opus-5-5", limit=2) == [
        "gemini-3.8-flash", "deepseek-flash",
    ]


def test_call_llm_falls_back_on_provider_error(isolated_keys, monkeypatch):
    isolated_keys.setenv("OPENAI_API_KEY", "sk-o")

    def failing_anthropic(*args, **kwargs):
        raise RuntimeError("credit balance is too low")

    captured = {}
    monkeypatch.setattr(llm_gateway, "_call_anthropic", failing_anthropic)
    monkeypatch.setattr(
        llm_gateway, "_call_openai_compatible",
        lambda **kw: captured.update(kw) or ("yedek yanıt", "stop"),
    )

    assert call_llm("s", "u", "claude-opus-5-5") == ("yedek yanıt", "stop")
    assert captured["model"] == "gpt-6-astra"
    assert captured["base_url"] == "https://api.openai.com/v1"


def test_call_llm_raises_when_all_candidates_fail(isolated_keys, monkeypatch):
    isolated_keys.setenv("OPENAI_API_KEY", "sk-o")

    def boom(*args, **kwargs):
        raise RuntimeError("kredi bitti")

    monkeypatch.setattr(llm_gateway, "_call_anthropic", boom)
    monkeypatch.setattr(llm_gateway, "_call_openai_compatible", boom)

    with pytest.raises(RuntimeError, match="Tüm LLM adayları başarısız"):
        call_llm("s", "u", "claude-opus-5-5")


def test_call_llm_with_model_returns_requested_when_primary_works(isolated_keys, monkeypatch):
    monkeypatch.setattr(llm_gateway, "_call_anthropic", lambda *_a, **_k: ("ok", "stop"))
    assert call_llm_with_model("s", "u", "claude-opus-5-5") == (
        "ok", "stop", "claude-opus-5-5",
    )


def test_call_llm_with_model_reports_fallback(isolated_keys, monkeypatch):
    isolated_keys.setenv("OPENAI_API_KEY", "sk-o")

    def boom(*args, **kwargs):
        raise RuntimeError("credit balance is too low")

    monkeypatch.setattr(llm_gateway, "_call_anthropic", boom)
    monkeypatch.setattr(llm_gateway, "_call_openai_compatible", lambda **_kw: ("ok", "stop"))

    assert call_llm_with_model("s", "u", "claude-opus-5-5") == (
        "ok", "stop", "gpt-6-astra",
    )
