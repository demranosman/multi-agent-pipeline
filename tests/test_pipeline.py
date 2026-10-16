"""
Bu testler GERÇEK Anthropic API'yi çağırmaz - orchestrator.AGENT_MAP'i
sahte (mock) ajan fonksiyonlarıyla değiştirir. Amaç: API anahtarı ya da
ağ bağlantısı olmadan, akışın (onay kapıları, revizyon döngüsü,
eskalasyon, soru-cevap) doğru çalıştığını doğrulamak.

Çalıştırmak için:
    pip install -r requirements.txt -r requirements-dev.txt
    pytest tests/ -v
"""
import orchestrator
import workspace


def _mock_agent(name):
    def _agent(context, revision_note=None, model=None):
        return {
            "summary": f"{name} tamamlandı" + (f" (rev: {revision_note})" if revision_note else ""),
            "full_output": {"stage": name, "revision_note": revision_note},
        }
    return _agent


MOCK_AGENT_MAP = {
    "research": _mock_agent("research"),
    "planning": _mock_agent("planning"),
    "coding": _mock_agent("coding"),
    "testing": _mock_agent("testing"),
    "marketing": _mock_agent("marketing"),
}


def test_happy_path_completes_all_stages(client, monkeypatch):
    monkeypatch.setattr(orchestrator, "AGENT_MAP", MOCK_AGENT_MAP)

    resp = client.post("/pipelines", json={"idea_text": "Kedi sahipleri için hatırlatma uygulaması"})
    assert resp.status_code == 200
    pipeline = resp.json()
    pid = pipeline["id"]
    assert pipeline["status"] == "waiting_approval"
    assert pipeline["current_stage"] == "research"

    for expected_next_stage in ["planning", "coding", "testing", "marketing"]:
        resp = client.post(f"/pipelines/{pid}/approve")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_stage"] == expected_next_stage
        assert body["status"] == "waiting_approval"

    resp = client.post(f"/pipelines/{pid}/approve")  # marketing'i onayla -> tamamlanmalı
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    logs = client.get(f"/pipelines/{pid}/logs").json()
    assert len(logs) == 5
    assert {l["stage"] for l in logs} == {"research", "planning", "coding", "testing", "marketing"}


def test_log_records_actual_fallback_model(client, monkeypatch):
    """Ajan fallback modelini bildirirse, log istenen değil gerçek modeli göstermeli."""
    def _agent(context, revision_note=None, model=None):
        return {"summary": "ok", "full_output": {}, "model_used": "gpt-6-astra"}

    monkeypatch.setattr(orchestrator, "AGENT_MAP", {**MOCK_AGENT_MAP, "research": _agent})

    pid = client.post("/pipelines", json={"idea_text": "Fallback testi"}).json()["id"]

    logs = client.get(f"/pipelines/{pid}/logs").json()
    research_log = next(l for l in logs if l["stage"] == "research")
    assert research_log["model"] == "gpt-6-astra"


def test_blocking_correction_triggers_revision(client, monkeypatch):
    monkeypatch.setattr(orchestrator, "AGENT_MAP", MOCK_AGENT_MAP)

    pid = client.post("/pipelines", json={"idea_text": "Fikir X"}).json()["id"]
    client.post(f"/pipelines/{pid}/approve")  # research -> planning

    resp = client.post(f"/pipelines/{pid}/messages", json={
        "from_agent": "coding_agent",
        "to_agent": "planning_agent",
        "message_type": "correction_request",
        "severity": "blocking",
        "content": "Milestone sırası yanlış",
        "stage_reference": "planning",
    })
    assert resp.status_code == 200
    message_id = resp.json()["id"]

    resp = client.post(f"/pipelines/{pid}/rerun")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_stage"] == "planning"
    assert body["status"] == "waiting_approval"

    logs = client.get(f"/pipelines/{pid}/logs").json()
    planning_logs = [l for l in logs if l["stage"] == "planning"]
    assert len(planning_logs) == 2
    assert "Milestone sırası yanlış" in planning_logs[-1]["summary"]

    messages = client.get(f"/pipelines/{pid}/messages").json()
    processed = next(m for m in messages if m["id"] == message_id)
    assert processed["status"] == "processed"
    assert processed["resolved_log_id"] == planning_logs[-1]["id"]


def test_escalation_after_max_revisions(client, monkeypatch):
    monkeypatch.setattr(orchestrator, "AGENT_MAP", MOCK_AGENT_MAP)

    pid = client.post("/pipelines", json={"idea_text": "Fikir Y"}).json()["id"]
    client.post(f"/pipelines/{pid}/approve")  # planning'e geç

    resp = None
    for i in range(2):  # varsayılan max_revision_rounds=3 -> 2. düzeltmede eskale olmalı
        client.post(f"/pipelines/{pid}/messages", json={
            "from_agent": "coding_agent",
            "to_agent": "planning_agent",
            "message_type": "correction_request",
            "severity": "blocking",
            "content": f"Düzeltme talebi {i}",
            "stage_reference": "planning",
        })
        resp = client.post(f"/pipelines/{pid}/rerun")

    assert resp.json()["status"] == "escalated"

    resp = client.post(f"/pipelines/{pid}/approve")  # kullanıcı yine de ilerletebilmeli
    assert resp.status_code == 200
    assert resp.json()["current_stage"] == "coding"


