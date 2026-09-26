"""Chạy một tiến trình nền, giữ log để giao diện hỏi định kỳ."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import config

MAX_LOG_LINES = 800
MAX_HISTORY = 50
PROGRESS = re.compile(r"\[(\d+)\s*/\s*(\d+)[^\]]*\]")
HISTORY_PATH = config.OUTPUT_DIR / "lich_su_tac_vu.json"


class Job:
    def __init__(self, kind: str, label: str, argv: list[str], expected: int = 0,
                 details: dict | None = None):
        self.kind = kind
        self.label = label
        self.argv = argv
        self.expected = expected
        self.done = 0
        self.total = expected
        self.lines = deque(maxlen=MAX_LOG_LINES)
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.finished_at: str | None = None
        self.returncode: int | None = None
        self.stopping = False
        self.process: subprocess.Popen | None = None
        self.details = details or {}

    @property
    def running(self) -> bool:
        return self.returncode is None

    def as_dict(self) -> dict[str, Any]:
        percent = round(self.done * 100 / self.total) if self.total else 0
        return {
            "kind": self.kind, "label": self.label, "command": " ".join(self.argv),
            "running": self.running, "stopping": self.stopping,
            "done": self.done, "total": self.total, "percent": min(percent, 100),
            "lines": list(self.lines), "started_at": self.started_at,
            "finished_at": self.finished_at, "returncode": self.returncode,
            "details": self.details,
        }


class JobRunner:
    def __init__(self):
        self.current: Job | None = None
        self.history: deque[dict] = deque(self._load_history(), maxlen=MAX_HISTORY)
        self.lock = threading.Lock()

    @staticmethod
    def _load_history() -> list[dict]:
        try:
            value = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, ValueError):
            return []

    def _save_history(self) -> None:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = HISTORY_PATH.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(list(self.history), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(HISTORY_PATH)

    def status(self) -> dict:
        with self.lock:
            return {"current": self.current.as_dict() if self.current else None,
                    "history": list(self.history)}

    def start_crawl(self, params: dict) -> dict:
        languages = params["languages"]
        expected = int(params["limit"]) * len(languages)
        argv = self._worker_command("crawl") + [
            "--city-id", str(params["city_id"]),
            "--province-id", str(params.get("province_id") or 0),
            "--country-id", str(params["country_id"]),
            "--city-name", params["city_name"],
            "--country-name", params["country_name"],
            "--limit", str(params["limit"]),
            "--languages", *languages,
        ]
        if params.get("continue_mode"):
            argv.append("--continue-mode")
        details = {
            "city_id": int(params["city_id"]), "city_name": params["city_name"],
            "limit": int(params["limit"]),
            "languages": list(languages), "continue_mode": bool(params.get("continue_mode")),
        }
        return self._start(Job("crawl", "Cào dữ liệu Trip.com", argv, expected, details))

    def start_cookie(self, languages: list[str]) -> dict:
        argv = self._worker_command("cookie") + ["--languages", *languages]
        return self._start(Job("cookie", "Lấy lại cookie", argv,
                               details={"languages": list(languages)}))

    def clear_history(self) -> dict:
        with self.lock:
            self.history.clear()
            self._save_history()
            return {"ok": True}

    @staticmethod
    def _worker_command(kind: str) -> list[str]:
        """Bản cài gọi lại backend EXE; mã nguồn gọi đúng script Python."""
        if getattr(sys, "frozen", False):
            return [sys.executable, "--worker", kind]
        script = "crawl_pipeline.py" if kind == "crawl" else "cookie_refresh.py"
        return [sys.executable, "-u", str(config.ROOT / "src" / script)]

    def _start(self, job: Job) -> dict:
        with self.lock:
            if self.current and self.current.running:
                raise RuntimeError("Một tác vụ khác đang chạy. Hãy chờ hoặc bấm Dừng.")
            # Khi chạy mã nguồn, không ép worker vào tiến trình ẩn: một số cấu hình
            # bảo mật Windows chặn mạng của Chrome sinh từ tiến trình NO_WINDOW.
            # Backend đóng gói vẫn ẩn console để người dùng không thấy cửa sổ đen.
            flags = (subprocess.CREATE_NO_WINDOW
                     if sys.platform == "win32" and getattr(sys, "frozen", False) else 0)
            job.process = subprocess.Popen(
                job.argv,
                cwd=str(config.ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
            self.current = job
            threading.Thread(target=self._pump, args=(job,), daemon=True).start()
            return job.as_dict()

    def _pump(self, job: Job) -> None:
        assert job.process and job.process.stdout
        for raw_line in job.process.stdout:
            line = raw_line.rstrip("\r\n")
            with self.lock:
                job.lines.append(line)
                match = PROGRESS.search(line)
                if match:
                    current, total = map(int, match.groups())
                    # Khi sang ngôn ngữ thứ hai, cộng phần đã hoàn tất trước đó.
                    if current < job.done % max(total, 1):
                        job.done = (job.done // max(total, 1) + 1) * total
                    job.done = min(job.expected or total, (job.done // max(total, 1)) * total + current)
                    job.total = job.expected or total
        code = job.process.wait()
        with self.lock:
            job.returncode = code
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            self.history.appendleft(job.as_dict())
            self._save_history()

    def stop(self) -> dict:
        with self.lock:
            job = self.current
            if not job or not job.running or not job.process:
                raise RuntimeError("Không có tác vụ nào đang chạy.")
            job.stopping = True
            job.lines.append("Đang dừng theo yêu cầu…")
            job.process.terminate()
            return job.as_dict()
