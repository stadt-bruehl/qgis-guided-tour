# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Detects whether the user has completed the task of a step.

Supported ``complete_on`` types:

* ``action_triggered``  – {"action": "actionOpenTable"}  tool/menu item triggered
* ``map_tool``          – {"action": "actionPan"}        map tool activated
* ``extent_changed``    – map extent changed (zoom/pan)
* ``layer_added``       – a layer was added to the project
* ``current_layer_changed`` – another layer selected in the Layers panel
* ``visibility_changed``    – a layer's checkbox toggled
* ``selection_changed`` – feature selection changed
* ``editing_toggled``   – editing mode toggled; optional {"state": true/false}
* ``project_saved``     – project saved
* ``dock_shown``        – {"name": "LayerStyling"} panel shown (also panels of
                          plugins that are only created later)
* ``layout_opened``     – a print layout window was opened
* ``window_opened``     – {"window": "QgsDataSourceManagerDialog"} window/dialog is open
* ``window_closed``     – {"window": …} window was open and has been closed
* ``item_selected``     – {"window"/"in_dock": …, "texts": [...]} entry selected in list/tree;
                          without ``texts``: any other entry selected
* ``text_entered``      – {"window"/"in_dock": …, "texts": [...]} text typed into an input field;
                          without ``texts``: any text
* ``button_checked``    – {"in_dock": …, "texts": [...], "state": true} toggle button (e.g. in the
                          toolbar of a plugin panel) switched on or off
* ``context_menu``      – {"in_dock": …} context menu (right click) opened in this area
* ``layout_item_added`` – {"item_type": "QgsLayoutItemMap"} item added to the print layout
* ``layer_filtered``    – filter (query) set on a layer; {"state": false} = filter removed
* ``labels_enabled``    – labeling enabled for a layer

Besides ``window`` and ``in_dock``, the polling types accept ``in_class`` (a Qt class name) to
restrict the search to the first visible widget of that class, e.g. the locator bar.

