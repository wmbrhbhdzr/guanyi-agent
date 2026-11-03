"""Bounded waiting for local tools and model requests; workers cannot be killed."""

import queue
import threading
import time


def wait_call(function, timeout_s):
    """Wait at most timeout_s; a daemon worker may finish after TimeoutError."""
    if timeout_s <= 0:
        raise TimeoutError("等待预算已耗尽")
    deadline = time.monotonic() + timeout_s
    box = queue.Queue(maxsize=1)

    def worker():
        try:
            box.put((True, function()))
        except Exception as exc:
            box.put((False, exc))

    threading.Thread(target=worker, daemon=True).start()
    try:
        ok, value = box.get(timeout=max(0, deadline - time.monotonic()))
    except queue.Empty:
        raise TimeoutError("等待超时；后台操作可能仍在运行") from None
    if time.monotonic() >= deadline:
        raise TimeoutError("结果到达时已超时")
    if not ok:
        raise value
    return value
