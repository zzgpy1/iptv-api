import io
import os
import threading


class SignalLogStream(io.TextIOBase):
    def __init__(self, path: str, emit, original=None):
        super().__init__()
        self.path = path
        self.emit = emit
        self.original = original
        self.pending = ""
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
                    self.emit(line)
        return len(text)

    def flush(self):
        with self.lock:
            if self.original:
                self.original.flush()
            if self.pending.strip():
                self.emit(self.pending)
                self.pending = ""
