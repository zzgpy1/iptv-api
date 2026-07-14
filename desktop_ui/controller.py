import asyncio
import os
import socket
import sys
import traceback
from collections import deque
import threading

from PySide6.QtCore import QByteArray, QObject, QProcess, QProcessEnvironment, QThread, QUrl, Signal, Slot
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from main import UpdateSource
import utils.constants as constants
from utils.channel_operations import ChannelOperations
from utils.channel_repository import append_stream_samples
from utils.config import config
from utils.rtmp_stats import fetch_rtmp_snapshot


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


class RtmpMonitorWorker(QObject):
    snapshot = Signal(dict)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()
        self.last_persisted = 0.0

    @Slot()
    def run(self):
        while not self.stop_event.is_set():
            snapshot = fetch_rtmp_snapshot()
            self.snapshot.emit(snapshot)
            sampled_at = float(snapshot.get("sampled_at") or 0)
            if snapshot.get("available") and sampled_at - self.last_persisted >= 60:
                append_stream_samples(constants.channel_results_path, sampled_at, snapshot.get("streams", []))
                self.last_persisted = sampled_at
            self.refresh_event.wait(2)
            self.refresh_event.clear()
        self.finished.emit()

    def stop(self):
        self.stop_event.set()
        self.refresh_event.set()

    def refresh(self):
        self.refresh_event.set()


class RtmpMonitorController(QObject):
    snapshot = Signal(dict)
    control_finished = Signal(str, bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self.network = QNetworkAccessManager(self)

    def start(self):
        if self.thread:
            return
        self.thread = QThread(self)
        self.worker = RtmpMonitorWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.snapshot.connect(self.snapshot)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def stop(self):
        if self.worker:
            self.worker.stop()

    def refresh(self):
        if self.worker:
            self.worker.refresh()

    def shutdown(self):
        self.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)

    def control(self, action: str, result_key: str):
        url = QUrl(f"http://127.0.0.1:{config.app_port}/api/rtmp/streams/{result_key}/{action}")
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        reply = self.network.post(request, QByteArray(b"{}"))
        reply.finished.connect(lambda: self._control_finished(action, reply))

    def _control_finished(self, action: str, reply: QNetworkReply):
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        success = isinstance(status, int) and 200 <= status < 300
        message = bytes(reply.readAll()).decode("utf-8", errors="replace")
        self.control_finished.emit(action, success, message)
        reply.deleteLater()

    def _finished(self):
        self.worker = None
        self.thread = None


class ServiceProcessController(QObject):
    status_changed = Signal(str)
    output = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.owns_process = False

    def start(self):
        if self._port_open(config.app_port):
            self.status_changed.emit("external")
            return
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.setWorkingDirectory(os.path.abspath("."))
        self.process.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
        if getattr(sys, "frozen", False):
            self.process.setProgram(sys.executable)
            self.process.setArguments(["--service"])
        else:
            self.process.setProgram(sys.executable)
            self.process.setArguments([os.path.abspath("service/app.py")])
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(lambda: self.status_changed.emit("running"))
        self.process.errorOccurred.connect(lambda _: self.status_changed.emit("failed"))
        self.process.finished.connect(lambda *_: self.status_changed.emit("stopped"))
        self.process.start()
        self.owns_process = True

    def stop(self):
        if not self.process or not self.owns_process:
            return
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
                self.process.waitForFinished(2000)
        self.process = None
        self.owns_process = False

    def _read_output(self):
        if not self.process:
            return
        content = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not content:
            return
        self.output.emit(content)
        os.makedirs(os.path.dirname(constants.log_path), exist_ok=True)
        with open(constants.log_path, "a", encoding="utf-8") as file:
            file.write(content)

    @staticmethod
    def _port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.2):
                return True
        except OSError:
            return False
