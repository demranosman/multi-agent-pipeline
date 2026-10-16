"""Ajan çıktı ayrıştırma ve yapılandırılmış çağrı testleri (LLM çağrısı mock'lanır)."""

import json
from types import SimpleNamespace

import pytest

import agents
from agent_schemas import ResearchOutput
from agents import (
    _append_revision_note,
    _call_structured_agent,
    _parse_json_output,
    coding_agent,
    marketing_agent,
    planning_agent,
    research_agent,
)
from agents import (
    testing_agent as run_testing_agent,
)


def test_parse_plain_json_object():
    assert _parse_json_output('{"a": 1}') == {"a": 1}


def test_parse_fenced_json_object():
    assert _parse_json_output('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_fenced_without_language():
    assert _parse_json_output('```\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.parametrize("raw", ["[1, 2, 3]", '"metin"', "42", "null"])
def test_parse_rejects_non_object(raw):
    with pytest.raises(TypeError):
        _parse_json_output(raw)


def test_parse_rejects_invalid_json():
    with pytest.raises(ValueError):
        _parse_json_output("{bozuk")


def test_structured_agent_handles_non_object_json(monkeypatch):
    """Model geçerli ama nesne olmayan JSON dönerse çökmemeli, özet dönmeli."""
    monkeypatch.setattr(
        agents, "call_llm_with_model",
        lambda **kwargs: ("[1, 2, 3]", "end_turn", "m"),
    )

    result = _call_structured_agent(
        system_prompt="s", user_prompt="u", model="m",
        fallback_summary="Test",
        summarize=lambda parsed: "buraya düşmemeli",
        schema=ResearchOutput,
    )

    assert "JSON nesnesi" in result["summary"]
    assert result["full_output"] == {"raw_response": "[1, 2, 3]"}
    assert result["model_used"] == "m"


def test_structured_agent_validates_and_summarizes(monkeypatch):
    payload = '{"feasibility_score": 7, "competitors": ["a", "b"]}'
    monkeypatch.setattr(
        agents, "call_llm_with_model",
        lambda **kwargs: (payload, "end_turn", "istenen-model"),
    )
    captured = {}

    def summarize(parsed):
        captured.update(parsed)
        return "özet"

    result = _call_structured_agent(
        system_prompt="s", user_prompt="u", model="istenen-model",
        fallback_summary="Test", summarize=summarize, schema=ResearchOutput,
    )

    assert result["summary"] == "özet"
    assert result["model_used"] == "istenen-model"
    assert captured["feasibility_score"] == 7
    assert captured["competitors"] == ["a", "b"]
    # Eksik opsiyonel alanlar atılır, varsayılan listeler gelir.
    assert "market_need" not in captured
    assert captured["key_risks"] == []


def test_structured_agent_rejects_wrong_type(monkeypatch):
    payload = '{"competitors": 5}'
    monkeypatch.setattr(
        agents, "call_llm_with_model",
        lambda **kwargs: (payload, "end_turn", "m"),
    )

    result = _call_structured_agent(
        system_prompt="s", user_prompt="u", model="m",
        fallback_summary="Test", summarize=lambda parsed: "olmamalı", schema=ResearchOutput,
    )

    assert "şemaya uymadı" in result["summary"]
    assert "validation_error" in result["full_output"]
    assert result["full_output"]["raw_response"] == payload


def test_structured_agent_preserves_extra_fields(monkeypatch):
    payload = '{"feasibility_score": 3, "beklenmeyen_alan": "x"}'
    monkeypatch.setattr(
        agents, "call_llm_with_model",
        lambda **kwargs: (payload, "end_turn", "m"),
    )
    captured = {}

    def summarize(parsed):
        captured.update(parsed)
        return "özet"

    _call_structured_agent(
        system_prompt="s", user_prompt="u", model="m",
        fallback_summary="Test", summarize=summarize, schema=ResearchOutput,
    )

    assert captured["beklenmeyen_alan"] == "x"


# --- Ajan seviyesi (LLM çağrısı mock'lu) -------------------------------------

def _fake_llm(payload):
    """Başarılı bir LLM çağrısını taklit eder; istenen modeli kullanılmış gibi döner."""
    return lambda **kwargs: (
        json.dumps(payload), "end_turn", kwargs.get("model", "test-model"),
    )


def test_research_agent_returns_validated_output(monkeypatch):
    monkeypatch.setattr(agents, "call_llm_with_model", _fake_llm({
        "feasibility_score": 8, "competitors": ["a"], "key_risks": ["r"],
    }))

    result = research_agent({"idea_text": "fikir"})

    assert "8/10" in result["summary"]
    assert result["full_output"]["feasibility_score"] == 8
    assert result["model_used"] == "claude-sonnet-5-5"


def test_agent_records_fallback_model(monkeypatch):
    """Birincil model düşüp yedek kullanılırsa, ajan gerçek modeli bildirmeli."""
    monkeypatch.setattr(
        agents, "call_llm_with_model",
        lambda **kwargs: (json.dumps({"feasibility_score": 5}), "end_turn", "gpt-6-astra"),
    )

    result = research_agent({"idea_text": "f"})

    assert result["model_used"] == "gpt-6-astra"


def test_planning_agent_summary(monkeypatch):
    monkeypatch.setattr(agents, "call_llm_with_model", _fake_llm({
        "stack": ["python"], "milestones": ["m1", "m2"], "estimated_weeks": 4,
    }))

    result = planning_agent({"idea_text": "f", "research_report": {}})

    assert "python" in result["summary"]
    assert "4 hafta" in result["summary"]


def test_coding_agent_counts_files(monkeypatch):
    monkeypatch.setattr(agents, "call_llm_with_model", _fake_llm({
        "files": [{"path": "main.py", "content": "print(1)"}],
    }))

    result = coding_agent({"idea_text": "f", "planning_report": {}})

    assert "1 dosya" in result["summary"]
    assert result["full_output"]["files"][0]["path"] == "main.py"


def test_marketing_agent_summary(monkeypatch):
    monkeypatch.setattr(agents, "call_llm_with_model", _fake_llm({
        "positioning": "P", "channels": ["x"], "campaign_ideas": ["c1", "c2"],
    }))

    result = marketing_agent({"idea_text": "f", "research_report": {}})

    assert "1 kanal" in result["summary"]
    assert "2 kampanya" in result["summary"]


def test_testing_agent_without_pipeline(monkeypatch):
    monkeypatch.setattr(agents, "call_llm_with_model", _fake_llm({
        "findings": [{"severity": "minor", "description": "d", "file": "f"}],
        "recommended_action": "approve",
    }))

    result = run_testing_agent({"coding_report": {}, "pipeline_id": None})

    assert "1 bulgu" in result["summary"]
    assert result["full_output"]["quality_report"] is None


def test_testing_agent_forces_blocking_on_failed_quality(monkeypatch, tmp_path):
    """Kalite motoru 'fail' verirse, model ne derse desin karar request_changes olmalı."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(agents, "get_workspace_path", lambda pid: ws)
    monkeypatch.setattr(
        agents, "run_pipeline",
        lambda path: SimpleNamespace(to_dict=lambda: {"overall_status": "fail", "results": []}),
    )
    monkeypatch.setattr(agents, "call_llm_with_model", _fake_llm({
        "findings": [], "recommended_action": "approve",
    }))

    result = run_testing_agent({"coding_report": {}, "pipeline_id": "p1"})

    findings = result["full_output"]["findings"]
    assert any(f["severity"] == "blocking" for f in findings)
    assert result["full_output"]["recommended_action"] == "request_changes"
    assert result["full_output"]["quality_report"]["overall_status"] == "fail"


def test_agent_handles_llm_exception(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("ağ hatası")

    monkeypatch.setattr(agents, "call_llm_with_model", boom)

    result = research_agent({"idea_text": "f"})

    assert "başarısız oldu" in result["summary"]
    assert result["full_output"]["error"] == "ağ hatası"
    # Çağrı hiç başarılı olmadığı için istenen model raporlanır.
    assert result["model_used"] == "claude-sonnet-5-5"


def test_agent_handles_max_tokens_stop(monkeypatch):
    monkeypatch.setattr(
        agents, "call_llm_with_model",
        lambda **kwargs: ("kısmi", "max_tokens", "gpt-6-luna"),
    )

    result = research_agent({"idea_text": "f"})

    assert "max_tokens" in result["summary"]
    assert result["full_output"]["truncated"] is True
    assert result["model_used"] == "gpt-6-luna"


def test_append_revision_note():
    assert _append_revision_note("p", None) == "p"
    assert "geri bildirim" in _append_revision_note("p", "düzelt")
