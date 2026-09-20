"""
Her fonksiyon bir "ajanı" temsil eder. Şu an stub (sahte) çıktı
döndürüyorlar - gerçek kullanımda her biri Anthropic API'ye
(gerekirse web_search tool'uyla) bir çağrı yapıp yapılandırılmış
JSON döndürmeli.

Her ajan fonksiyonunun imzası aynı:
    def agent(context: dict, revision_note: str | None, model: str) -> dict

- context: önceki aşamalardan gelen birikmiş bilgi (idea_text,
  research_report, plan, code_summary ...)
- revision_note: eğer bu bir revizyon turuysa, düzeltilmesi istenen
  şeyin metni (AgentMessage.content) - stub'larda kullanılmıyor ama
  gerçek implementasyonda prompt'a eklenmeli.
- model: orchestrator'ın stage_configs tablosundan (ya da DEFAULT_MODELS
  varsayılanından) çözdüğü model string'i, örn. "claude-opus-5".
  Gerçek implementasyonda Anthropic API çağrısındaki `model` parametresine
  doğrudan geçirilmeli - böylece hangi ajanın hangi modeli kullanacağı
  kod değiştirmeden, stage_configs üzerinden ayarlanabilir.

Dönüş değeri: {"summary": str, "full_output": dict, "question": str (opsiyonel)}
summary -> PipelineLog.summary, full_output -> PipelineLog.full_output

"question" alanı doldurulursa (örn. "Ödeme için Stripe mi iyzico mu?"),
orchestrator bunu otomatik olarak "user"a yönelik blocking bir
AgentMessage'a çevirir ve pipeline'ı waiting_response durumuna alır.
Kullanıcı /messages/{id}/answer ile cevapladığında aynı ajan, cevabı
revision_note olarak alıp kaldığı yerden devam eder.
"""
from typing import Optional
import json
import os

import anthropic

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    """
    Client'ı lazily oluşturuyoruz ki ANTHROPIC_API_KEY set edilmeden
    modül import edildiğinde (ör. testlerde) hata vermesin.

    ANTHROPIC_WORKSPACE_ID opsiyoneldir: sadece kullandığın API anahtarı
    belirli bir workspace'e bağlı DEĞİLSE gerekir (bu durumda Anthropic
    API'si "anthropic-workspace-id header gerekli" hatası döner). Normal
    şartlarda console.anthropic.com'da bir workspace içinde oluşturulan
    anahtarlar için bu değişkene gerek yoktur.
    """
    global _client
    if _client is None:
        default_headers = {}
        workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        if workspace_id:
            default_headers["anthropic-workspace-id"] = workspace_id
        _client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            default_headers=default_headers or None,
        )
    return _client


def _extract_text(response) -> str:
    """response.content, web_search kullanıldığında metin dışı bloklar da
    içerebilir (server_tool_use, web_search_tool_result) - sadece text
    bloklarını birleştiriyoruz."""
    return "".join(block.text for block in response.content if block.type == "text")


def _parse_json_output(raw_text: str) -> dict:
    """Model bazen ```json ... ``` gibi code fence'lerle sarabiliyor,
    onları temizleyip parse ediyoruz."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        cleaned = cleaned.removeprefix("json").strip()
    return json.loads(cleaned)


RESEARCH_SYSTEM_PROMPT = """\
Sen bir pazar araştırması ajanısın. Sana bir ürün/hizmet fikri verilecek.
Görevin: web araması yaparak bu fikrin uygulanabilirliğini değerlendirmek.

Değerlendirirken şunlara bak:
- Benzer/rakip ürünler var mı, varsa kaç tane ve ne kadar olgunlar
- Bu ihtiyaca gerçekten pazar talebi var mı (arama hacmi, forum/topluluk
  tartışmaları, mevcut ürünlerin şikayetleri gibi sinyaller)
- Teknik/operasyonel zorluk derecesi
- Hedef müşteri kim, ne kadar büyük bir kitle

