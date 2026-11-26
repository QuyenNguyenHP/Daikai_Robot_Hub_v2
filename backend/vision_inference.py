"""Run at most one AI inference without queuing camera frames."""
from concurrent.futures import ThreadPoolExecutor


class LiveInference:
    def __init__(self):
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vision-ai")
        self.pending = None

    def poll(self):
        if self.pending is None or not self.pending.done():
            return None
        completed, self.pending = self.pending, None
        return completed.result()

    def submit(self, function, *args):
        if self.pending is not None:
            return False
        self.pending = self.worker.submit(function, *args)
        return True

    def close(self):
        self.worker.shutdown(wait=True)
