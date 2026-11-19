import argparse
import asyncio
import contextlib
import re
import sys
import threading
from pathlib import Path
from typing import TextIO

from app.paths import COOKIE_PATH, DOWNLOAD_DIR, LOG_DIR, PROJECT_ROOT, ensure_directories
from app.security import unprotect_text, validate_login_cookie
from app.store import get_task, initialize, update_progress, update_task


ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
COMPLETE_LINE = re.compile(r"\[\s*完成\s*\]")
FINAL_COUNT = re.compile(r"共处理\s*(\d+)\s*个作品")
FAILED_COUNT = re.compile(r"有\s*(\d+)\s*个文件下载失败")


async def fetch_profile_summary(profile_url: str, cookie: str) -> tuple[str, int]:
    from f2.apps.douyin.handler import DouyinHandler
    from f2.apps.douyin.utils import ClientConfManager, SecUserIdFetcher

    kwargs = {
        "cookie": cookie,
        "headers": ClientConfManager.headers(),
        "proxies": ClientConfManager.proxies(),
        "timeout": 10,
        "max_retries": 5,
        "max_connections": 3,
        "max_tasks": 5,
    }
    sec_user_id = await SecUserIdFetcher.get_sec_user_id(profile_url, kwargs["proxies"])
    profile = await DouyinHandler(kwargs).fetch_user_profile(sec_user_id)
    if profile is None:
        raise RuntimeError("无法读取主页信息")
    return str(profile.nickname or sec_user_id), int(profile.aweme_count or 0)


async def fetch_mix_total(mix_url: str, cookie: str) -> int:
    from f2.apps.douyin.crawler import DouyinCrawler
    from f2.apps.douyin.filter import UserMixFilter
    from f2.apps.douyin.model import UserMix
    from f2.apps.douyin.utils import ClientConfManager, MixIdFetcher

    kwargs = {
        "cookie": cookie,
        "headers": ClientConfManager.headers(),
        "proxies": ClientConfManager.proxies(),
        "timeout": 10,
        "max_retries": 5,
        "max_connections": 3,
        "max_tasks": 5,
    }
    mix_id = await MixIdFetcher.get_mix_id(mix_url, proxies=kwargs["proxies"])
    cursor = 0
    aweme_ids: set[str] = set()
    async with DouyinCrawler(kwargs) as crawler:
        for _ in range(100):
            response = await crawler.fetch_user_mix(
                UserMix(cursor=cursor, count=20, mix_id=mix_id)
            )
            page = UserMixFilter(response)
            aweme_ids.update(str(item) for item in (page.aweme_id or []) if item)
            next_cursor = page.max_cursor
            if not page.has_more or next_cursor in (None, cursor):
                break
            cursor = next_cursor
        else:
            raise RuntimeError("合集分页超过安全上限")
    return len(aweme_ids)


class ProgressLogWriter:
    def __init__(self, target: TextIO, task_id: str, total_items: int) -> None:
        self.target = target
        self.task_id = task_id
        self.total_items = total_items
        self.processed = 0
        self.downloaded = 0
        self.failed = 0
        self.buffer = ""
        self.lock = threading.Lock()

    def write(self, text: str) -> int:
        with self.lock:
            self.target.write(text)
            self.target.flush()
            self.buffer += text
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                self._handle_line(ANSI_ESCAPE.sub("", line).strip())
        return len(text)

    def flush(self) -> None:
        with self.lock:
            self.target.flush()

    def _advance(self, *, downloaded: bool = False, failed: bool = False, item: str = "") -> None:
        self.processed += 1
        self.downloaded += int(downloaded)
        self.failed += int(failed)
        update_progress(
            self.task_id,
            stage="downloading",
            processed_items=self.processed,
            downloaded_items=self.downloaded,
            failed_items=self.failed,
            current_item=item[-300:],
            message=f"正在处理第 {self.processed}/{self.total_items or '?'} 个作品",
        )

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        if COMPLETE_LINE.search(line):
            self._advance(downloaded=True, item=line)
        elif "文件已存在且完整，跳过下载" in line:
            self._advance(item=line.split("跳过下载:", 1)[-1].strip())
        elif "所有链接都无法下载" in line:
            self._advance(failed=True, item="视频地址下载失败")

        final_match = FINAL_COUNT.search(line)
        if final_match:
            final_total = int(final_match.group(1))
            self.processed = max(self.processed, final_total)
            self.total_items = max(self.total_items, self.processed)
            update_progress(
                self.task_id,
                stage="finalizing",
                total_items=self.total_items,
                processed_items=self.processed,
                message=f"已处理 {self.processed}/{self.total_items} 个作品，正在汇总结果",
            )

        failed_match = FAILED_COUNT.search(line)
        if failed_match:
            self.failed = int(failed_match.group(1))
            update_progress(self.task_id, failed_items=self.failed)