def test_question_and_answer_flow(client, monkeypatch):
    def planning_with_question(context, revision_note=None, model=None):
        if revision_note is None:
            return {
                "summary": "Ödeme sağlayıcısı netleşmeden devam edemiyorum.",
                "full_output": {"status": "needs_input"},
                "question": "Stripe mi iyzico mu kullanılsın?",
            }
        return {
            "summary": f"Plan tamamlandı (cevap: {revision_note}).",
            "full_output": {"payment_provider": revision_note},
        }

    mock_map = dict(MOCK_AGENT_MAP)
    mock_map["planning"] = planning_with_question
    monkeypatch.setattr(orchestrator, "AGENT_MAP", mock_map)

    pid = client.post("/pipelines", json={"idea_text": "Fikir Z"}).json()["id"]
    resp = client.post(f"/pipelines/{pid}/approve")  # planning çalışır, soru sorar
    assert resp.json()["status"] == "waiting_response"

    messages = client.get(f"/pipelines/{pid}/messages").json()
    question = next(m for m in messages if m["message_type"] == "question")
    assert question["requires_response"] is True

    resp = client.post(
        f"/pipelines/{pid}/messages/{question['id']}/answer",
        json={"answer": "iyzico"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "waiting_approval"
    assert body["current_stage"] == "planning"

    logs = client.get(f"/pipelines/{pid}/logs").json()
    planning_logs = [l for l in logs if l["stage"] == "planning"]
    assert len(planning_logs) == 2
    assert planning_logs[-1]["full_output"]["payment_provider"] == "iyzico"


# --- Faz kapıları: contract / scope / placeholder ---------------------------

def _agent_returning(full_output):
    def _agent(context, revision_note=None, model=None):
        return {"summary": "ok", "full_output": full_output}
    return _agent


def test_coding_placeholder_blocks_and_writes_nothing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "WORKSPACE_BASE_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "AGENT_MAP", {
        **MOCK_AGENT_MAP,
        "planning": _agent_returning({"scope_patterns": ["app.py"]}),
        "coding": _agent_returning({"files": [{"path": "app.py", "content": "# TODO: bitir"}]}),
    })

    pid = client.post("/pipelines", json={"idea_text": "placeholder"}).json()["id"]
    client.post(f"/pipelines/{pid}/approve")                 # research -> planning
    body = client.post(f"/pipelines/{pid}/approve").json()   # planning -> coding (kapı)

    assert body["status"] == "escalated"
    assert body["current_stage"] == "coding"
    messages = client.get(f"/pipelines/{pid}/messages").json()
    assert any(m["from_agent"] == "gate" and "TODO" in m["content"] for m in messages)
    assert client.get(f"/pipelines/{pid}/workspace/files").json() == []


def test_coding_out_of_scope_blocks(client, monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "WORKSPACE_BASE_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "AGENT_MAP", {
        **MOCK_AGENT_MAP,
        "planning": _agent_returning({"scope_patterns": ["app.py"]}),
        "coding": _agent_returning({"files": [{"path": "evil.py", "content": "x = 1"}]}),
    })

    pid = client.post("/pipelines", json={"idea_text": "scope"}).json()["id"]
    client.post(f"/pipelines/{pid}/approve")
    body = client.post(f"/pipelines/{pid}/approve").json()

    assert body["status"] == "escalated"
    messages = client.get(f"/pipelines/{pid}/messages").json()
    assert any("kapsam dışı" in m["content"] for m in messages)
    assert client.get(f"/pipelines/{pid}/workspace/files").json() == []


def test_coding_gate_pass_writes_files(client, monkeypatch, tmp_path):
    """Kapılar temizse dosyalar yazılır ve akış eskisi gibi ilerler."""
    monkeypatch.setattr(workspace, "WORKSPACE_BASE_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "AGENT_MAP", {
        **MOCK_AGENT_MAP,
        "planning": _agent_returning({"scope_patterns": ["app/*"]}),
        "coding": _agent_returning({"files": [{"path": "app/main.py", "content": "x = 1"}]}),
    })

    pid = client.post("/pipelines", json={"idea_text": "temiz"}).json()["id"]
    client.post(f"/pipelines/{pid}/approve")
    body = client.post(f"/pipelines/{pid}/approve").json()

    assert body["status"] == "waiting_approval"
    assert body["current_stage"] == "coding"
    files = client.get(f"/pipelines/{pid}/workspace/files").json()
    assert [f["path"] for f in files] == ["app/main.py"]


def test_contract_snapshot_and_stale_detection():
    """Onaylanan aşamanın çıktısı sonradan değişirse contract ihlali üretilmeli."""
    from database import SessionLocal
    from models import Pipeline, PipelineLog, StageName
    from orchestrator import _contract_violations, _snapshot_contract

    db = SessionLocal()
    try:
        pipeline = Pipeline(idea_text="contract")
        pipeline.current_stage = StageName.planning
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)

        db.add(PipelineLog(
            pipeline_id=pipeline.id, stage=StageName.research, agent="research_agent",
            summary="ilk", full_output={"v": 1}, revision_round=0,
        ))
        db.commit()

        _snapshot_contract(db, pipeline, StageName.research)
        db.commit()
        assert _contract_violations(db, pipeline) == []

        # Onaylı aşama yeniden çalışmış gibi yeni bir log ekle -> hash değişir.
        db.add(PipelineLog(
            pipeline_id=pipeline.id, stage=StageName.research, agent="research_agent",
            summary="yeni", full_output={"v": 2}, revision_round=1,
        ))
        db.commit()

        violations = _contract_violations(db, pipeline)
        assert violations
        assert "research" in violations[0]
    finally:
        db.close()
