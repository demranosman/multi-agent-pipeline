"""
Çoklu LLM Sağlayıcı Katmanı (Anthropic, OpenAI, DeepSeek, Google Gemini).
Ajanların modele göre ilgili sağlayıcıya otomatik yönlendirilmesini sağlar.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

# Desteklenen model listesi ve sağlayıcıları.
# Kaynak (2026-10): resmi sağlayıcı model dokümanları. Emekli adlar kaldırıldı
# (örn. DeepSeek deepseek-chat/coder/v4 → 2026-07-24'te kapatıldı).
PROVIDER_CATALOG = {
    "anthropic": [
        "claude-fable-5-1",            # en yetenekli: uzun ufuklu ajanik akıl yürütme
        "claude-opus-5-5",             # çoğu iş yükü için varsayılan
        "claude-sonnet-5-5",           # dengeli hız/maliyet
        "claude-haiku-4-5-20251001",   # en hızlı/ekonomik
    ],
    "deepseek": [
        "deepseek-v4-pro",             # zor akıl yürütme (DeepSeek-V4-Pro)
        "deepseek-flash",              # DeepSeek-V4.1-Flash, hızlı/ekonomik
    ],
    "openai": [
        "gpt-6-astra",                 # en yüksek zeka
        "gpt-6.1-sol",                 # dengeli
        "gpt-6-luna",                  # en hızlı/ekonomik
    ],
    "gemini": [
        "gemini-3.8-flash",            # en yetenekli Flash (stable)
        "gemini-3.1-pro-preview",      # Pro (preview)
        "gemini-3.7-flash",            # önceki nesil Flash
        "gemini-3.5-flash-lite",       # ekonomik
    ],
}

logger = logging.getLogger(__name__)

# Sağlayıcı bazlı API anahtarı ortam değişkenleri (fallback uygunluğu için).
_PROVIDER_KEY_ENV = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def provider_available(provider: str) -> bool:
    """Sağlayıcı için kendi API anahtarı ortamda tanımlı mı?"""
    return any(os.environ.get(k) for k in _PROVIDER_KEY_ENV.get(provider, ()))


def fallback_models(model: str, limit: int = 2) -> list[str]:
    """Verilen model başarısız olursa (kredi/ağ/limit) denenecek alternatifler.

    - `LLM_FALLBACK_MODELS` ortam değişkeni virgülle ayrılmış model listesi verirse
      o kullanılır (elle kalibrasyon knob'u).
    - Aksi halde farklı sağlayıcılardan API anahtarı tanımlı olanların en üst
      modeli seçilir. Aynı sağlayıcı atlanır: kredi tükenmesi hesap genelindedir,
      aynı sağlayıcının başka modeli de başarısız olur.
    """
    override = os.environ.get("LLM_FALLBACK_MODELS", "").strip()
    if override:
        candidates = [m.strip() for m in override.split(",") if m.strip()]
        return [m for m in candidates if m != model][:limit]

    primary = detect_provider(model)
    result: list[str] = []
    for provider, models in PROVIDER_CATALOG.items():
        if provider == primary or not provider_available(provider):
            continue
        result.append(models[0])
        if len(result) >= limit:
            break
    return result


def detect_provider(model: str) -> str:
    """Model adından sağlayıcıyı belirler."""
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if "deepseek" in m:
        return "deepseek"
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith(("gpt-", "o1", "o3", "chatgpt")):
        return "openai"
    return "anthropic"


def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    tools: list | None = None,
) -> tuple[str, str]:
    import anthropic

    headers = {}
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    if workspace_id:
        headers["anthropic-workspace-id"] = workspace_id

    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        default_headers=headers or None,
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if tools:
        kwargs["tools"] = tools

    response = client.messages.create(**kwargs)
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response.stop_reason or ""


def _call_openai_compatible(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    base_url: str,
    api_key: str,
) -> tuple[str, str]:
    """OpenAI, DeepSeek ve Google Gemini OpenAI-uyumlu uç noktalarını httpx ile çağırır."""
    if not api_key:
        raise ValueError(f"{model} için gerekli API anahtarı bulunamadı (.env dosyasını kontrol edin).")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        return "", "no_choices"

    first = choices[0]
    content = first.get("message", {}).get("content", "")
    finish_reason = first.get("finish_reason", "")
    return content, finish_reason


def _dispatch_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    tools: list | None,
) -> tuple[str, str]:
    """Tek bir model adını ilgili sağlayıcıya yönlendirir."""
    provider = detect_provider(model)

    if provider == "anthropic":
        return _call_anthropic(system_prompt, user_prompt, model, max_tokens, tools)

    if provider == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        return _call_openai_compatible(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            base_url="https://api.deepseek.com/v1",
            api_key=api_key,
        )

    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        return _call_openai_compatible(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=api_key,
        )

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        return _call_openai_compatible(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            base_url="https://api.openai.com/v1",
            api_key=api_key,
        )

    raise ValueError(f"Desteklenmeyen model/sağlayıcı: {model}")


def call_llm_with_model(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int = 4096,
    tools: list | None = None,
) -> tuple[str, str, str]:
    """
    call_llm gibi çalışır ama yanıtı gerçekte üreten modeli de döndürür:
    (raw_text, stop_reason, model_used). Fallback devreye girerse `model_used`
    istenen modelden farklı olur.
    """
    candidates = [model, *fallback_models(model)]
    errors: list[str] = []

    for candidate in candidates:
        try:
            text, stop_reason = _dispatch_llm(system_prompt, user_prompt, candidate, max_tokens, tools)
            return text, stop_reason, candidate
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
            if candidate != candidates[-1]:
                logger.warning(
                    "LLM çağrısı başarısız (%s): %s — sıradaki aday deneniyor.",
                    candidate, exc,
                )

    raise RuntimeError("Tüm LLM adayları başarısız oldu — " + " | ".join(errors))


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int = 4096,
    tools: list | None = None,
) -> tuple[str, str]:
    """Geriye uyumlu sarmalayıcı: yalnız (raw_text, stop_reason) döndürür."""
    text, stop_reason, _model_used = call_llm_with_model(
        system_prompt, user_prompt, model, max_tokens, tools,
    )
    return text, stop_reason
