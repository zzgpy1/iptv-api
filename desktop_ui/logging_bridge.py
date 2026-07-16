import io
import os
import threading
import time


class SignalLogStream(io.TextIOBase):
    def __init__(self, path: str, emit, original=None):
        super().__init__()
        self.path = path
        self.emit = emit
        self.original = original
        self.pending = ""
        self.display_pending = []
        self.last_emit = 0.0
        self.lock = threading.Lock()

    def writable(self):
        return True

    def write(self, value):
        text = str(value or "")
        if not text:
            return 0
        with self.lock:
            if self.original:
                self.original.write(text)
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as file:
                file.write(text)
            self.pending += text.replace("\r", "\n")
            parts = self.pending.split("\n")
            self.pending = parts.pop()
            for line in parts:
                if line.strip():
                    self.display_pending.append(line)
            self._emit_ready()
        return len(text)

    def _emit_ready(self, force=False):
        if not self.display_pending:
            return
        now = time.monotonic()
        if not force and now - self.last_emit < 0.12 and len(self.display_pending) < 20:
            return
        self.emit("\n".join(self.display_pending))
        self.display_pending = []
        self.last_emit = now

    def flush(self):
        with self.lock:
            if self.original:
                self.original.flush()
            if self.pending.strip():
                self.display_pending.append(self.pending)
                self.pending = ""
            self._emit_ready(force=True)
