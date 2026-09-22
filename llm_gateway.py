"""
Çoklu LLM Sağlayıcı Katmanı (Anthropic, OpenAI, DeepSeek, Google Gemini).
Ajanların modele göre ilgili sağlayıcıya otomatik yönlendirilmesini sağlar.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

# Desteklenen model listesi ve sağlayıcıları
PROVIDER_CATALOG = {
    "anthropic": [
        "claude-sonnet-5",
        "claude-opus-5",
        "claude-haiku-4-5-20251001",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-coder",
        "deepseek-v3",
        "deepseek-v4",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o1",
        "o3-mini",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ],
}


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
    # Varsayılan Anthropic
    return "anthropic"


def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    tools: Optional[list] = None,
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
    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
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


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int = 4096,
    tools: Optional[list] = None,
) -> tuple[str, str]:
    """
    Seçilen model ve sağlayıcıya göre LLM çağrısını gerçekleştirir.
    Dönüş: (raw_text, stop_reason)
    """
    provider = detect_provider(model)

    if provider == "anthropic":
        return _call_anthropic(system_prompt, user_prompt, model, max_tokens, tools)

    elif provider == "deepseek":
        # DeepSeek API
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        # deepseek-v4 henüz çıkmadıysa fallback olarak deepseek-chat/coder
        mapped_model = model
        if model in ("deepseek-v4", "deepseek-coder"):
            mapped_model = "deepseek-coder"
        return _call_openai_compatible(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=mapped_model,
            max_tokens=max_tokens,
            base_url="https://api.deepseek.com/v1",
            api_key=api_key,
        )

    elif provider == "gemini":
        # Google Gemini OpenAI-uyumlu endpoint
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        return _call_openai_compatible(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=api_key,
        )

    elif provider == "openai":
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
