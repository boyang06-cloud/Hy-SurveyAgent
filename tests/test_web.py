"""工作台 API 集成测试：真实离线流程与 Mock 模型，不调用在线 API。"""

from __future__ import annotations

import json
import time
from contextlib import nullcontext
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.io.exporter import RunWriter
from app.web.server import create_app
from tests.test_pipeline import scripted_step2_responses


@pytest.fixture
def web(tmp_path: Path, prompt_dir: Path):
    config = tmp_path / "web.yaml"
    config.write_text(f"paths:\n  prompts_dir: {prompt_dir}\n", encoding="utf-8")
    app = create_app(tmp_path, config)
    with TestClient(app) as client:
        yield client, app, tmp_path


def submit_payload(sample_papers, **overrides):
    return {
        "topic": "研究主题",
        "filename": "papers.json",
        "content": json.dumps([paper.to_dict() for paper in sample_papers]),
        "mode": "dry_run",
        **overrides,
    }


def await_run(client, run_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(f"/api/runs/{run_id}").json()
        if result["status"] != "running":
            return result
        time.sleep(0.02)
    pytest.fail("后台任务未在测试时限内结束")


def test_dry_run_full_http_flow_and_download(web, sample_papers):
    client, app, root = web
    assert client.get("/").status_code == 200
    assert client.get("/api/settings").json()["configured"] is False
    assert client.get("/api/runs").json() == []
    response = client.post("/api/runs", json=submit_payload(sample_papers))
    assert response.status_code == 202
    run_id = response.json()["id"]
    result = await_run(client, run_id)
    assert result["status"] == "dry_run"
    assert len(result["stages"]) == 7
    assert result["survey_html"] == ""
    assert result["artifacts"]["verification.json"]["summary"]["total_claims"] == 0
    assert client.get("/api/runs").json()[0]["id"] == run_id
    download = client.get(f"/api/runs/{run_id}/files/result.json")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    assert download.json()["papers"][0]["paper_id"] == "P001"
    meta = json.loads((root / "runs" / run_id / "meta.json").read_text())
    assert meta["web_mode"] == "dry_run"
    assert set(meta["prompts"]) >= {"writer", "citation_verifier"}


def test_generate_reuses_pipeline_and_preserves_evidence(
    web,
    sample_papers,
    scripted_provider,
    monkeypatch,
    prompt_dir,
):
    client, app, root = web
    config = AppConfig(root=root)
    config.paths.prompts_dir = str(prompt_dir)
    provider = scripted_step2_responses(scripted_provider)
    monkeypatch.setattr("app.web.service.load_config", lambda **kwargs: config)
    monkeypatch.setattr(
        "app.web.service.Hy3Adapter.from_config",
        lambda config: nullcontext(provider),
    )
    response = client.post("/api/runs", json=submit_payload(sample_papers, mode="generate"))
    result = await_run(client, response.json()["id"])
    assert result["status"] == "completed"
    assert "driving" in result["survey_html"]
    assert result["verification"]["supported"] == 1
    assert result["verification"]["unverifiable"] == 1
    assert result["artifacts"]["result.json"]["evidence_map"][0]["paper_id"] == "P001"
    assert len(provider.calls) == 7


@pytest.mark.parametrize(
    "overrides",
    [
        {"topic": "  "},
        {"filename": "paper.pdf"},
        {"content": "not json"},
        {"content": "[]"},
        {"research_questions": ["q"] * 21},
        {"research_questions": ["q" * 2001]},
        {"mode": "unknown"},
        {"content": '[{"title":"A","paper_id":"P001"},{"title":"B","paper_id":"P001"}]'},
    ],
)
def test_invalid_upload_never_creates_run(web, sample_papers, overrides):
    client, _, root = web
    response = client.post("/api/runs", json=submit_payload(sample_papers, **overrides))
    assert response.status_code == 422
    assert client.get("/api/runs").json() == []


def test_requires_model_configuration(web, sample_papers):
    client, _, _ = web
    response = client.post("/api/runs", json=submit_payload(sample_papers, mode="generate"))
    assert response.status_code == 422
    assert "API_key.conf.example" in response.json()["detail"]


def test_cross_origin_and_host_are_rejected(web, sample_papers):
    client, _, _ = web
    payload = submit_payload(sample_papers)
    assert (
        client.post("/api/runs", json=payload, headers={"Origin": "https://other.test"}).status_code
        == 403
    )
    assert client.get("/api/runs", headers={"Host": "other.test"}).status_code == 400
    assert client.post("/api/runs", content="{}").status_code == 415
    assert client.get("/api/runs", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_download_allowlist_and_symlink(web):
    client, _, root = web
    run = RunWriter.create(root, "runs", "t-safe")
    run.write_json("task.json", {"topic": "Safe"})
    run.write_text("private.txt", "private")
    outside = root / "outside.md"
    outside.write_text("not an artifact")
    (run.run_dir / "final.md").symlink_to(outside)
    for name in ["private.txt", "meta.json", "web_status.json", "final.md"]:
        assert client.get(f"/api/runs/t-safe/files/{name}").status_code == 404
    assert "final.md" not in client.get("/api/runs/t-safe").json()["artifacts"]
    (root / "runs" / "t-link").symlink_to(run.run_dir)
    assert client.get("/api/runs/t-link").status_code == 404
    assert client.get("/api/runs/not-found").status_code == 404


def test_markdown_cannot_inject_html_or_external_images(web):
    client, _, root = web
    run = RunWriter.create(root, "runs", "t-html")
    run.write_json("task.json", {"topic": "HTML"})
    run.write_text(
        "final.md",
        "<script>alert(1)</script>\n\n![x](https://other.test/x)\n\n[x](javascript:alert(1))",
    )
    response = client.get("/api/runs/t-html")
    html = response.json()["survey_html"]
    assert "<script>" not in html
    assert "<img" not in html
    assert 'href="javascript:' not in html
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_restart_marks_stale_run_interrupted(web):
    client, _, root = web
    run = RunWriter.create(root, "runs", "t-stale")
    run.write_json("task.json", {"topic": "Stale"})
    run.write_json("web_status.json", {"status": "running"})
    assert client.get("/api/runs/t-stale").json()["status"] == "interrupted"


def test_busy_workspace_rejects_second_run(web, sample_papers):
    client, app, _ = web
    app.state.workspace.active.add("t-active")
    response = client.post("/api/runs", json=submit_payload(sample_papers))
    assert response.status_code == 409
    app.state.workspace.active.clear()


def test_background_failure_has_terminal_status(web, sample_papers, monkeypatch):
    client, _, _ = web

    async def fail(*args, **kwargs):
        raise RuntimeError("原始异常详情不应返回浏览器")

    monkeypatch.setattr("app.web.service.run_pipeline", fail)
    response = client.post("/api/runs", json=submit_payload(sample_papers))
    result = await_run(client, response.json()["id"])
    assert result["status"] == "failed"
    assert "原始异常" not in json.dumps(result, ensure_ascii=False)


def test_background_failure_records_error_type_only(web, sample_papers, monkeypatch):
    client, _, root = web

    async def fail(*args, **kwargs):
        raise RuntimeError("原始异常详情不应返回浏览器")

    monkeypatch.setattr("app.web.service.run_pipeline", fail)
    response = client.post("/api/runs", json=submit_payload(sample_papers))
    run_id = response.json()["id"]
    result = await_run(client, run_id)
    assert result["status"] == "failed"
    state = json.loads((root / "runs" / run_id / "web_status.json").read_text())
    assert state["error"] == "RuntimeError"
    assert "原始异常" not in json.dumps(state, ensure_ascii=False)


def test_status_endpoint_is_lightweight_and_consistent(web, sample_papers):
    client, _, _ = web
    response = client.post("/api/runs", json=submit_payload(sample_papers))
    run_id = response.json()["id"]
    await_run(client, run_id)
    status = client.get(f"/api/runs/{run_id}/status").json()
    detail = client.get(f"/api/runs/{run_id}").json()
    assert "artifacts" not in status and "survey_html" not in status
    assert status["status"] == detail["status"]
    assert status["paper_count"] == detail["paper_count"]
    assert [row["stage"] for row in status["stages"]] == [row["stage"] for row in detail["stages"]]
    assert client.get("/api/runs/not-found/status").status_code == 404


def test_empty_artifacts_are_not_listed(web, sample_papers):
    client, _, _ = web
    response = client.post("/api/runs", json=submit_payload(sample_papers))
    result = await_run(client, response.json()["id"])
    # 离线检查只渲染 Prompt，正文产物为空，不应展示为可下载结果。
    assert "draft.md" not in result["artifacts"]
    assert "final.md" not in result["artifacts"]
    assert "papers.json" in result["artifacts"]
