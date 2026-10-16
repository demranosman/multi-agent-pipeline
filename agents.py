"""
Her fonksiyon bir "ajanı" temsil eder. Çoklu LLM sağlayıcıları (Anthropic, DeepSeek,
OpenAI, Google Gemini) ve yerel test motoru (quality_checker) ile çalışırlar.

Her ajan fonksiyonunun imzası aynı:
    def agent(context: dict, revision_note: str | None, model: str) -> dict

Dönüş değeri: {"summary": str, "full_output": dict, "question": str (opsiyonel)}
"""
from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from agent_schemas import (
    CodingOutput,
    MarketingOutput,
    PlanningOutput,
    ResearchOutput,
    TestingOutput,
)
from llm_gateway import call_llm_with_model
from quality_checker.runner import run_pipeline
from workspace import get_workspace_path


def _parse_json_output(raw_text: str) -> dict:
    """Model bazen ```json ... ``` gibi code fence'lerle sarabiliyor,
    onları temizleyip parse ediyoruz.

    Dönüş her zaman bir JSON nesnesi (dict) olmalı; model liste/sayı/dize
döndürürse bu bir sözleşme ihlalidir ve ValueError yükseltilir.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
        cleaned = cleaned.removeprefix("json").removeprefix("JSON").strip()

    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise TypeError(f"JSON nesnesi bekleniyordu, gelen tip: {type(parsed).__name__}")
    return parsed


def _append_revision_note(prompt: str, revision_note: str | None) -> str:
    if not revision_note:
        return prompt
    return (
        f"{prompt}\n\nNot: Bu bir revizyon turu. Önceki çıktıyla ilgili şu geri "
        f"bildirim geldi, bunu dikkate alarak güncelle:\n{revision_note}"
    )


def _call_structured_agent(
    system_prompt: str,
    user_prompt: str,
    model: str,
    fallback_summary: str,
    summarize: Callable[[dict], str],
    schema: type[BaseModel],
    tools: list | None = None,
    max_tokens: int = 4096,
) -> dict:
    """
    Ortak akış: LLM Gateway'i çağır -> JSON'a ayrıştır -> şemaya karşı doğrula -> özet üret.
    """
    try:
        raw_text, stop_reason, model_used = call_llm_with_model(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            tools=tools,
        )
    except Exception as e:
        return {
            "summary": f"{fallback_summary} çağrısı başarısız oldu: {e!s}",
            "full_output": {"error": str(e), "model": model},
            "model_used": model,
        }

    if stop_reason == "max_tokens":
        return {
            "summary": (
                f"{fallback_summary} ancak yanıt max_tokens={max_tokens} limitine "
                f"takılıp yarıda kesildi. Prompt'u kısaltman ya da max_tokens'ı "
                f"artırman gerekebilir."
            ),
            "full_output": {"raw_response": raw_text, "truncated": True},
            "model_used": model_used,
        }

    try:
        parsed = _parse_json_output(raw_text)
    except (ValueError, TypeError) as exc:
        # json.JSONDecodeError (ValueError) veya dict olmayan JSON (TypeError) buraya düşer.
        return {
            "summary": f"{fallback_summary} ancak çıktı beklenen JSON nesnesi formatında değildi ({exc}).",
            "full_output": {"raw_response": raw_text},
            "model_used": model_used,
        }

    try:
        output = schema.model_validate(parsed).model_dump(exclude_none=True)
    except ValidationError as exc:
        # Yanlış tip/alan: çökmek yerine ham çıktıyı sakla, pipeline devam etsin.
        return {
            "summary": f"{fallback_summary} ancak çıktı beklenen şemaya uymadı ({exc.error_count()} doğrulama hatası).",
            "full_output": {"raw_response": raw_text, "validation_error": str(exc)},
            "model_used": model_used,
        }

    return {"summary": summarize(output), "full_output": output, "model_used": model_used}


RESEARCH_SYSTEM_PROMPT = """\
Sen bir pazar araştırması ajanısın. Sana bir ürün/hizmet fikri verilecek.
Görevin: pazar verilerini analiz ederek bu fikrin uygulanabilirliğini değerlendirmek.

Değerlendirirken şunlara bak:
- Benzer/rakip ürünler var mı, varsa kaç tane ve ne kadar olgunlar
- Bu ihtiyaca gerçekten pazar talebi var mı
- Teknik/operasyonel zorluk derecesi
- Hedef müşteri kim, ne kadar büyük bir kitle

Cevabını SADECE aşağıdaki JSON şemasında ver, başka hiçbir metin ekleme:

