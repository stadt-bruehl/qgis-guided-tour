# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""The dock widget: topic overview, search and step display."""

from qgis.core import QgsSettings
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import QByteArray, QPointF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import helpers
from .engine import MODE_FULL
from .progress import get_bool, set_value
from .translate import tr

ROLE = Qt.ItemDataRole.UserRole

FONT_SCALE_DEFAULT = 1.3
FONT_SCALE_MIN = 1.0
FONT_SCALE_MAX = 2.0

# font sizes via stylesheet, because QGIS itself sets the font globally via stylesheet
STYLE = """
QWidget#tourRoot, QWidget#tourRoot QWidget {{ font-size: {pt:.1f}pt; }}
QLabel#tourTitle {{ font-size: {title:.1f}pt; font-weight: bold; }}
QLabel#tourContext {{ color: palette(mid); font-size: {small:.1f}pt; }}
QFrame#taskFrame {{ background:#fff4d6; border:1px solid #f0c060; border-radius:4px; }}
QFrame#taskFrame QLabel {{ color:#3a2a00; background:transparent; }}
"""


def _check_icon():
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(46, 160, 67))
    pen.setWidthF(2.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawPolyline([QPointF(3, 8.5), QPointF(6.5, 12), QPointF(13, 4)])
    p.end()
    return QIcon(pm)


def _empty_icon():
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    return QIcon(pm)


class TourDock(QgsDockWidget):
    closed = pyqtSignal()
    fontScaleChanged = pyqtSignal(float)

    def __init__(self, iface, engine, content, progress, tours=None):
        super().__init__(tr("Guided Tour"), iface.mainWindow())
        self.setObjectName("GuidedTourDock")
        self.setMinimumWidth(300)
        self.iface = iface
        self.engine = engine
        self.content = content
        self.progress = progress
        self.tours = list(tours or [content])
        self._step_items = {}
        self._topic_items = {}
        self._icon_done = _check_icon()
        self._icon_open = _empty_icon()

        try:
            self._font_scale = float(QgsSettings().value("guided_tour/font_scale", FONT_SCALE_DEFAULT))
        except (TypeError, ValueError):
            self._font_scale = FONT_SCALE_DEFAULT

        self._build_ui()
        self._populate_tree()
        self._apply_font_scale()
        self._connect()
        self._refresh_progress()
        self.show_welcome()

    # ------------------------------------------------------------ construction
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("tourRoot")
        self._root = root
        lay = QVBoxLayout(root)
        lay.setContentsMargins(6, 6, 6, 6)

        # --- tour selection (only visible if there are several tours)
        self.tour_row = QWidget()
        trl = QHBoxLayout(self.tour_row)
        trl.setContentsMargins(0, 0, 0, 0)
        trl.addWidget(QLabel(tr("Tour:")))
        self.tour_combo = QComboBox()
        self.tour_combo.setToolTip(tr("Which tour would you like to see?"))
        for tour in self.tours:
            self.tour_combo.addItem(tour.title, tour.id)
        self.tour_combo.setCurrentIndex(max(0, self.tour_combo.findData(self.content.id)))
        trl.addWidget(self.tour_combo, 1)
        self.tour_row.setVisible(len(self.tours) > 1)
        lay.addWidget(self.tour_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        lay.addWidget(self.progress_bar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        lay.addWidget(splitter, 1)

        # --- upper part: topics
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search for a topic or keyword …"))
        self.search.setClearButtonEnabled(True)
        tl.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setToolTip(tr("Double-click a topic or step to open the explanation."))
        self.tree.setMinimumHeight(60)
        tl.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.btn_full = QPushButton(tr("Start complete tour"))
        self.btn_topic = QPushButton(tr("Selected topic"))
        self.btn_topic.setEnabled(False)
        row.addWidget(self.btn_full)
        row.addWidget(self.btn_topic)
        tl.addLayout(row)
        splitter.addWidget(top)

        # --- lower part: current step
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        self.lbl_context = QLabel()
        self.lbl_context.setObjectName("tourContext")
        self.lbl_context.setWordWrap(True)
        bl.addWidget(self.lbl_context)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("tourTitle")
        self.lbl_title.setWordWrap(True)
        bl.addWidget(self.lbl_title)

        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setMinimumHeight(60)
        bl.addWidget(self.text, 1)

        self.task_frame = QFrame()
        self.task_frame.setObjectName("taskFrame")
        self.task_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        tfl = QVBoxLayout(self.task_frame)
        self.lbl_task = QLabel()
        self.lbl_task.setWordWrap(True)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        tfl.addWidget(self.lbl_task)
        tfl.addWidget(self.lbl_status)
        bl.addWidget(self.task_frame)

        self.lbl_missing = QLabel(
            tr("<i>This UI element is not visible right now – maybe the window is "
               "not open yet, it is hidden, or your QGIS version looks slightly different. "
               "The explanation still applies.</i>")
        )
        self.lbl_missing.setWordWrap(True)
        self.lbl_missing.setVisible(False)
        bl.addWidget(self.lbl_missing)

        self.helper_box = QWidget()
        self.helper_layout = QVBoxLayout(self.helper_box)
        self.helper_layout.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.helper_box)

        self.nav = QWidget()
        nl = QHBoxLayout(self.nav)
        nl.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QPushButton(tr("◀ Back"))
        self.btn_show = QPushButton(tr("Show"))
        self.btn_show.setToolTip(tr("Highlight the UI element again"))
        self.btn_next = QPushButton(tr("Next ▶"))
        self.btn_next.setDefault(True)
        self.btn_stop = QToolButton()
        self.btn_stop.setText("✕")
        self.btn_stop.setToolTip(tr("End tour"))
        for b in (self.btn_prev, self.btn_show, self.btn_next):
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            nl.addWidget(b)
        nl.addWidget(self.btn_stop)
        # the lower pane scrolls on small screens; the navigation stays pinned below the splitter
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(bottom)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)

        lay.addWidget(self.nav)

        # --- options
        opts = QHBoxLayout()
        self.chk_dim = QCheckBox(tr("Dim surroundings"))
        self.chk_dim.setChecked(self.engine.overlay.dim)
        self.chk_auto = QCheckBox(tr("Advance automatically"))
        self.chk_auto.setToolTip(tr("Switch to the next step automatically after a task is completed"))
        self.chk_auto.setChecked(self.engine.auto_advance)
        self.btn_reset = QToolButton()
        self.btn_reset.setText(tr("Reset progress"))
        self.btn_reset.setAutoRaise(True)
        self.btn_smaller = QToolButton()
        self.btn_smaller.setText("A−")
        self.btn_smaller.setToolTip(tr("Smaller font"))
        self.btn_bigger = QToolButton()
        self.btn_bigger.setText("A+")
        self.btn_bigger.setToolTip(tr("Larger font"))
        opts.addWidget(self.chk_dim)
        opts.addWidget(self.chk_auto)
        opts.addStretch(1)
        opts.addWidget(self.btn_smaller)
        opts.addWidget(self.btn_bigger)
        lay.addLayout(opts)
        reset_row = QHBoxLayout()
        self.btn_window = QToolButton()
        self.btn_window.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.chk_on_top = QCheckBox(tr("Always on top"))
        self.chk_on_top.setToolTip(tr("The tour window stays above QGIS, even when you click into the main window"))
        self.chk_on_top.setChecked(get_bool("window_on_top", False))
        reset_row.addWidget(self.btn_window)
        reset_row.addWidget(self.chk_on_top)
        reset_row.addStretch(1)
        reset_row.addWidget(self.btn_reset)
        lay.addLayout(reset_row)
        self._update_window_button()

        self.setWidget(root)

    def _populate_tree(self):
        self.tree.clear()
        self._step_items = {}
        self._topic_items = {}
        for topic in self.content.topics:
            ti = QTreeWidgetItem([topic.title])
            ti.setData(0, ROLE, ("topic", topic.id))
            ti.setToolTip(0, topic.description)
            self._topic_items[topic.id] = ti
            for step in topic.steps:
                si = QTreeWidgetItem([step.title])
                si.setData(0, ROLE, ("step", step.id))
                ti.addChild(si)
                self._step_items[step.id] = si
            self.tree.addTopLevelItem(ti)

    def _connect(self):
        self.tour_combo.currentIndexChanged.connect(self._on_tour_chosen)
        self.search.textChanged.connect(self._filter)
        self.tree.itemActivated.connect(self._on_item_activated)
        self.tree.currentItemChanged.connect(lambda cur, prev: self.btn_topic.setEnabled(cur is not None))
        self.btn_full.clicked.connect(lambda: self.engine.start_full(resume=True))
        self.btn_topic.clicked.connect(self._start_selected)
        self.btn_prev.clicked.connect(self.engine.prev)
        self.btn_next.clicked.connect(self.engine.next)
        self.btn_show.clicked.connect(self.engine.reshow)
        self.btn_stop.clicked.connect(self.engine.stop)
        self.chk_dim.toggled.connect(self.engine.set_dim)
        self.chk_auto.toggled.connect(self.engine.set_auto_advance)
        self.btn_reset.clicked.connect(self._reset_progress)
        self.btn_smaller.clicked.connect(lambda: self._change_font_scale(-0.1))
        self.btn_bigger.clicked.connect(lambda: self._change_font_scale(+0.1))
        self.btn_window.clicked.connect(self.toggle_window_mode)
        self.chk_on_top.toggled.connect(self._on_top_toggled)
        self.topLevelChanged.connect(self._on_top_level_changed)
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(500)
        self._geometry_timer.timeout.connect(self._save_geometry)

        self.engine.stepChanged.connect(self._on_step_changed)
        self.engine.stepStatusChanged.connect(self._on_status)
        self.engine.targetMissing.connect(self._on_target_missing)
        self.engine.targetFound.connect(lambda sid: self.lbl_missing.setVisible(False))
        self.engine.progressChanged.connect(self._refresh_progress)
        self.engine.tourFinished.connect(self._on_finished)
        self.engine.tourStopped.connect(self.show_welcome)

    # ------------------------------------------------------------ display
    def _set_step_mode(self, active):
        self.nav.setVisible(active)
        self.lbl_context.setVisible(active)
        if not active:
            self.task_frame.setVisible(False)
            self.lbl_missing.setVisible(False)
            self._set_helpers([])

    def show_welcome(self):
        self._set_step_mode(False)
        self.lbl_title.setText(self.content.welcome_title)
        self.text.setHtml(self.content.welcome)
        self._update_start_button()

    def _on_finished(self, mode):
        self._set_step_mode(False)
        self._refresh_progress()
        if mode == MODE_FULL:
            self.lbl_title.setText(tr("Done! 🎉"))
            self.text.setHtml(self.content.finished)
        else:
            self.lbl_title.setText(tr("Topic completed"))
            self.text.setHtml(
                tr("<p>You have completed this topic. Pick another topic above "
                   "or continue the complete tour.</p>")
            )
        self._update_start_button()

    def _on_step_changed(self, step, index, count):
        self._set_step_mode(True)
        topic = self.content.topic(step.topic_id)
        topic_title = topic.title if topic else ""
        if self.engine.mode == MODE_FULL:
            self.lbl_context.setText(tr("Complete tour · Step {} of {} · {}").format(index + 1, count, topic_title))
        else:
            self.lbl_context.setText(tr("{} · Step {} of {}").format(topic_title, index + 1, count))
        self.lbl_title.setText(step.title)
        self.text.setHtml(step.text)
        self.lbl_missing.setVisible(False)

        self.task_frame.setVisible(bool(step.task))
        self.lbl_task.setText(tr("<b>Your task:</b> {}").format(step.task) if step.task else "")
        self._set_helpers(step.helpers)

        self.btn_prev.setEnabled(index > 0)
        self.btn_next.setText(tr("Done ✓") if index + 1 >= count else tr("Next ▶"))

        item = self._step_items.get(step.id)
        if item is not None:
            if item.parent() is not None:
                item.parent().setExpanded(True)
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    def _on_status(self, step_id, status):
        if status == "waiting":
            self.lbl_status.setText(tr("⏳ Waiting for you … (you can also just click “Next”)"))
        elif status == "done":
            self.lbl_status.setText(tr("<b style='color:#1e7d32'>✓ Great, done!</b>"))
        else:
            self.lbl_status.setText("")
        self._refresh_progress()

    def _on_target_missing(self, step_id):
        step = self.engine.current_step
        if step is not None and step.id == step_id:
            self.lbl_missing.setVisible(True)

    def _set_helpers(self, names):
        while self.helper_layout.count():
            w = self.helper_layout.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for name in names:
            btn = QPushButton(helpers.label(name))
            btn.clicked.connect(lambda checked=False, n=name: self.engine.run_helper(n))
            self.helper_layout.addWidget(btn)
        self.helper_box.setVisible(bool(names))

    def _refresh_progress(self):
        all_ids = [s.id for s in self.content.all_steps()]
        done = self.progress.count(all_ids)
        self.progress_bar.setRange(0, max(1, len(all_ids)))
        self.progress_bar.setValue(done)
        self.progress_bar.setFormat(tr("{} of {} steps completed").format(done, len(all_ids)))
        for topic in self.content.topics:
            ids = [s.id for s in topic.steps]
            n = self.progress.count(ids)
            ti = self._topic_items[topic.id]
            ti.setText(0, "{}  ({}/{})".format(topic.title, n, len(ids)))
            ti.setIcon(0, self._icon_done if n == len(ids) else self._icon_open)
            for s in topic.steps:
                done_s = self.progress.is_done(s.id)
                self._step_items[s.id].setIcon(0, self._icon_done if done_s else self._icon_open)
        self._update_start_button()

    def _update_start_button(self):
        all_ids = [s.id for s in self.content.all_steps()]
        done = self.progress.count(all_ids)
        if done == 0:
            self.btn_full.setText(tr("Start complete tour"))
        elif done < len(all_ids):
            self.btn_full.setText(tr("Continue tour"))
        else:
            self.btn_full.setText(tr("Repeat tour"))

    # ------------------------------------------------------------ tour selection
    def select_tour(self, tour_id):
        """Select a tour by ID; False if it does not exist."""
        index = self.tour_combo.findData(tour_id)
        if index < 0:
            return False
        if index != self.tour_combo.currentIndex():
            self.tour_combo.setCurrentIndex(index)  # -> _on_tour_chosen
        return True

    def _on_tour_chosen(self, index):
        tour_id = self.tour_combo.itemData(index)
        tour = next((t for t in self.tours if t.id == tour_id), None)
        if tour is None or tour is self.content:
            return
        set_value("current_tour", tour.id)
        self.engine.set_content(tour)
        self.content = tour
        self._populate_tree()
        self._apply_font_scale()
        self._refresh_progress()
        self._filter(self.search.text())
        self.show_welcome()

    # ------------------------------------------------------------ font size
    @property
    def font_scale(self):
        return self._font_scale

    def _change_font_scale(self, delta):
        scale = round(min(FONT_SCALE_MAX, max(FONT_SCALE_MIN, self._font_scale + delta)), 2)
        if scale != self._font_scale:
            self._font_scale = scale
            set_value("font_scale", scale)
            self._apply_font_scale()

    def _apply_font_scale(self):
        base = QApplication.font().pointSizeF()
        if base <= 0:
            base = 9.0
        pt = base * self._font_scale
        self._root.setStyleSheet(STYLE.format(pt=pt, title=pt * 1.3, small=pt * 0.9))
        self.btn_smaller.setEnabled(self._font_scale > FONT_SCALE_MIN + 0.001)
        self.btn_bigger.setEnabled(self._font_scale < FONT_SCALE_MAX - 0.001)
        # topics in bold – item fonts do not inherit the stylesheet, so set explicitly
        self.tree.ensurePolished()
        bold = QFont(self.tree.font())
        bold.setBold(True)
        for ti in self._topic_items.values():
            ti.setFont(0, bold)
        self.text.document().setDefaultFont(self.text.font())
        self.engine.overlay.set_font_scale(self._font_scale)
        self.fontScaleChanged.emit(self._font_scale)

    # ------------------------------------------------------------ actions
    def _on_item_activated(self, item, column=0):
        data = item.data(0, ROLE)
        if not data:
            return
        kind, ident = data
        if kind == "topic":
            self.engine.start_topic(ident)
        else:
            step = self.content.step(ident)
            if step is not None:
                self.engine.start_topic(step.topic_id, ident)

    def _start_selected(self):
        item = self.tree.currentItem()
        if item is not None:
            self._on_item_activated(item)

    def _filter(self, text):
        words = [w for w in text.lower().split() if w]
        current = self.engine.current_step
        current_topic = current.topic_id if current is not None else None
        for topic in self.content.topics:
            ti = self._topic_items[topic.id]
            topic_hit = all(w in topic.search_text() for w in words)
            any_child = False
            for step in topic.steps:
                hit = topic_hit or all(w in step.search_text() for w in words)
                self._step_items[step.id].setHidden(not hit)
                any_child = any_child or hit
            ti.setHidden(not any_child)
            ti.setExpanded((bool(words) and any_child) or topic.id == current_topic)

    def _reset_progress(self):
        answer = QMessageBox.question(
            self,
            tr("Reset progress"),
            tr("Mark all steps of the tour “{}” as “open” again?").format(self.content.title),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.progress.reset([s.id for s in self.content.all_steps()])
            self._refresh_progress()

    # ------------------------------------------------------------ separate window
    def toggle_window_mode(self):
        self.setFloating(not self.isFloating())

    def restore_window_mode(self):
        """On startup: restore the last used mode (docked / separate window)."""
        if get_bool("window_mode", False) and not self.isFloating():
            self.setFloating(True)

    def _on_top_level_changed(self, floating):
        set_value("window_mode", bool(floating))
        if floating:
            # switch to a “real” window only after Qt's own transition
            QTimer.singleShot(0, self._make_real_window)
        self._update_window_button()

    def _window_flags(self):
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        if self.chk_on_top.isChecked():
            flags |= Qt.WindowType.WindowStaysOnTopHint
        return flags

    def _make_real_window(self):
        """Floating panel -> normal window with title bar (taskbar, maximize,
        freely movable to any screen)."""
        if not self.isFloating():
            return
        was_visible = self.isVisible()  # setWindowFlags() hides the window
        self.setWindowFlags(self._window_flags())
        self.setWindowTitle(tr("Guided Tour – QGIS"))
        icon = self.iface.mainWindow().windowIcon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self._restore_geometry()
        if was_visible:
            self.show()
            self.raise_()
            self.activateWindow()
        self._update_window_button()

    def _on_top_toggled(self, checked):
        set_value("window_on_top", bool(checked))
        if self.isFloating():
            self._make_real_window()

    def _update_window_button(self):
        floating = self.isFloating()
        self.btn_window.setText(tr("⇤ Dock") if floating else tr("⧉ Separate window"))
        self.btn_window.setToolTip(
            tr("Dock back into the QGIS window")
            if floating
            else tr("Open as a separate window – e.g. to drag it to a second screen")
        )
        self.chk_on_top.setVisible(floating)

    def _restore_geometry(self):
        raw = QgsSettings().value("guided_tour/window_geometry", "")
        if not raw:
            self.resize(480, 800)
            return
        try:
            data = QByteArray.fromBase64(QByteArray(str(raw).encode("ascii")))
            if not self.restoreGeometry(data):
                self.resize(480, 800)
        except Exception:
            self.resize(480, 800)
        # is the window on no existing screen (e.g. second monitor unplugged)?
        center = self.frameGeometry().center()
        if not any(screen.availableGeometry().contains(center) for screen in QApplication.screens()):
            self.move(self.iface.mainWindow().geometry().center() - self.rect().center())

    def _save_geometry(self):
        if self.isFloating() and self.isVisible():
            data = bytes(self.saveGeometry().toBase64()).decode("ascii")
            set_value("window_geometry", data)

    def moveEvent(self, event):  # noqa: N802
        super().moveEvent(event)
        if self.isFloating():
            self._geometry_timer.start()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self.isFloating():
            self._geometry_timer.start()

    def closeEvent(self, event):  # noqa: N802
        self._save_geometry()
        self.engine.stop()
        self.closed.emit()
        super().closeEvent(event)
