import asyncio
import traceback

from PySide6.QtCore import QObject, QThread, Signal, Slot

from main import UpdateSource


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