Cevabını SADECE aşağıdaki JSON şemasında ver, başka hiçbir metin ekleme
(markdown code fence de kullanma, düz JSON döndür):

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


def _append_revision_note(prompt: str, revision_note: Optional[str]) -> str:
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
    summarize: "callable",
    tools: Optional[list] = None,
    max_tokens: int = 4096,
) -> dict:
    """
    Ortak akış: API'yi çağır -> metni çıkar -> JSON'a ayrıştır -> özet üret.
    JSON parse edilemezse pipeline'ı kırmadan ham metni full_output'a koyar,
    böylece kullanıcı /logs üzerinden görüp manuel müdahale edebilir.

    summarize: parsed dict alıp özet string'i döndüren fonksiyon.
    """
    client = _get_client()
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if tools:
        kwargs["tools"] = tools

    response = client.messages.create(**kwargs)
    raw_text = _extract_text(response)

    if response.stop_reason == "max_tokens":
        # Format sorunu değil, kapasite sorunu - ayırt etmek önemli çünkü
        # çözümü farklı (max_tokens'ı artırmak ya da promptu kısaltmak).
        return {
            "summary": (
                f"{fallback_summary} ancak yanıt max_tokens={max_tokens} limitine "
                f"takılıp yarıda kesildi. Prompt'u kısaltman ya da max_tokens'ı "
                f"artırman gerekebilir."
            ),
            "full_output": {"raw_response": raw_text, "truncated": True},
        }

    try:
        parsed = _parse_json_output(raw_text)
    except (json.JSONDecodeError, IndexError):
        return {
            "summary": f"{fallback_summary} ancak çıktı beklenen JSON formatında değildi.",
            "full_output": {"raw_response": raw_text},
        }

    return {"summary": summarize(parsed), "full_output": parsed}


def research_agent(context: dict, revision_note: Optional[str] = None,
                    model: str = "claude-sonnet-5") -> dict:
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

    return _call_structured_agent(
        RESEARCH_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Araştırma tamamlandı",
        summarize=summarize,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )


PLANNING_SYSTEM_PROMPT = """\
Sen bir teknik mimar/planlama ajanısın. Sana bir ürün fikri ve o fikrin
pazar araştırması raporu verilecek. Görevin bu fikri hayata geçirmek için
somut bir teknik plan çıkarmak.

Listeleri (milestones, risks, key_integrations) en fazla 8 madde ile sınırla,
her maddeyi tek cümlede tut - yanıtın kesilmemesi için özlü ol.

Cevabını SADECE aşağıdaki JSON şemasında ver, başka metin ekleme:
  "architecture_notes": "<kısa mimari açıklama - servisler, veri akışı>",
  "milestones": ["<aşama>", ...],
  "key_integrations": ["<gerekli 3. parti servis/API>", ...],
  "estimated_weeks": <tam sayı>,
  "risks": ["<teknik risk>", ...],
  "reasoning": "<2-3 cümlelik gerekçe>"
}
"""


def planning_agent(context: dict, revision_note: Optional[str] = None,
                    model: str = "claude-opus-5") -> dict:
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
        max_tokens=6000,
    )


CODING_SYSTEM_PROMPT = """\
Sen bir kodlama ajanısın. Sana bir teknik plan verilecek. Görevin bu planın
ilk aşaması için somut, çalışır durumda kod üretmek.

Cevabını SADECE aşağıdaki JSON şemasında ver, başka metin ekleme:

{
  "files": [
    {"path": "<dosya yolu>", "content": "<dosyanın tam içeriği>"},
    ...
  ],
  "diff_summary": "<ne değişti/eklendi, kısa özet>",
  "open_questions": ["<koddan bağımsız, netleştirilmesi gereken nokta>", ...],
  "reasoning": "<2-3 cümlelik gerekçe>"
}
"""