def run(task_id: str) -> int:
    ensure_directories()
    initialize()
    task = get_task(task_id)
    mode = task.get("mode") or "post"
    log_path = LOG_DIR / f"{task_id}.log"

    if not COOKIE_PATH.exists():
        update_task(task_id, "failed", "尚未配置登录 Cookie")
        return 2

    update_task(task_id, "running", "正在识别并准备下载")
    update_progress(task_id, stage="preparing", message="正在识别并准备下载")
    cookie = unprotect_text(COOKIE_PATH.read_bytes())
    try:
        validate_login_cookie(cookie)
    except ValueError as exc:
        update_task(task_id, "failed", str(exc))
        return 2

    if mode == "post":
        try:
            nickname, total_items = asyncio.run(
                fetch_profile_summary(task["profile_url"], cookie)
            )
            update_progress(
                task_id,
                stage="downloading",
                total_items=total_items,
                message=f"主页获取成功：{nickname}，共 {total_items} 个作品",
            )
        except Exception as exc:
            update_task(task_id, "failed", f"主页信息获取失败：{exc}")
            update_progress(task_id, stage="failed")
            return 1
    elif mode == "one":
        total_items = 1
        update_progress(
            task_id,
            stage="downloading",
            total_items=1,
            message="已识别为单个视频或图文作品",
        )
    else:
        try:
            update_progress(
                task_id,
                stage="fetching_collection",
                message="已识别为合集或短剧，正在统计作品总数",
            )
            total_items = asyncio.run(fetch_mix_total(task["profile_url"], cookie))
            update_progress(
                task_id,
                stage="downloading",
                total_items=total_items,
                message=f"合集获取成功，共 {total_items} 个作品",
            )
        except Exception as exc:
            update_task(task_id, "failed", f"合集信息获取失败：{exc}")
            update_progress(task_id, stage="failed")
            return 1
    arguments = [
        "--no-log-file",
        "dy",
        "--url",
        task["profile_url"],
        "--mode",
        mode,
        "--path",
        str(DOWNLOAD_DIR),
        "--cookie",
        cookie,
        "--max-counts",
        str(task["max_counts"]),
        "--page-counts",
        "20",
        "--max-connections",
        "3",
        "--max-tasks",
        "5",
    ]
    if mode == "post":
        arguments.extend(["--interval", task["interval"]])

    try:
        from f2.cli.cli_commands import main as f2_main

        with log_path.open("a", encoding="utf-8") as log_file:
            progress_log = ProgressLogWriter(log_file, task_id, total_items)
            with contextlib.redirect_stdout(progress_log), contextlib.redirect_stderr(progress_log):
                result = f2_main(args=arguments, standalone_mode=False)
        if result not in (None, 0):
            update_task(task_id, "failed", f"F2 退出码：{result}，请查看任务日志")
            update_progress(task_id, stage="failed")
            return int(result)
        final_processed = max(total_items, progress_log.processed)
        final_total = max(total_items, final_processed)
        update_task(task_id, "completed", "下载任务已完成")
        update_progress(
            task_id,
            stage="completed",
            total_items=final_total,
            processed_items=final_processed,
        )
        return 0
    except SystemExit as exc:
        code = int(exc.code or 0)
        if code == 0:
            final_processed = max(total_items, progress_log.processed)
            final_total = max(total_items, final_processed)
            update_task(task_id, "completed", "下载任务已完成")
            update_progress(
                task_id,
                stage="completed",
                total_items=final_total,
                processed_items=final_processed,
            )
        else:
            update_task(task_id, "failed", f"F2 退出码：{code}，请查看任务日志")
            update_progress(task_id, stage="failed")
        return code
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as log_file:
            import traceback

            traceback.print_exc(file=log_file)
        update_task(task_id, "failed", f"{type(exc).__name__}: {exc}")
        update_progress(task_id, stage="failed")
        return 1
    finally:
        cookie = ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.task_id))


if __name__ == "__main__":
    main()

