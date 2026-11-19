import re
import subprocess
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from app.paths import COOKIE_PATH, LOG_DIR, PROJECT_ROOT, ensure_directories
from app.security import protect_text, unprotect_text, validate_login_cookie
from app.store import (
    ActiveTaskExistsError,
    create_task,
    get_task,
    initialize,
    list_tasks,
)


app = FastAPI(title="抖音主页归档器", version="0.1.0")
STATIC_DIR = Path(__file__).with_name("static")
DOUYIN_LINK = re.compile(r"https?\\?://[^\s]+", re.IGNORECASE)


class CookieRequest(BaseModel):
    cookie: str = Field(min_length=10, max_length=20000)


class DownloadRequest(BaseModel):
    profile: str = Field(min_length=8, max_length=5000)
    mode: Literal["auto", "post", "one", "mix"] = "auto"
    interval: str = Field(default="all", max_length=21)
    max_counts: int = Field(default=0, ge=0, le=100000)

    @field_validator("profile")
    @classmethod
    def normalize_profile(cls, value: str) -> str:
        match = DOUYIN_LINK.search(value.replace("https\\://", "https://"))
        if not match:
            raise ValueError("没有找到抖音链接")
        url = match.group(0).rstrip("。，,;；")
        host = (urlparse(url).hostname or "").lower()
        allowed = host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")
        if not allowed:
            raise ValueError("只接受抖音官方域名链接")
        return url

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, value: str) -> str:
        if value == "all" or re.fullmatch(r"\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}", value):
            return value
        raise ValueError("日期范围应为 all 或 YYYY-MM-DD|YYYY-MM-DD")


MODE_LABELS = {"post": "用户主页", "one": "单个作品", "mix": "合集/短剧"}


def classify_douyin_url(final_url: str) -> str:
    parsed = urlparse(final_url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    if "/share/user/" in path or "/user/" in path:
        return "post"
    if any(marker in path for marker in ("/collection/", "/mix/", "/short-drama/")):
        return "mix"
    if any(
        marker in path
        for marker in ("/video/", "/note/", "/share/video/", "/share/slides/")
    ) or "modal_id" in query:
        return "one"
    raise ValueError("无法识别抖音链接类型")


async def detect_douyin_mode(url: str) -> tuple[str, str]:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail=f"抖音链接解析失败：{exc}") from exc

    final_url = str(response.url)
    try:
        return classify_douyin_url(final_url), final_url
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="无法自动识别该抖音链接，请手动选择主页、单个作品或合集模式",
        ) from exc


@app.on_event("startup")
def startup() -> None:
    ensure_directories()
    initialize()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status() -> dict:
    cookie_configured = False
    if COOKIE_PATH.exists():
        try:
            validate_login_cookie(unprotect_text(COOKIE_PATH.read_bytes()))
            cookie_configured = True
        except (OSError, UnicodeDecodeError, ValueError):
            pass
    return {
        "cookie_configured": cookie_configured,
        "project_root": str(PROJECT_ROOT),
    }


@app.post("/api/settings/cookie")
def save_cookie(request: CookieRequest) -> dict:
    ensure_directories()
    cookie = request.cookie.strip()
    try:
        validate_login_cookie(cookie)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    encrypted = protect_text(cookie)
    COOKIE_PATH.write_bytes(encrypted)
    return {"ok": True, "message": "Cookie 已使用 Windows DPAPI 加密保存"}


@app.post("/api/tasks")
async def start_download(request: DownloadRequest) -> dict:
    if not status()["cookie_configured"]:
        raise HTTPException(status_code=409, detail="请先配置完整的登录 Cookie")
    mode = request.mode
    if mode == "auto":
        mode, _ = await detect_douyin_mode(request.profile)
    try:
        task = create_task(request.profile, request.interval, request.max_counts, mode)
    except ActiveTaskExistsError as exc:
        raise HTTPException(
            status_code=409, detail="该主页已有下载任务正在排队或运行，请勿重复提交"
        ) from exc
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [sys.executable, "-m", "app.worker", "--task-id", task["id"]],
        cwd=PROJECT_ROOT,
        creationflags=creation_flags,
        close_fds=True,
    )
    task["detected_label"] = MODE_LABELS[mode]
    return task


@app.get("/api/tasks")
def tasks() -> list[dict]:
    return list_tasks()


@app.get("/api/tasks/{task_id}")
def task(task_id: str) -> dict:
    try:
        return get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.get("/api/tasks/{task_id}/log", response_class=PlainTextResponse)
def task_log(task_id: str) -> str:
    try:
        get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    log_path = LOG_DIR / f"{task_id}.log"
    if not log_path.exists():
        return "暂时没有日志"
    return log_path.read_text(encoding="utf-8", errors="replace")[-50000:]

