# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Tour flow control: activate steps, highlight targets, watch tasks."""

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from . import helpers
from .highlight import OverlayManager
from .progress import get_bool, set_value
from .targets import TargetResolver
from .watchers import CompletionWatcher

MODE_FULL = "full"
MODE_TOPIC = "topic"


class TourEngine(QObject):
    stepChanged = pyqtSignal(object, int, int)  # step, index, count
    stepStatusChanged = pyqtSignal(str, str)  # step ID, "waiting" | "done" | "info"
    targetMissing = pyqtSignal(str)  # step ID
    targetFound = pyqtSignal(str)  # step ID
    progressChanged = pyqtSignal()
    tourFinished = pyqtSignal(str)  # mode
    tourStopped = pyqtSignal()

    def __init__(self, iface, content, progress, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.content = content
        self.progress = progress
        self._dock = None
        self.resolver = TargetResolver(iface, lambda: self._dock)
        self.watcher = CompletionWatcher(iface, self.resolver)
        self.overlay = OverlayManager(iface.mainWindow())
        self.overlay.set_dim(get_bool("dim", True))
        self.auto_advance = get_bool("auto_advance", True)

        self._sequence = []
        self._index = -1
        self._mode = None
        self._retries = 0
        self._target_index = -1
        self._missing = False
        self._watching = False

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._highlight_current)
        self._track_timer = QTimer(self)
        self._track_timer.setInterval(600)
        self._track_timer.timeout.connect(self._track)

    # ------------------------------------------------------------ state
    def set_dock(self, dock):
        self._dock = dock
        self.overlay.set_exclude_widget(dock)

    @property
    def is_running(self):
        return 0 <= self._index < len(self._sequence)

    @property
    def mode(self):
        return self._mode

    @property
    def current_step(self):
        return self._sequence[self._index] if self.is_running else None

    def set_content(self, content):
        """Select another tour (a running tour is stopped)."""
        self.stop()
        self.content = content

    def set_dim(self, enabled):
        set_value("dim", bool(enabled))
        self.overlay.set_dim(enabled)

    def set_auto_advance(self, enabled):
        self.auto_advance = bool(enabled)
        set_value("auto_advance", bool(enabled))

    # ------------------------------------------------------------ control
    def start_full(self, resume=True):
        steps = self.content.all_steps()
        start = 0
        if resume:
            open_steps = [i for i, s in enumerate(steps) if not self.progress.is_done(s.id)]
            start = open_steps[0] if open_steps else 0
        self._start(steps, start, MODE_FULL)

    def start_topic(self, topic_id, step_id=None):
        topic = self.content.topic(topic_id)
        if topic is None or not topic.steps:
            return
        start = 0
        if step_id:
            ids = [s.id for s in topic.steps]
            start = ids.index(step_id) if step_id in ids else 0
        self._start(topic.steps, start, MODE_TOPIC)

    def _start(self, steps, index, mode):
        if not steps:
            return
        self._sequence = list(steps)
        self._mode = mode
        self._activate(index)

    def next(self):
        step = self.current_step
        if step is None:
            return
        if not self._watching and not self.progress.is_done(step.id):
            self.progress.mark(step.id)  # info steps (and steps whose watcher could not start) count as done on Next
            self.progressChanged.emit()
        if self._index + 1 < len(self._sequence):
            self._activate(self._index + 1)
        else:
            self._finish()

    def prev(self):
        if self.is_running and self._index > 0:
            self._activate(self._index - 1)

    def reshow(self):
        if self.is_running:
            step = self.current_step
            self.resolver.prepare(step.targets)
            self._retries = 0
            self._retry_timer.start(120)

    def stop(self):
        was_running = self.is_running
        self._reset()
        if was_running:
            self.tourStopped.emit()

    def _finish(self):
        mode = self._mode
        self._reset()
        self.tourFinished.emit(mode)

    def _reset(self):
        self.watcher.stop()
        self._retry_timer.stop()
        self._track_timer.stop()
        self.overlay.set_target(None)
        self._sequence = []
        self._index = -1
        self._mode = None
        self._watching = False

    def run_helper(self, name):
        helpers.run(name, self.iface)

    def cleanup(self):
        self._reset()
        self.overlay.cleanup()

    # ------------------------------------------------------------ internal
    def _activate(self, index):
        self.watcher.stop()
        self._track_timer.stop()
        self.overlay.set_target(None)
        self._index = index
        step = self.current_step
        self.resolver.prepare(step.targets)
        self.stepChanged.emit(step, index, len(self._sequence))
        self._watching = False
        if step.complete_on and self.progress.is_done(step.id):
            status = "done"  # no watcher: polling watchers would fire at once and trigger auto-advance
        elif step.complete_on:
            self._watching = self.watcher.start(step.complete_on, lambda sid=step.id: self._on_completed(sid))
            status = "waiting" if self._watching else "info"
        else:
            status = "info"
        self.stepStatusChanged.emit(step.id, status)
        self._retries = 0
        self._target_index = -1
        self._missing = False
        self._retry_timer.start(150)  # newly shown panels need a moment to lay out

    def _show(self, step, target, index):
        self._target_index = index
        self.overlay.set_target(target, step.title)
        if self._missing:
            self._missing = False
            self.targetFound.emit(step.id)

    def _highlight_current(self):
        step = self.current_step
        if step is None:
            return
        if not step.targets:
            self.overlay.set_target(None)
            return
        target, index = self.resolver.resolve_indexed(step.targets)
        if target is not None:
            self._show(step, target, index)
            self._track_timer.start()
        elif self._retries < 8:
            self._retries += 1
            self._retry_timer.start(250)
        else:
            self.overlay.set_target(None)
            self._target_index = -1
            if not self._missing:
                self._missing = True
                self.targetMissing.emit(step.id)
            self._track_timer.start()  # the element may appear later

    def _track(self):
        """Track the target: look it up again if it disappears, and switch to a better
        alternative as soon as one appears (e.g. when a dialog opens)."""
        step = self.current_step
        if step is None or not step.targets:
            self._track_timer.stop()
            return
        current = self.overlay.target()
        if current is not None and current.is_valid():
            if self._target_index > 0:
                better, index = self.resolver.resolve_indexed(step.targets, limit=self._target_index)
                if better is not None:
                    self._show(step, better, index)
            return
        target, index = self.resolver.resolve_indexed(step.targets)
        if target is not None:
            self._show(step, target, index)
        else:
            self.overlay.set_target(None)

    def _on_completed(self, step_id):
        step = self.current_step
        if step is None or step.id != step_id:
            return
        self.progress.mark(step_id)
        self.stepStatusChanged.emit(step_id, "done")
        self.progressChanged.emit()
        if self.auto_advance:
            QTimer.singleShot(1800, lambda sid=step_id: self._auto_next(sid))

    def _auto_next(self, step_id):
        step = self.current_step
        if step is not None and step.id == step_id:
            self.next()
