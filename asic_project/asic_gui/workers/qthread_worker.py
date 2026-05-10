# workers/qthread_worker.py
# Generic QThread worker.
# All UART/instrument calls run here so the GUI event loop never blocks.
# One global serialised queue — only one hardware call at a time,
# which is correct because there is one serial port shared by all peripherals.

import traceback
from PyQt5.QtCore import QThread, pyqtSignal, QObject


class Worker(QObject):
    """
    Run a callable in a QThread.

    Usage:
        worker = Worker(fn, *args, **kwargs)
        thread = QThread()
        worker.moveToThread(thread)
        worker.finished.connect(on_result)   # dict result
        worker.error.connect(on_error)        # str message
        thread.started.connect(worker.run)
        thread.start()

    The thread is cleaned up automatically via the finished signal.
    """
    finished = pyqtSignal(dict)   # emits result dict from the callable
    error    = pyqtSignal(str)    # emits traceback string on exception
    progress = pyqtSignal(int)    # 0–100, optional use by long operations

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn   = fn
        self._args = args
        self._kw   = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kw)
            if not isinstance(result, dict):
                result = {"result": result}
            self.finished.emit(result)
        except Exception:
            self.error.emit(traceback.format_exc())


def run_in_thread(fn, *args, on_result=None, on_error=None,
                  parent=None, **kwargs):
    """
    Convenience helper: create Worker + QThread, wire signals, start.
    Returns (thread, worker) so the caller can keep references alive.

    on_result: callable(dict)
    on_error : callable(str)
    """
    thread = QThread(parent=parent)
    worker = Worker(fn, *args, **kwargs)
    # Keep a Python reference alive for callers that only store the thread.
    # Without this, PyQt can lose the worker before its signals return.
    thread._worker_ref = worker
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.error.connect(worker.deleteLater)
    thread.finished.connect(lambda: setattr(thread, "_worker_ref", None))
    thread.finished.connect(thread.deleteLater)

    if on_result:
        worker.finished.connect(on_result)
    if on_error:
        worker.error.connect(on_error)

    thread.start()
    return thread, worker
