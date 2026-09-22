"""
Workspace ve Quality Checker entegrasyon birim testleri.
"""
import pytest
from pathlib import Path

import workspace
import orchestrator
from quality_checker.models import Status, CheckResult, PipelineReport, Issue
from quality_checker.runner import run_pipeline
from llm_gateway import detect_provider


def test_detect_provider():
    assert detect_provider("claude-sonnet-5") == "anthropic"
    assert detect_provider("deepseek-coder") == "deepseek"
    assert detect_provider("deepseek-v4") == "deepseek"
    assert detect_provider("gemini-2.5-flash") == "gemini"
    assert detect_provider("gpt-4o") == "openai"
    assert detect_provider("o3-mini") == "openai"


def test_workspace_write_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "WORKSPACE_BASE_DIR", tmp_path)

    pid = "test-pipe-123"
    files = [
        {"path": "main.py", "content": "print('hello world')\n"},
        {"path": "utils/helper.py", "content": "def add(a, b):\n    return a + b\n"},
    ]

    ws_path = workspace.write_files_to_workspace(pid, files)
    assert ws_path.exists()
    assert (ws_path / "main.py").exists()
    assert (ws_path / "utils" / "helper.py").exists()

    read_files = workspace.read_workspace_files(pid)
    assert len(read_files) == 2
    paths = {f["path"] for f in read_files}
    assert "main.py" in paths
    assert "utils/helper.py" in paths

    workspace.clean_workspace(pid)
    assert not ws_path.exists()


def test_workspace_path_traversal_prevention(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "WORKSPACE_BASE_DIR", tmp_path)

    pid = "test-pipe-evil"
    files = [{"path": "../../evil.py", "content": "malicious"}]

    with pytest.raises(ValueError, match="Güvenlik ihlali"):
        workspace.write_files_to_workspace(pid, files)


def test_quality_checker_on_clean_python_code(tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text("def greet(name: str) -> str:\n    return f'Hello {name}'\n", encoding="utf-8")

    report = run_pipeline(tmp_path)
    assert isinstance(report, PipelineReport)
    assert "python" in report.project_types
    # Temiz kod üzerinde ruff, mypy, bandit, vulture geçer
    assert report.overall_status in (Status.PASS, Status.WARN)


def test_dashboard_and_files_endpoints(client, monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "WORKSPACE_BASE_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "AGENT_MAP", {
        "research": lambda context, revision_note=None, model=None: {"summary": "ok", "full_output": {}},
        "planning": lambda context, revision_note=None, model=None: {"summary": "ok", "full_output": {}},
        "coding": lambda context, revision_note=None, model=None: {"summary": "ok", "full_output": {"files": [{"path": "app.py", "content": "x = 1"}]}},
        "testing": lambda context, revision_note=None, model=None: {"summary": "ok", "full_output": {}},
        "marketing": lambda context, revision_note=None, model=None: {"summary": "ok", "full_output": {}},
    })

    # 1. Dashboard HTML endpoint kontrolü
    resp = client.get("/")
    assert resp.status_code == 200

    # 2. Model catalog endpoint
    resp = client.get("/models/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert "deepseek" in data
    assert "gemini" in data

    # 3. Pipeline oluştur ve workspace files endpointini test et
    pipe_resp = client.post("/pipelines", json={"idea_text": "Dosya testi"})
    assert pipe_resp.status_code == 200
    pid = pipe_resp.json()["id"]

    # Coding aşamasını çalıştırarak otomatik dosya yazılmasını sağla
    client.post(f"/pipelines/{pid}/approve")  # planning'e geçer
    client.post(f"/pipelines/{pid}/approve")  # coding çalışır ve app.py yazar

    resp = client.get(f"/pipelines/{pid}/workspace/files")
    assert resp.status_code == 200
    files = resp.json()
    assert len(files) == 1
    assert files[0]["path"] == "app.py"
