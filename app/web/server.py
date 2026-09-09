"""本地 HTTP 接口与静态前端，同源访问，不向前端返回密钥。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import PROJECT_ROOT, ConfigError, load_config
from app.io.loader import LoaderError
from app.io.workspace import artifact_path, parse_upload
from app.web.schemas import MAX_BODY_BYTES, MAX_UPLOAD_BYTES, RunRequest
from app.web.service import BusyError, Workspace

STATIC = Path(__file__).parent / "static"


def create_app(root: Path = PROJECT_ROOT, config_path: Path | None = None) -> FastAPI:
    config = load_config(root=root, config_path=config_path, require_secrets=False)
    workspace = Workspace(config, config_path)
    app = FastAPI(title="Hy-SurveyAgent Workspace", docs_url=None, redoc_url=None)
    app.state.workspace = workspace
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )
    markdown = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image")

    @app.middleware("http")
    async def local_only(request: Request, call_next: Any) -> Any:
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (
            origin
            and (
                urlsplit(origin).netloc != request.headers.get("host")
                or urlsplit(origin).scheme != request.url.scheme
            )
        ):
            return JSONResponse({"detail": "仅允许从本地工作台访问。"}, status_code=403)
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "请使用 JSON 请求。"}, status_code=415)
            too_large = JSONResponse(
                {"detail": f"文件过大，请使用小于 {MAX_UPLOAD_BYTES // 1_000_000} MB 的论文集。"},
                status_code=413,
            )
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
                return too_large
            # 用公开的 body() 读取：它会缓存请求体，供下游路由再次读取。
            if len(await request.body()) > MAX_BODY_BYTES:
                return too_large
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"detail": "输入不符合要求，请检查主题、问题数量和论文文件。"}, status_code=422
        )

    @app.get("/api/settings")
    def settings() -> dict[str, Any]:
        ready = True
        try:
            load_config(root=root, config_path=config_path, require_secrets=True)
        except (ConfigError, OSError, ValueError):
            ready = False
        return {
            "model": config.model.name,
            "concurrency": config.runtime.max_concurrency,
            "configured": ready,
            "max_upload_bytes": MAX_UPLOAD_BYTES,
        }

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        return workspace.list_runs()

    @app.post("/api/runs", status_code=202)
    def submit(request: RunRequest) -> dict[str, str]:
        try:
            papers = parse_upload(request.filename, request.content)
            return {"id": workspace.submit(request, papers)}
        except LoaderError as exc:
            raise HTTPException(422, str(exc)) from None
        except BusyError as exc:
            raise HTTPException(409, str(exc)) from None
        except (ConfigError, OSError, ValueError):
            raise HTTPException(
                422,
                "无法启动任务。请检查运行配置；生成模式需先复制 "
                "API_key.conf.example 为 API_key.conf 并填写配置。",
            ) from None

    @app.get("/api/runs/{run_id}")
    def detail(run_id: str) -> dict[str, Any]:
        try:
            result = workspace.detail(run_id)
        except FileNotFoundError:
            raise HTTPException(404, "任务不存在。") from None
        artifacts = result["artifacts"]
        result["survey_html"] = markdown.render(
            artifacts.get("final.md") or artifacts.get("draft.md") or ""
        )
        return result

    @app.get("/api/runs/{run_id}/status")
    def status(run_id: str) -> dict[str, Any]:
        """运行中轮询用的轻量接口：只返回状态与阶段日志，不携带产物全文。"""
        try:
            return workspace.status(run_id)
        except FileNotFoundError:
            raise HTTPException(404, "任务不存在。") from None

    @app.get("/api/runs/{run_id}/files/{name}")
    def download(run_id: str, name: str) -> FileResponse:
        try:
            path = artifact_path(config.runs_dir(), run_id, name)
        except FileNotFoundError:
            raise HTTPException(404, "产物尚未生成或不可下载。") from None
        return FileResponse(
            path, filename=f"{run_id}-{name}", media_type="application/octet-stream"
        )

    @app.get("/api/example")
    def example() -> dict[str, str]:
        path = root / "examples" / "papers_vlm.json"
        if not path.is_file():
            raise HTTPException(404, "当前目录没有示例论文集。")
        return {"filename": path.name, "content": path.read_text(encoding="utf-8")}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Hy-SurveyAgent 本地研究工作台")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    uvicorn.run(create_app(config_path=args.config), host="127.0.0.1", port=args.port)