def coding_agent(context: dict, revision_note: Optional[str] = None,
                  model: str = "claude-sonnet-5") -> dict:
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

    result = _call_structured_agent(
        CODING_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Kodlama tamamlandı",
        summarize=summarize,
        max_tokens=8000,
    )
    # NOT: Bu implementasyon kodu sadece ÜRETİR, gerçek bir repo'ya yazmaz
    # ya da çalıştırmaz. Üretimde full_output["files"] içeriğini bir
    # sandbox/container'a yazıp (ör. Docker + git) orada test_agent'ın
    # gerçekten çalıştırabileceği bir ortam kurman gerekir.
    return result


TESTING_SYSTEM_PROMPT = """\
Sen bir test ajanısın. Sana üretilmiş kod dosyaları verilecek. Görevin bu
kodu statik olarak incelemek, olası hataları/eksikleri tespit etmek ve
bu kod için test senaryoları üretmek.

Not: Kodu gerçekten ÇALIŞTIRMIYORSUN, sadece okuyarak analiz ediyorsun.
Bu yüzden "passed/failed" gibi kesin sayılar üretme - bunun yerine
tespit ettiğin somut sorunları ve önerdiğin testleri raporla.

Cevabını SADECE aşağıdaki JSON şemasında ver, başka metin ekleme:

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


def testing_agent(context: dict, revision_note: Optional[str] = None,
                   model: str = "claude-haiku-4-5-20251001") -> dict:
    code = context.get("coding_report", {})
    prompt = _append_revision_note(
        f"İncelenecek kod:\n{json.dumps(code, ensure_ascii=False, indent=2)}",
        revision_note,
    )

    def summarize(parsed: dict) -> str:
        findings = parsed.get("findings", [])
        blocking = sum(1 for f in findings if f.get("severity") == "blocking")
        return (
            f"Statik inceleme tamamlandı: {len(findings)} bulgu "
            f"({blocking} engelleyici), {len(parsed.get('generated_tests', []))} test üretildi."
        )

    result = _call_structured_agent(
        TESTING_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Test/inceleme tamamlandı",
        summarize=summarize,
        max_tokens=6000,
    )
    # NOT: Gerçek "test çalıştırma" (pytest vb.) için full_output["generated_tests"]
    # içeriğini coding_agent'ın ürettiği dosyalarla birlikte bir sandbox'a
    # yazıp gerçekten çalıştırman, sonucu ayrı bir adımda buraya eklemen gerekir.
    return result


MARKETING_SYSTEM_PROMPT = """\
Sen bir pazarlama strateji ajanısın. Sana bir ürün fikri ve o fikrin pazar
araştırması raporu (hedef kitle, rakipler) verilecek. Görevin bu ürün için
bir konumlandırma ve başlangıç pazarlama stratejisi üretmek. Gerekirse
güncel trendleri/kanalları kontrol etmek için web araması yapabilirsin.

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


def marketing_agent(context: dict, revision_note: Optional[str] = None,
                     model: str = "claude-sonnet-5") -> dict:
    research = context.get("research_report", {})
    prompt = _append_revision_note(
        f"Fikir:\n{context['idea_text']}\n\n"
        f"Pazar araştırması raporu (hedef kitle/rakipler dahil):\n"
        f"{json.dumps(research, ensure_ascii=False, indent=2)}",
        revision_note,
    )

    def summarize(parsed: dict) -> str:
        return (
            f"Pazarlama stratejisi hazır: {parsed.get('positioning', '?')} | "
            f"{len(parsed.get('channels', []))} kanal, "
            f"{len(parsed.get('campaign_ideas', []))} kampanya fikri."
        )

    return _call_structured_agent(
        MARKETING_SYSTEM_PROMPT, prompt, model,
        fallback_summary="Pazarlama stratejisi tamamlandı",
        summarize=summarize,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )


AGENT_MAP = {
    "research": research_agent,
    "planning": planning_agent,
    "coding": coding_agent,
    "testing": testing_agent,
    "marketing": marketing_agent,
}