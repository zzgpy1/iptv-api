import asyncio
import traceback
from collections import deque

from PySide6.QtCore import QObject, QThread, Signal, Slot

from main import UpdateSource
from utils.channel_operations import ChannelOperations


class UpdateWorker(QObject):
    progress = Signal(str, int, bool, object, object)
    finished = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.loop = None
        self.task = None
        self.source = UpdateSource()

    @Slot()
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.task = self.loop.create_task(self.source.run_once(self._progress))
        try:
            self.loop.run_until_complete(self.task)
        except asyncio.CancelledError:
            pass
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            self.task = None
            self.loop.close()
            self.loop = None
            self.finished.emit()

    def cancel(self):
        if self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)

    def _progress(self, title, progress, finished=False, url=None, now=None):
        self.progress.emit(str(title), int(progress), bool(finished), url, now)


class UpdateController(QObject):
    progress = Signal(str, int, bool, object, object)
    started = Signal()
    finished = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None

    def start(self):
        if self.thread and self.thread.isRunning():
            return
        self.thread = QThread(self)
        self.worker = UpdateWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        self.started.emit()

    def cancel(self):
        if self.worker:
            self.worker.cancel()

    def _finished(self):
        self.finished.emit()
        self.worker = None
        self.thread = None


class OperationWorker(QObject):
    progress = Signal(str, int)
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, operation: str, payload: dict):
        super().__init__()
        self.operation = operation
        self.payload = payload
        self.loop = None
        self.task = None

    @Slot()
    def run(self):
        service = ChannelOperations()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        method = getattr(service, self.operation)
        self.task = self.loop.create_task(method(progress=self._progress, **self.payload))
        try:
            result = self.loop.run_until_complete(self.task)
            self.succeeded.emit(self.operation, result)
        except asyncio.CancelledError:
            pass
        except Exception:
            self.failed.emit(self.operation, traceback.format_exc())
        finally:
            self.task = None
            self.loop.close()
            self.loop = None
            self.finished.emit()

    def cancel(self):
        if self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)

    def _progress(self, current: int, total: int, name: str):
        percent = int(current / total * 100) if total else 0
        self.progress.emit(name, percent)


class ChannelOperationController(QObject):
    task_started = Signal(str)
    task_progress = Signal(str, int)
    task_succeeded = Signal(str, object)
    task_failed = Signal(str, str)
    queue_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue = deque()
        self.thread = None
        self.worker = None
        self.suspended = False

    def enqueue(self, operation: str, payload: dict):
        self.queue.append((operation, payload))
        self.queue_changed.emit(len(self.queue))
        if not self.thread and not self.suspended:
            self._start_next()

    @property
    def is_busy(self):
        return bool(self.thread or self.queue)

    def suspend(self):
        self.suspended = True

    def resume(self):
        self.suspended = False
        if not self.thread:
            self._start_next()

    def cancel_current(self):
        if self.worker:
            self.worker.cancel()

    def _start_next(self):
        if not self.queue or self.suspended:
            self.queue_changed.emit(len(self.queue))
            return
        operation, payload = self.queue.popleft()
        self.queue_changed.emit(len(self.queue))
        self.thread = QThread(self)
        self.worker = OperationWorker(operation, payload)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.task_progress)
        self.worker.succeeded.connect(self.task_succeeded)
        self.worker.failed.connect(self.task_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        self.task_started.emit(operation)

    def _finished(self):
        self.worker = None
        self.thread = None
        self._start_next()
