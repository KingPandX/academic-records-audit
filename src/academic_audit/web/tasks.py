from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Any, Callable


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_task(
        self, desc: str, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> str:
        task_id = uuid.uuid4().hex[:8]
        log_queue: queue.Queue[str | None] = queue.Queue()

        with self._lock:
            self._tasks[task_id] = {
                "desc": desc,
                "queue": log_queue,
                "status": "running",
                "started": time.time(),
            }

        def _worker() -> None:
            try:
                fn(*args, **kwargs)
                with self._lock:
                    t = self._tasks[task_id]
                    if t["status"] == "running":
                        t["status"] = "completed"
            except BaseException as e:
                log_queue.put(f"ERROR: {e}")
                with self._lock:
                    t = self._tasks.get(task_id)
                    if t:
                        t["status"] = "failed"
            finally:
                log_queue.put(None)

        t = threading.Thread(target=_worker, daemon=True, name=f"task-{task_id}")
        t.start()
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._tasks.get(task_id)

    def event_stream(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            yield f"event: error\ndata: Tarea no encontrada\n\n"
            return

        q: queue.Queue[str | None] = task["queue"]
        try:
            while True:
                try:
                    msg = q.get(timeout=1)
                    if msg is None:
                        break
                    for line in msg.split("\n"):
                        if line:
                            yield f"data: {line}\n"
                    yield "\n"
                except queue.Empty:
                    yield f": keepalive\n\n"

            t = self.get_task(task_id)
            status = t["status"] if t else "unknown"
            yield f"event: done\ndata: {status}\n\n"
        finally:
            threading.Timer(30, self._cleanup, [task_id]).start()

    def _cleanup(self, task_id: str) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)
