# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Plugin entry point: menu entry, toolbar icon, dock widget."""

import os

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QApplication

from . import translate
from .compat import QAction
from .translate import tr
from .companion import ModalCompanion
from .content import load_tours
from .engine import TourEngine
from .progress import Progress, get_bool, get_value, set_value
from .tour_dock import TourDock

MENU = "&Guided Tour"


class GuidedTourPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dock = None
        self.engine = None
        self.companion = None
        self._help_menu = None
        self._help_separator = None
        self.progress = None
        self.tours = []
        self.content = None

    def initGui(self):  # noqa: N802
        # load the content first: if it fails, nothing has been registered yet
        translate.install(self.plugin_dir)
        self.progress = Progress()
        self.tours = load_tours(self.plugin_dir)
        last = get_value("current_tour", "")
        self.content = next((t for t in self.tours if t.id == last), self.tours[0])

        icon = QIcon(os.path.join(self.plugin_dir, "icons", "icon.svg"))
        self.action = QAction(icon, tr("Guided Tour through QGIS"), self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.setToolTip(tr("Guided Tour: get to know QGIS step by step"))
        self.action.toggled.connect(self._toggle_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(MENU, self.action)
        try:  # also add to the Help menu, where beginners look first
            self._help_menu = self.iface.helpMenu()
            self._help_separator = self._help_menu.addSeparator()
            self._help_menu.addAction(self.action)
        except Exception:
            self._help_menu = None

        self.engine = TourEngine(self.iface, self.content, self.progress)
        self.dock = TourDock(self.iface, self.engine, self.content, self.progress, self.tours)
        self.engine.set_dock(self.dock)
        self.companion = ModalCompanion(self.iface, self.engine, self.dock)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.hide()
        self.dock.restore_window_mode()
        if self.dock.isFloating():
            self.dock.hide()
        self.dock.closed.connect(lambda: self._sync_action(False))
        self.dock.visibilityChanged.connect(lambda visible: visible and self._sync_action(True))

        if not get_bool("first_run_done", False):
            # offer the tour on the very first start, once QGIS has finished loading
            QTimer.singleShot(1500, self._first_run)

    def _first_run(self):
        if self.action is None:  # plugin was unloaded before the timer fired
            return
        set_value("first_run_done", True)
        self.action.setChecked(True)

    def start_tour(self, tour_id, topic_id=None):
        """Open the dock with the requested tour, e.g. from another plugin:

            from qgis.utils import plugins
            plugins["guided_tour"].start_tour("my_plugin")

        The tour starts at the first open step (or at topic ``topic_id``).
        Returns False if the tour does not exist.
        """
        if self.dock is None or not self.dock.select_tour(tour_id):
            return False
        self.action.setChecked(True)
        self._toggle_dock(True)
        if topic_id:
            self.engine.start_topic(topic_id)
        else:
            self.engine.start_full(resume=True)
        return True

    def _sync_action(self, checked):
        if self.action is not None and self.action.isChecked() != checked:
            self.action.blockSignals(True)
            self.action.setChecked(checked)
            self.action.blockSignals(False)

    def _ensure_on_screen(self):
        """Re-dock a floating window on the right if it lies on no existing screen
        (e.g. because the second monitor is missing)."""
        if not self.dock.isFloating():
            return
        center = self.dock.frameGeometry().center()
        if not any(s.availableGeometry().contains(center) for s in QApplication.screens()):
            self.dock.setFloating(False)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _toggle_dock(self, checked):
        if checked:
            self._ensure_on_screen()
            self.dock.show()
            self.dock.raise_()
            if self.dock.isFloating():
                self.dock.activateWindow()
        else:
            self.dock.close()

    def unload(self):
        translate.remove()
        if getattr(self, "companion", None) is not None:
            self.companion.cleanup()
            self.companion = None
        if self.engine is not None:
            self.engine.cleanup()
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
        if self.action is not None:
            self.iface.removePluginMenu(MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            if self._help_menu is not None:
                self._help_menu.removeAction(self.action)
                if self._help_separator is not None:
                    self._help_menu.removeAction(self._help_separator)
            self.action.deleteLater()
        self.engine = self.dock = self.action = None