Windows, entries, texts, buttons, menus and layer states are polled every 400 ms, because Qt has
no global signal for "window opened" or "entry selected in a foreign dialog".
"""

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QLineEdit,
    QMenu,
    QWidget,
)

from .compat import WARNING, log
from .targets import class_names, match_text


class CompletionWatcher:
    def __init__(self, iface, resolver):
        self.iface = iface
        self.resolver = resolver
        self._connections = []
        self._callback = None
        self._fired = False
        self._poll = QTimer()
        self._poll.setInterval(400)
        self._poll.timeout.connect(self._on_poll)
        self._predicate = None

    def start(self, spec, callback):
        """Start watching; returns False if the task cannot be detected."""
        self.stop()
        if not spec:
            return False
        self._callback = callback
        self._fired = False
        handler = getattr(self, "_w_" + str(spec.get("type")), None)
        if handler is None:
            log("Unknown complete_on type: {}".format(spec), WARNING)
            return False
        try:
            handler(spec)
        except Exception as e:
            log("Task detection {} not possible: {}".format(spec, e), WARNING)
            self.stop()
            return False
        return True

    def stop(self):
        self._poll.stop()
        self._predicate = None
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._connections = []
        self._callback = None

    # ------------------------------------------------------------ internal
    def _connect(self, signal, slot):
        signal.connect(slot)
        self._connections.append((signal, slot))

    def _fire(self, *args):
        if self._fired or self._callback is None:
            return
        self._fired = True
        QTimer.singleShot(0, self._callback)  # do not react inside signal handling

    def _start_polling(self, predicate):
        self._predicate = predicate
        self._poll.start()

    def _on_poll(self):
        if self._predicate is None:
            return
        try:
            done = self._predicate()
        except RuntimeError:  # widget has been deleted meanwhile
            done = False
        if done:
            self._poll.stop()
            self._fire()

    def _root(self, spec):
        root = self.resolver.find_window(spec.get("window"))
        if root is not None and spec.get("in_dock"):
            root = self.resolver.find_by_name(QDockWidget, spec["in_dock"], root)
        if root is not None and spec.get("in_class"):
            root = next((w for w in root.findChildren(QWidget)
                         if w.isVisible() and spec["in_class"] in class_names(w)), None)
        return root

    def _action(self, spec):
        act = self.resolver.action(spec.get("action", ""))
        if act is None:
            raise ValueError("Action {} not found".format(spec.get("action")))
        return act

    # ------------------------------------------------------------ types
    def _w_action_triggered(self, spec):
        self._connect(self._action(spec).triggered, self._fire)

    def _w_map_tool(self, spec):
        act = self._action(spec)

        def check(*args):
            if act.isChecked():
                self._fire()

        self._connect(self.iface.mapCanvas().mapToolSet, check)
        self._connect(act.triggered, check)

    def _w_extent_changed(self, spec):
        self._connect(self.iface.mapCanvas().extentsChanged, self._fire)

    def _w_layer_added(self, spec):
        self._connect(QgsProject.instance().layersAdded, self._fire)

    def _w_current_layer_changed(self, spec):
        self._connect(self.iface.currentLayerChanged, self._fire)

    def _w_visibility_changed(self, spec):
        self._connect(QgsProject.instance().layerTreeRoot().visibilityChanged, self._fire)

    def _w_selection_changed(self, spec):
        self._connect(self.iface.mapCanvas().selectionChanged, self._fire)

    def _w_editing_toggled(self, spec):
        wanted = spec.get("state")

        def check(checked):
            if wanted is None or bool(checked) == bool(wanted):
                self._fire()

        self._connect(self.iface.actionToggleEditing().toggled, check)

    def _w_project_saved(self, spec):
        self._connect(QgsProject.instance().projectSaved, self._fire)

    def _w_dock_shown(self, spec):
        name = spec.get("name", "")
        dock = self.resolver.find_by_name(QDockWidget, name)
        if dock is not None:
            def check(visible):
                if visible:
                    self._fire()

            self._connect(dock.visibilityChanged, check)
            return

        # panel does not exist yet (plugins often create it only on first opening)
        def appeared():
            d = self.resolver.find_by_name(QDockWidget, name)
            return d is not None and d.isVisible()

        self._start_polling(appeared)

    def _w_layout_opened(self, spec):
        self._connect(self.iface.layoutDesignerOpened, self._fire)

    def _w_window_opened(self, spec):
        self._start_polling(lambda: self.resolver.find_window(spec.get("window")) is not None)

    def _w_window_closed(self, spec):
        state = {"seen": self.resolver.find_window(spec.get("window")) is not None}

        def check():
            open_now = self.resolver.find_window(spec.get("window")) is not None
            if open_now:
                state["seen"] = True
                return False
            return state["seen"]

        self._start_polling(check)

    def _current_indexes(self, spec):
        root = self._root(spec)
        if root is None:
            return {}
        result = {}
        for view in root.findChildren(QAbstractItemView):
            if view.isVisible():
                result[id(view)] = view.currentIndex()
        return result

    def _w_item_selected(self, spec):
        texts = spec.get("texts", [])

        if not texts:  # any other entry
            start = {k: (i.row(), i.internalId()) if i.isValid() else None
                     for k, i in self._current_indexes(spec).items()}

            def changed():
                for k, idx in self._current_indexes(spec).items():
                    if idx.isValid() and start.get(k) != (idx.row(), idx.internalId()):
                        return True
                return False

            self._start_polling(changed)
            return

        def matches(idx):
            return idx.isValid() and match_text(idx.data(), texts) is not None

        # Fire only when a view newly switches to a matching entry; views already
        # matching at the start (or first seen later) just set their baseline.
        seen = {k: matches(idx) for k, idx in self._current_indexes(spec).items()}

        def check():
            fired = False
            for k, idx in self._current_indexes(spec).items():
                now = matches(idx)
                if now and k in seen and not seen[k]:
                    fired = True
                seen[k] = now
            return fired

        self._start_polling(check)

    def _w_text_entered(self, spec):
        texts = spec.get("texts", [])

        def matches(edit):
            if texts:
                return match_text(edit.text(), texts) is not None
            return bool(edit.text().strip())

        def visible_edits():
            root = self._root(spec)
            return [] if root is None else [e for e in root.findChildren(QLineEdit) if e.isVisible()]

        # Same baseline rule as item_selected: only a change into "matches" counts.
        seen = {id(e): matches(e) for e in visible_edits()}

        def check():
            fired = False
            for edit in visible_edits():
                now = matches(edit)
                if now and id(edit) in seen and not seen[id(edit)]:
                    fired = True
                seen[id(edit)] = now
            return fired

        self._start_polling(check)

    def _w_button_checked(self, spec):
        texts = spec.get("texts", [])
        wanted = bool(spec.get("state", True))

        def buttons():
            root = self._root(spec)
            if root is None:
                return []
            found = []
            for btn in root.findChildren(QAbstractButton):
                if not btn.isCheckable():
                    continue
                if match_text(btn.text(), texts) is not None or match_text(btn.toolTip(), texts) is not None:
                    found.append(btn)
            return found

        start = {id(b): b.isChecked() for b in buttons()}  # fire only on a change into the wanted state

        def check():
            for btn in buttons():
                state = btn.isChecked()
                if state == wanted and start.get(id(btn), not wanted) != wanted:
                    return True
                start[id(btn)] = state
            return False

        self._start_polling(check)

    def _w_context_menu(self, spec):
        def inside(widget, root):
            while widget is not None:
                if widget is root:
                    return True
                widget = widget.parentWidget()
            return False

        def check():
            popup = QApplication.activePopupWidget()
            if not isinstance(popup, QMenu):
                return False
            root = self._root(spec)
            return root is not None and inside(popup.parentWidget(), root)

        self._start_polling(check)

    def _w_layout_item_added(self, spec):
        wanted = spec.get("item_type", "QgsLayoutItem")

        def count():
            n = 0
            for designer in self.iface.openLayoutDesigners():
                layout = designer.layout()
                if layout is None:
                    continue
                for item in layout.items():
                    names = [c.__name__ for c in type(item).__mro__]
                    if wanted not in names:
                        try:
                            names = class_names(item)
                        except (AttributeError, RuntimeError):
                            continue
                    if wanted in names:
                        n += 1
            return n

        baseline = {"n": count()}

        def check():
            n = count()
            if n > baseline["n"]:
                return True
            baseline["n"] = min(baseline["n"], n)  # do not count deleted items
            return False

        self._start_polling(check)

    # ------------------------------------------------------------ layer states
    @staticmethod
    def _vector_layers():
        return [lyr for lyr in QgsProject.instance().mapLayers().values() if hasattr(lyr, "subsetString")]

    def _poll_layer_state(self, getter, wanted=True):
        """Fire as soon as a layer switches into the wanted state (layers added later only set a baseline)."""
        baseline = {}
        for lyr in self._vector_layers():
            try:
                baseline[lyr.id()] = bool(getter(lyr))
            except RuntimeError:
                pass

        def check():
            fired = False
            for lyr in self._vector_layers():
                state = bool(getter(lyr))
                previous = baseline.get(lyr.id())  # None: layer added after the start -> baseline only
                if previous is not None and state == wanted and previous != wanted:
                    fired = True
                baseline[lyr.id()] = state
            return fired

        self._start_polling(check)

    def _w_layer_filtered(self, spec):
        self._poll_layer_state(lambda lyr: lyr.subsetString().strip(), bool(spec.get("state", True)))

    def _w_labels_enabled(self, spec):
        self._poll_layer_state(lambda lyr: lyr.labelsEnabled(), True)
