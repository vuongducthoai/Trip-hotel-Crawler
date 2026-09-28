"""Chạy một tiến trình nền, giữ log để giao diện hỏi định kỳ."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import config

MAX_LOG_LINES = 800
MAX_HISTORY = 50
# Nghỉ giữa hai thành phố trong hàng đợi để giảm nguy cơ Trip.com chặn mềm.
QUEUE_PAUSE_SECONDS = int(__import__("os").getenv("QUEUE_PAUSE_SECONDS", "60"))
PROGRESS = re.compile(r"\[(\d+)\s*/\s*(\d+)[^\]]*\]")
HISTORY_PATH = config.OUTPUT_DIR / "lich_su_tac_vu.json"
LOG_DIR = config.OUTPUT_DIR / "logs"
LOG_KEEP_DAYS = int(__import__("os").getenv("LOG_KEEP_DAYS", "30"))


def _prune_logs() -> None:
    """Xoá log cũ hơn LOG_KEEP_DAYS ngày để thư mục không phình mãi."""
    try:
        cutoff = time.time() - LOG_KEEP_DAYS * 86400
        for path in LOG_DIR.glob("*.log"):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        pass


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
        self.log_path: Path | None = None

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
            "log_path": str(self.log_path) if self.log_path else None,
            "finished_at": self.finished_at, "returncode": self.returncode,
            "details": self.details,
        }


class JobRunner:
    def __init__(self):
        self.current: Job | None = None
        self.queue: deque[Job] = deque()
        self.queue_wait_until: float | None = None   # mốc thời gian job kế tiếp được chạy
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
                    "queue": [self._queue_item(j) for j in self.queue],
                    "queue_wait_seconds": (max(0, int(self.queue_wait_until - time.time()))
                                           if self.queue_wait_until else 0),
                    "history": list(self.history)}

    @staticmethod
    def _queue_item(job: Job) -> dict:
        return {"id": id(job), "kind": job.kind, "label": job.label, "details": job.details,
                "expected": job.expected}

    def _crawl_job(self, params: dict) -> Job:
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
        return Job("crawl", f"Cào {params['city_name']}", argv, expected, details)

    def start_crawl(self, params: dict) -> dict:
        return self._start(self._crawl_job(params))

    def enqueue_crawls(self, params_list: list[dict]) -> dict:
        """Nhiều thành phố: chạy cái đầu ngay (nếu rảnh), số còn lại xếp hàng."""
        jobs = [self._crawl_job(p) for p in params_list]
        with self.lock:
            busy = bool(self.current and self.current.running)
            for job in jobs:
                self.queue.append(job)
        if not busy:
            self._start_next_from_queue(delay=0)
        return self.status()

    def remove_from_queue(self, job_id: int) -> dict:
        with self.lock:
            self.queue = deque(j for j in self.queue if id(j) != job_id)
            if not self.queue:
                self.queue_wait_until = None
        return self.status()

    def clear_queue(self) -> dict:
        with self.lock:
            self.queue.clear()
            self.queue_wait_until = None
        return self.status()

    def _start_next_from_queue(self, delay: int) -> None:
        """Chạy job kế tiếp trong hàng đợi sau `delay` giây (chạy ở luồng riêng)."""
        def run():
            if delay:
                with self.lock:
                    self.queue_wait_until = time.time() + delay
                # Đợi nhưng thoát sớm nếu hàng đợi bị xoá.
                for _ in range(delay * 2):
                    time.sleep(0.5)
                    with self.lock:
                        if not self.queue:
                            self.queue_wait_until = None
                            return
            with self.lock:
                self.queue_wait_until = None
                if not self.queue or (self.current and self.current.running):
                    return
                job = self.queue.popleft()
            try:
                self._start(job)
            except RuntimeError:
                with self.lock:
                    self.queue.appendleft(job)
        threading.Thread(target=run, daemon=True).start()

    def start_cao_bu(self, ids: list[str], languages: list[str], *, bo_qua_da_co: bool = False,
                     nguon: str = "cao_bu") -> dict:
        """Cào đúng các ID được đưa cho từng ngôn ngữ.

        nguon="cao_bu": cào lại (ghi đè raw cũ). nguon="danh_sach": người dùng đưa
        danh sách ID/URL; bo_qua_da_co=True thì raw đã hoàn chỉnh được bỏ qua.
        """
        ids_dir = config.OUTPUT_DIR / "ids"
        ids_dir.mkdir(parents=True, exist_ok=True)
        ids_file = ids_dir / f"{nguon}_{datetime.now():%Y%m%d_%H%M%S}.txt"
        ids_file.write_text("\n".join(ids), encoding="utf-8")
        nhan = "CÀO DANH SÁCH" if nguon == "danh_sach" else "CÀO BÙ"
        argv = self._worker_command("caobu") + ["--ids-file", str(ids_file), "--languages", *languages,
                                               "--nhan", nhan]
        if bo_qua_da_co:
            argv.append("--bo-qua-da-co")
        details = {"so_khach_san": len(ids), "languages": list(languages), "ids_file": str(ids_file),
                   "nguon": nguon, "bo_qua_da_co": bo_qua_da_co}
        label = f"Cào danh sách {len(ids)} khách sạn" if nguon == "danh_sach" else f"Cào bù {len(ids)} khách sạn"
        return self._start(Job("caobu", label, argv, len(ids) * len(languages), details))

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
        script = {"crawl": "crawl_pipeline.py", "cookie": "cookie_refresh.py",
                  "caobu": "cao_bu.py"}[kind]
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
        log_file = None
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            _prune_logs()
            job.log_path = LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{job.kind}.log"
            log_file = job.log_path.open("a", encoding="utf-8")
            log_file.write(f"# {job.label}\n# {' '.join(job.argv)}\n# bắt đầu {job.started_at}\n")
        except OSError:
            log_file = None
        for raw_line in job.process.stdout:
            line = raw_line.rstrip("\r\n")
            if log_file:
                try:
                    log_file.write(line + "\n")
                    log_file.flush()
                except OSError:
                    pass
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
        if log_file:
            try:
                log_file.write(f"# kết thúc {datetime.now().isoformat(timespec='seconds')} · mã thoát {code}\n")
                log_file.close()
            except OSError:
                pass
        with self.lock:
            job.returncode = code
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            self.history.appendleft(job.as_dict())
            self._save_history()
            has_next = bool(self.queue) and not job.stopping
            if job.stopping:
                self.queue.clear()   # bấm Dừng = huỷ luôn hàng đợi
        if has_next:
            # Bị chặn (mã 2) thì nghỉ lâu hơn trước khi sang thành phố kế.
            self._start_next_from_queue(delay=QUEUE_PAUSE_SECONDS * (5 if code == 2 else 1))

    def stop(self) -> dict:
        with self.lock:
            job = self.current
            if not job or not job.running or not job.process:
                raise RuntimeError("Không có tác vụ nào đang chạy.")
            job.stopping = True
            job.lines.append("Đang dừng theo yêu cầu…")
            job.process.terminate()
            return job.as_dict()