{
  "feasibility_score": <1-10 arası tam sayı>,
  "market_need": "<düşük|orta|orta-yüksek|yüksek>",
  "difficulty": "<düşük|orta|yüksek>",
  "target_customer": "<kısa hedef kitle tanımı>",
  "competitors": ["<rakip adı ve kısa not>", ...],
  "key_risks": ["<risk>", ...],
  "reasoning": "<2-3 cümlelik gerekçe>"
}
"""


def research_agent(context: dict, revision_note: str | None = None,
                    model: str = "claude-sonnet-5-5") -> dict:
    prompt = _append_revision_note(
        f"Değerlendirilecek fikir:\n{context['idea_text']}", revision_note
    )

    def summarize(parsed: dict) -> str:
        competitor_count = len(parsed.get("competitors", []))
        return (
            f"Uygulanabilirlik puanı {parsed.get('feasibility_score', '?')}/10, "
            f"pazar ihtiyacı '{parsed.get('market_need', '?')}', "
            f"{competitor_count} rakip tespit edildi."
        )

    tools = [{"type": "web_search_20250305", "name": "web_search"}] if "claude" in model.lower() else None

    return _call_structured_agent(
        RESEARCH_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Araştırma tamamlandı",
        summarize=summarize,
        schema=ResearchOutput,
        tools=tools,
    )


PLANNING_SYSTEM_PROMPT = """\
Sen bir teknik mimar ve ürün planlama ajanısın. Sana bir ürün fikri ve o fikrin
pazar araştırması raporu verilecek. Görevin bu fikri hayata geçirmek için
somut bir teknik ve mimari plan çıkarmak.

Listeleri en fazla 8 madde ile sınırla, her maddeyi tek cümlede tut.

Cevabını SADECE aşağıdaki JSON şemasında ver, başka metin ekleme:

{
  "stack": ["<teknoloji/dil/kütüphane>", ...],
  "architecture_notes": "<mimari açıklama - servisler, veri akışı>",
  "milestones": ["<aşama>", ...],
  "key_integrations": ["<gerekli 3. parti servis/API>", ...],
  "estimated_weeks": <tam sayı>,
  "risks": ["<teknik risk>", ...],
  "scope_patterns": ["<coding aşamasında izin verilen dosya/dizin deseni, ör. app/* veya tests/*>", ...],
  "reasoning": "<2-3 cümlelik gerekçe>"
}
"""


def planning_agent(context: dict, revision_note: str | None = None,
                    model: str = "claude-opus-5-5") -> dict:
    research = context.get("research_report", {})
    prompt = _append_revision_note(
        f"Fikir:\n{context['idea_text']}\n\n"
        f"Pazar araştırması raporu:\n{json.dumps(research, ensure_ascii=False, indent=2)}",
        revision_note,
    )

    def summarize(parsed: dict) -> str:
        return (
            f"Teknik plan hazır: {', '.join(parsed.get('stack', [])) or 'stack belirtilmedi'}, "
            f"tahmini süre {parsed.get('estimated_weeks', '?')} hafta, "
            f"{len(parsed.get('milestones', []))} milestone."
        )

    return _call_structured_agent(
        PLANNING_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Planlama tamamlandı",
        summarize=summarize,
        schema=PlanningOutput,
        max_tokens=6000,
    )


CODING_SYSTEM_PROMPT = """\
Sen uzman bir kodlama ajanısın. Sana bir teknik plan verilecek. Görevin bu planın
ilk aşaması için somut, temiz ve çalışır durumda kod dosyaları üretmek.
Üretilen kodlar projenin çalışma alanına fiziksel olarak yazılacaktır.
Ayrıca bu kodlar için temel bir test dosyası (test_*.py) da üretmeyi unutma.

Cevabını SADECE aşağıdaki JSON şemasında ver, başka metin ekleme:

{
  "files": [
    {"path": "<dosya yolu, ör. main.py veya tests/test_main.py>", "content": "<dosyanın tam içeriği>"},
    ...
  ],
  "diff_summary": "<ne değişti/eklendi, kısa özet>",
  "open_questions": ["<koddan bağımsız nokta>", ...],
  "reasoning": "<2-3 cümlelik gerekçe>"
}
"""


def coding_agent(context: dict, revision_note: str | None = None,
                  model: str = "deepseek-v4-pro") -> dict:
    plan = context.get("planning_report", {})
    prompt = _append_revision_note(
        f"Fikir:\n{context['idea_text']}\n\n"
        f"Teknik plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}",
        revision_note,
    )

    def summarize(parsed: dict) -> str:
        files = parsed.get("files", [])
        note = f" (revizyon: {revision_note})" if revision_note else ""
        return f"{len(files)} dosya üretildi{note}."

    return _call_structured_agent(
        CODING_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Kodlama tamamlandı",
        summarize=summarize,
        schema=CodingOutput,
        max_tokens=8000,
    )


TESTING_SYSTEM_PROMPT = """\
Sen bir test ve kalite güvence (QA) ajanısın. Sana üretilen kod dosyaları ve
bu kodlar üzerinde gerçekten çalıştırılmış deterministik statik analiz / test motoru
(Ruff, Mypy, Bandit, Vulture, Pytest) raporu verilecek.

Görevin:
1. Otomatik test motorunun bulgularını (lint, güvenlik, test başarısızlığı vb.) analiz etmek.
2. Kodun mantıksal doğruluğunu incelemek.
3. Varsa engelleyici (blocking) sorunları listelemek ve recommended_action'ı "approve" veya "request_changes" olarak belirlemek.

