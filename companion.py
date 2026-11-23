# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Companion window for modal dialogs.

When QGIS opens a modal dialog (e.g. filter, new GeoPackage layer, save as …),
Qt blocks all other windows – including the tour dock. Windows that *belong* to
the modal dialog stay usable, though. This module therefore attaches a small
tour window with step, task and Next/Back directly to the currently open dialog.
"""

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, QPoint, Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import helpers

PANEL_WIDTH = 360

STYLE = """
QFrame#tourCompanion, QFrame#tourCompanion QWidget {{ font-size: {pt:.1f}pt; }}
QFrame#tourCompanion {{ border: 3px solid #ffab00; }}
QLabel#companionHead {{ background:#ffab00; color:#281c00; font-weight:bold; padding:4px 6px; }}
QLabel#companionTitle {{ font-weight: bold; font-size: {title:.1f}pt; }}
QFrame#companionTask {{ background:#fff4d6; border:1px solid #f0c060; border-radius:4px; }}
QFrame#companionTask QLabel {{ color:#3a2a00; background:transparent; }}
"""


class CompanionPanel(QFrame):
    """The small window itself – a child of the modal dialog."""

    def __init__(self, host, companion):
        super().__init__(host, Qt.WindowType.Tool | Qt.WindowType.WindowTitleHint
                         | Qt.WindowType.CustomizeWindowHint)
        self.setObjectName("tourCompanion")
        self.setWindowTitle("Guided Tour")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.companion = companion
        self.setFixedWidth(PANEL_WIDTH)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(4)

        head = QLabel("Guided Tour – continue here while this dialog is open")
        head.setObjectName("companionHead")
        head.setWordWrap(True)
        lay.addWidget(head)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(8, 2, 8, 0)
        self.lbl_context = QLabel()
        self.lbl_context.setStyleSheet("color: palette(mid);")
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("companionTitle")
        self.lbl_title.setWordWrap(True)
        bl.addWidget(self.lbl_context)
        bl.addWidget(self.lbl_title)

        self.btn_toggle = QToolButton()
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(True)
        self.btn_toggle.setAutoRaise(True)
        self.btn_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.btn_toggle.setText("Explanation")
        bl.addWidget(self.btn_toggle)

        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setMinimumHeight(80)
        self.text.setMaximumHeight(260)
        bl.addWidget(self.text)

        self.task = QFrame()
        self.task.setObjectName("companionTask")
        self.task.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        tl = QVBoxLayout(self.task)
        self.lbl_task = QLabel()
        self.lbl_task.setWordWrap(True)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        tl.addWidget(self.lbl_task)
        tl.addWidget(self.lbl_status)
        bl.addWidget(self.task)

        self.helper_box = QVBoxLayout()
        bl.addLayout(self.helper_box)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Back")
        self.btn_show = QPushButton("Show")
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setDefault(False)
        self.btn_next.setAutoDefault(False)  # keep Enter inside the dialog (e.g. OK)
        for b in (self.btn_prev, self.btn_show):
            b.setAutoDefault(False)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_show)
        nav.addWidget(self.btn_next)
        bl.addLayout(nav)
        lay.addWidget(body)

        self.btn_toggle.toggled.connect(self._toggle_text)
        self.btn_prev.clicked.connect(companion.engine.prev)
        self.btn_next.clicked.connect(companion.engine.next)
        self.btn_show.clicked.connect(companion.engine.reshow)

    def _toggle_text(self, expanded):
        self.text.setVisible(expanded)
        self.btn_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.adjustSize()

    def apply_font_scale(self, scale):
        base = QApplication.font().pointSizeF()
        if base <= 0:
            base = 9.0
        pt = base * scale
        self.setStyleSheet(STYLE.format(pt=pt, title=pt * 1.2))
        self.text.document().setDefaultFont(self.text.font())

    def show_step(self, step, index, count, mode_full, topic_title, status):
        self.lbl_context.setText(
            ("Complete tour · " if mode_full else "") + "Step {} of {} · {}".format(index + 1, count, topic_title)
        )
        self.lbl_title.setText(step.title)
        self.text.setHtml(step.text)
        self.task.setVisible(bool(step.task))
        self.lbl_task.setText("<b>Your task:</b> " + step.task if step.task else "")
        self.set_status(status)
        self.btn_prev.setEnabled(index > 0)
        self.btn_next.setText("Done ✓" if index + 1 >= count else "Next ▶")
        while self.helper_box.count():
            w = self.helper_box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for name in step.helpers:
            if name.startswith("open_"):
                continue  # dialog openers are pointless while a dialog is open
            btn = QPushButton(helpers.label(name))
            btn.setAutoDefault(False)
            btn.clicked.connect(lambda checked=False, n=name: self.companion.engine.run_helper(n))
            self.helper_box.addWidget(btn)
        self.adjustSize()

    def set_status(self, status):
        if status == "waiting":
            self.lbl_status.setText("⏳ Waiting for you … (or click “Next”)")
        elif status == "done":
            self.lbl_status.setText("<b style='color:#1e7d32'>✓ Great, done!</b>")
        else:
            self.lbl_status.setText("")


class ModalCompanion(QObject):
    """Watches for an open modal dialog and then attaches the companion window."""

    def __init__(self, iface, engine, dock, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.engine = engine
        self.dock = dock
        self._host = None
        self._panel = None
        self._status = ""
        self._step_args = None
        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        engine.stepChanged.connect(self._on_step)
        dock.fontScaleChanged.connect(self._on_font_scale)
        engine.stepStatusChanged.connect(self._on_status)
        engine.tourStopped.connect(self._on_tour_end)
        engine.tourFinished.connect(lambda mode: self._on_tour_end())

    # ------------------------------------------------------------ state
    def _alive(self, obj):
        return obj is not None and not sip.isdeleted(obj)

    def _is_ours(self, widget):
        w = widget
        while w is not None:
            if w is self.dock:
                return True
            w = w.parentWidget()
        return False

    def _tick(self):
        if not self.engine.is_running:
            self._detach()
            return
        modal = QApplication.activeModalWidget()
        if modal is None or not modal.isVisible() or self._is_ours(modal):
            self._detach()
            return
        if modal is not self._host or not self._alive(self._panel):
            self._attach(modal)

    def _attach(self, host):
        self._detach()
        self._host = host
        self._panel = CompanionPanel(host, self)
        self._panel.apply_font_scale(self.dock.font_scale)
        if self._step_args is not None:
            self._panel.show_step(*self._step_args, self._status)
        self._panel.adjustSize()
        self._place()
        self._panel.show()
        self._panel.raise_()

    def _detach(self):
        if self._alive(self._panel):
            self._panel.hide()
            self._panel.deleteLater()
        self._panel = None
        self._host = None

    def _place(self):
        """Right of the dialog, else left of it, else in its upper right corner."""
        host, panel = self._host, self._panel
        frame = host.frameGeometry()
        screen = host.screen().availableGeometry() if hasattr(host, "screen") and host.screen() else \
            QApplication.primaryScreen().availableGeometry()
        size = panel.sizeHint()
        h = min(size.height(), screen.height() - 40)
        panel.resize(PANEL_WIDTH, h)
        y = max(screen.top() + 10, min(frame.top(), screen.bottom() - h - 10))
        if frame.right() + 12 + PANEL_WIDTH <= screen.right():
            pos = QPoint(frame.right() + 12, y)
        elif frame.left() - 12 - PANEL_WIDTH >= screen.left():
            pos = QPoint(frame.left() - 12 - PANEL_WIDTH, y)
        else:
            pos = QPoint(frame.right() - PANEL_WIDTH - 20, frame.top() + 40)
        panel.move(pos)

    # ------------------------------------------------------------ engine signals
    def _on_step(self, step, index, count):
        topic = self.engine.content.topic(step.topic_id)
        self._step_args = (step, index, count, self.engine.mode == "full", topic.title if topic else "")
        self._status = ""
        if self._alive(self._panel):
            self._panel.show_step(*self._step_args, self._status)

    def _on_tour_end(self):
        self._step_args = None
        self._status = ""
        self._detach()

    def _on_font_scale(self, scale):
        if self._alive(self._panel):
            self._panel.apply_font_scale(scale)
            self._panel.adjustSize()

    def _on_status(self, step_id, status):
        step = self.engine.current_step
        if step is None or step.id != step_id:
            return
        self._status = status
        if self._alive(self._panel):
            self._panel.set_status(status)

    def cleanup(self):
        self._timer.stop()
        self._detach()