Cevabını SADECE aşağıdaki JSON şemasında ver:

{
  "findings": [
    {"severity": "<blocking|important|minor>", "description": "<sorun>", "file": "<dosya>"},
    ...
  ],
  "generated_tests": [
    {"path": "<test dosyası yolu>", "content": "<test kodu>"},
    ...
  ],
  "recommended_action": "<approve|request_changes>",
  "reasoning": "<2-3 cümlelik gerekçe>"
}
"""


def testing_agent(context: dict, revision_note: str | None = None,
                   model: str = "claude-haiku-4-5-20251001") -> dict:
    code_report = context.get("coding_report", {})
    pipeline_id = context.get("pipeline_id")

    quality_report_dict = None
    if pipeline_id:
        try:
            workspace_path = get_workspace_path(pipeline_id)
            if workspace_path.exists():
                qp_result = run_pipeline(workspace_path)
                quality_report_dict = qp_result.to_dict()
        except Exception as exc:
            quality_report_dict = {"error": f"Kalite denetimi motor hatası: {exc!s}"}

    quality_summary_text = (
        json.dumps(quality_report_dict, ensure_ascii=False, indent=2)
        if quality_report_dict else "Kalite denetim raporu bulunamadı."
    )
    prompt = _append_revision_note(
        f"İncelenecek kod raporu:\n{json.dumps(code_report, ensure_ascii=False, indent=2)}\n\n"
        f"Gerçek Kalite ve Test Motoru Sonuçları:\n{quality_summary_text}",
        revision_note,
    )

    def summarize(parsed: dict) -> str:
        findings = parsed.get("findings", [])
        blocking = sum(1 for f in findings if f.get("severity") == "blocking")
        qp_status = (quality_report_dict or {}).get("overall_status", "N/A").upper()
        return (
            f"Kalite Denetimi: {qp_status} | Statik İnceleme: {len(findings)} bulgu "
            f"({blocking} engelleyici), Karar: {parsed.get('recommended_action', 'approve')}."
        )

    result = _call_structured_agent(
        TESTING_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Test ve kalite denetimi tamamlandı",
        summarize=summarize,
        schema=TestingOutput,
        max_tokens=6000,
    )

    if isinstance(result.get("full_output"), dict):
        result["full_output"]["quality_report"] = quality_report_dict

        if quality_report_dict and quality_report_dict.get("overall_status") == "fail":
            existing_findings = result["full_output"].get("findings", [])
            has_blocking = any(f.get("severity") == "blocking" for f in existing_findings)
            if not has_blocking:
                existing_findings.append({
                    "severity": "blocking",
                    "description": "Kalite kontrol motoru kritik hatalar tespit etti (Fail). Düzeltme gereklidir.",
                    "file": "quality_checker",
                })
                result["full_output"]["findings"] = existing_findings
                result["full_output"]["recommended_action"] = "request_changes"

    return result


MARKETING_SYSTEM_PROMPT = """\
Sen bir pazarlama strateji ve Go-to-Market (GTM) ajanısın. Sana bir ürün fikri ve
o fikrin pazar araştırması raporu verilecek. Görevin bu ürün için güçlü bir konumlandırma,
hedef kitle mesajı, lansman kanalları ve kampanya fikirleri üretmek.

Cevabını SADECE aşağıdaki JSON şemasında ver, başka metin ekleme:

{
  "positioning": "<kısa konumlandırma cümlesi>",
  "target_messaging": "<hedef kitleye yönelik ana mesaj>",
  "channels": ["<kanal>", ...],
  "campaign_ideas": ["<kampanya fikri>", ...],
  "content_calendar_suggestion": "<ilk 4 hafta için kabaca ne paylaşılmalı>",
  "reasoning": "<2-3 cümlelik gerekçe>"
}
"""


def marketing_agent(context: dict, revision_note: str | None = None,
                     model: str = "claude-sonnet-5-5") -> dict:
    research = context.get("research_report", {})
    prompt = _append_revision_note(
        f"Fikir:\n{context['idea_text']}\n\n"
        f"Pazar araştırması raporu:\n{json.dumps(research, ensure_ascii=False, indent=2)}",
        revision_note,
    )

    def summarize(parsed: dict) -> str:
        return (
            f"Pazarlama stratejisi hazır: {parsed.get('positioning', '?')} | "
            f"{len(parsed.get('channels', []))} kanal, "
            f"{len(parsed.get('campaign_ideas', []))} kampanya fikri."
        )

    tools = [{"type": "web_search_20250305", "name": "web_search"}] if "claude" in model.lower() else None

    return _call_structured_agent(
        MARKETING_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Pazarlama stratejisi tamamlandı",
        summarize=summarize,
        schema=MarketingOutput,
        tools=tools,
    )


AGENT_MAP = {
    "research": research_agent,
    "planning": planning_agent,
    "coding": coding_agent,
    "testing": testing_agent,
    "marketing": marketing_agent,
}