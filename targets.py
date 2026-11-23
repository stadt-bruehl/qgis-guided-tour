# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finds user interface elements of QGIS from a target description.

Supported target types (field ``type``):

* ``canvas``     – the map view
* ``dock``       – a panel (QDockWidget) via ``name`` = objectName,
                   e.g. ``Layers``, ``Browser``, ``ProcessingToolbox``, ``LayerStyling``
* ``toolbar``    – a toolbar via ``name``, e.g. ``mMapNavToolBar``
* ``action``     – a tool via the name of the iface method, e.g. ``actionPan``;
                   the button in the toolbar is highlighted
* ``menu``       – a main menu via ``name`` (objectName, e.g. ``mProjectMenu``)
                   or ``titles`` (visible menu title, e.g. ["Projekt", "Project"])
* ``menubar``, ``statusbar``
* ``object``     – any widget via ``name`` = objectName
* ``class``      – first visible widget of a Qt class (including base classes), e.g. ``QgsLocatorWidget``;
                   optionally with ``texts``: only widgets whose text/entry matches (e.g. combo boxes)
* ``window``     – the whole window given by ``window``
* ``item``       – an entry in a list/tree with the text (or tooltip) from ``texts``
                   (e.g. "Vector" in the Data Source Manager, "XYZ Tiles" in the Browser);
                   with ``"scroll_to": true`` the list is scrolled there if the entry
                   is currently outside the visible area
* ``button``     – a button whose label (or tooltip) matches one of the ``texts``
* ``tour_dock``  – the dock widget of this plugin

Optionally, the following determine where to search:

* ``"window": "QgsDataSourceManagerDialog"`` – in a separate window/dialog
  (Qt class name including base classes, or objectName). If the window is not open,
  the target counts as not found – the next alternative is then tried.
* ``"in_dock": "ProcessingToolbox"`` – only inside this panel.

Texts are compared first exactly, then as a substring (case-insensitive,
"&" accelerators are ignored).

Optional: ``"ensure_visible": false`` prevents a hidden panel or toolbar
from being shown automatically.
"""

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QRect, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QMainWindow,
    QMenu,
    QMenuBar,
    QToolBar,
    QToolButton,
    QTreeView,
    QWidget,
)

from .compat import WARNING, log

DISPLAY_ROLE = Qt.ItemDataRole.DisplayRole
TOOLTIP_ROLE = Qt.ItemDataRole.ToolTipRole


def class_names(obj):
    """Qt class name of the object and all its base classes."""
    names = []
    mo = obj.metaObject()
    while mo is not None:
        names.append(mo.className())
        mo = mo.superClass()
    return names


def _clean(text):
    return str(text or "").replace("&", "").replace("…", "").replace("...", "").strip().lower()


def match_text(text, candidates):
    """0 = exact match, 1 = substring, None = no match."""
    t = _clean(text)
    if not t:
        return None
    best = None
    for c in candidates:
        c = _clean(c)
        if not c:
            continue
        if t == c:
            return 0
        if c in t:
            best = 1
    return best


def _in_vertical_toolbar(widget):
    try:
        if isinstance(widget, QToolBar):
            return widget.orientation() == Qt.Orientation.Vertical
        parent = widget.parentWidget()
        return isinstance(parent, QToolBar) and parent.orientation() == Qt.Orientation.Vertical
    except RuntimeError:
        return False


class ResolvedTarget:
    """A found UI element: widget + rectangle in widget coordinates."""

    def __init__(self, widget, rect_fn=None, prefer_side=None):
        self.widget = widget
        self._rect_fn = rect_fn or (lambda: widget.rect())
        if prefer_side is None:
            prefer_side = _in_vertical_toolbar(widget)
        self.prefer_side = prefer_side

    def is_valid(self):
        try:
            if self.widget is None or sip.isdeleted(self.widget):
                return False
            if not self.widget.isVisible():
                return False
            r = self._rect_fn()
            return r is not None and r.isValid() and not r.isEmpty()
        except RuntimeError:
            return False

    def host_window(self):
        try:
            return self.widget.window()
        except RuntimeError:
            return None

    def global_rect(self):
        if not self.is_valid():
            return None
        r = self._rect_fn()
        return QRect(self.widget.mapToGlobal(r.topLeft()), r.size())

    def same_as(self, other):
        if other is None:
            return False
        try:
            return self.widget is other.widget and self.global_rect() == other.global_rect()
        except RuntimeError:
            return False


class TargetResolver:
    def __init__(self, iface, tour_dock_getter):
        self.iface = iface
        self._tour_dock = tour_dock_getter

    @property
    def main(self):
        return self.iface.mainWindow()

    # ------------------------------------------------------------ public
    def resolve(self, specs):
        """Return the first visible target from the list ``specs``, or None."""
        return self.resolve_indexed(specs)[0]

    def resolve_indexed(self, specs, limit=None):
        """Like resolve(), but also returns the index of the alternative used."""
        specs = specs or []
        for i, spec in enumerate(specs[:limit] if limit is not None else specs):
            try:
                target = self._resolve_one(spec)
            except Exception as e:  # robust against differing QGIS versions
                log("Target {} could not be resolved: {}".format(spec, e), WARNING)
                target = None
            if target is not None and target.is_valid():
                return target, i
        return None, -1

    def prepare(self, specs):
        """Show the first existing target (panel/toolbar) if necessary."""
        for spec in specs or []:
            try:
                if self._prepare_one(spec):
                    return
            except Exception as e:
                log("Target {} could not be prepared: {}".format(spec, e), WARNING)

    def action(self, name):
        attr = getattr(self.iface, name, None)
        if callable(attr):
            try:
                return attr()
            except Exception:
                return None
        return None

    def find_window(self, ident):
        """Visible window by class name (including base classes) or objectName."""
        if not ident:
            return self.main
        matches = []
        for w in QApplication.topLevelWidgets():
            try:
                if not w.isVisible():
                    continue
                if ident in class_names(w) or w.objectName() == ident:
                    matches.append(w)
            except RuntimeError:
                continue
        if not matches:
            return None
        active = QApplication.activeWindow()
        for w in matches:
            if w is active:
                return w
        return matches[-1]

    def find_by_name(self, cls, name, root=None):
        if not name:
            return None
        root = root or self.main
        w = root.findChild(cls, name)
        if w is not None:
            return w
        low = name.lower()
        for child in root.findChildren(cls):
            if child.objectName().lower() == low:
                return child
        return None

    # ------------------------------------------------------------ internal
    def _root(self, spec):
        """Widget to search in – or None if the window/panel is missing."""
        root = self.find_window(spec.get("window"))
        if root is None:
            return None
        dock_name = spec.get("in_dock")
        if dock_name:
            dock = self.find_by_name(QDockWidget, dock_name, root)
            if dock is None or not dock.isVisible():
                return None
            return dock
        return root

    def _resolve_one(self, spec):
        kind = spec.get("type")
        name = spec.get("name", "")
        if kind == "canvas":
            return ResolvedTarget(self.iface.mapCanvas())
        if kind == "tour_dock":
            dock = self._tour_dock()
            return ResolvedTarget(dock) if dock is not None else None
        root = self._root(spec)
        if root is None:
            return None
        if kind == "window":
            return ResolvedTarget(root)
        if kind == "dock":
            w = self.find_by_name(QDockWidget, name, root)
            return ResolvedTarget(w) if w is not None else None
        if kind == "toolbar":
            w = self.find_by_name(QToolBar, name, root)
            return ResolvedTarget(w) if w is not None else None
        if kind == "object":
            w = self.find_by_name(QWidget, name, root)
            return ResolvedTarget(w) if w is not None else None
        if kind == "class":
            texts = spec.get("texts")
            for w in root.findChildren(QWidget):
                if w.isVisible() and name in class_names(w):
                    if texts and not self._widget_has_text(w, texts):
                        continue
                    return ResolvedTarget(w)
            return None
        if kind == "menubar":
            mb = self._menubar(root)
            return ResolvedTarget(mb) if mb is not None else None
        if kind == "statusbar":
            return ResolvedTarget(root.statusBar()) if isinstance(root, QMainWindow) else None
        if kind == "menu":
            return self._resolve_menu(spec, root)
        if kind == "action":
            act = self.action(name)
            return self._resolve_action(act, root) if act is not None else None
        if kind == "item":
            return self._resolve_item(spec, root)
        if kind == "button":
            return self._resolve_button(spec, root)
        log("Unknown target type: {}".format(kind), WARNING)
        return None

    @staticmethod
    def _menubar(root):
        if isinstance(root, QMainWindow):
            return root.menuBar()
        return root.findChild(QMenuBar)

    def _resolve_menu(self, spec, root):
        mb = self._menubar(root)
        if mb is None:
            return None
        act = None
        menu = self.find_by_name(QMenu, spec.get("name", ""), root)
        if menu is not None:
            act = menu.menuAction()
        else:
            titles = spec.get("titles", [])
            for a in mb.actions():
                if match_text(a.text(), titles) == 0:
                    act = a
                    break
        if act is None:
            return None
        return ResolvedTarget(mb, lambda: mb.actionGeometry(act))

    def _resolve_action(self, act, root=None):
        root = root or self.main
        # 1) directly in a visible toolbar
        for tb in root.findChildren(QToolBar):
            if tb.isVisible() and act in tb.actions():
                target = ResolvedTarget(tb, lambda tb=tb: tb.actionGeometry(act))
                if target.is_valid():
                    return target
        # 2) in a dropdown button (e.g. selection tools)
        for btn in root.findChildren(QToolButton):
            if not btn.isVisible():
                continue
            menu = btn.menu()
            if btn.defaultAction() == act or (menu is not None and act in menu.actions()):
                return ResolvedTarget(btn)
        # 3) button sits in the overflow (») of a toolbar that is too narrow -> show the whole toolbar
        tb = self._toolbar_containing(act, root)
        if tb is not None and tb.isVisible():
            return ResolvedTarget(tb)
        return None

    def _resolve_item(self, spec, root):
        texts = spec.get("texts", [])
        depth = int(spec.get("depth", 3))
        best = None
        for view in root.findChildren(QAbstractItemView):
            if not view.isVisible() or view.model() is None:
                continue
            if spec.get("view_class") and spec["view_class"] not in class_names(view):
                continue
            found = self._search_model(view, texts, depth)
            if found is not None and (best is None or found[0] < best[0]):
                best = found + (view,)
                if found[0] == 0:
                    break
        if best is None:
            return None
        _, index, view = best
        if spec.get("scroll_to") and not view.visualRect(index).intersects(view.viewport().rect()):
            view.scrollTo(index)
        from qgis.PyQt.QtCore import QPersistentModelIndex

        pindex = QPersistentModelIndex(index)  # survives model changes; the rect is recomputed on every call

        def rect():
            if not pindex.isValid():
                return QRect()
            idx = view.model().index(pindex.row(), pindex.column(), pindex.parent())
            r = view.visualRect(idx)
            if isinstance(view, QTreeView):
                r.setLeft(0)
                r.setRight(view.viewport().width() - 1)
            return r.intersected(view.viewport().rect())

        return ResolvedTarget(view.viewport(), rect, prefer_side=False)

    @staticmethod
    def _search_model(view, texts, depth):
        """Search visible (expanded) entries; returns (quality, index)."""
        model = view.model()
        best = None
        stack = [(None, 0)]  # FIFO queue -> breadth-first, so shallow entries win over deep ones
        is_tree = isinstance(view, QTreeView)
        while stack:
            parent, level = stack.pop(0)
            rows = model.rowCount(parent) if parent is not None else model.rowCount()
            for row in range(min(rows, 500)):
                idx = model.index(row, 0, parent) if parent is not None else model.index(row, 0)
                if is_tree and view.isRowHidden(row, idx.parent()):
                    continue
                q = match_text(idx.data(DISPLAY_ROLE), texts)
                if q is None:  # e.g. icon lists without text (Layer Styling panel)
                    q2 = match_text(idx.data(TOOLTIP_ROLE), texts)
                    q = None if q2 is None else q2 + 2
                if q is not None and (best is None or q < best[0]):
                    best = (q, idx)
                    if q == 0:
                        return best
                if is_tree and level + 1 < depth and view.isExpanded(idx):
                    stack.append((idx, level + 1))
        return best

    @staticmethod
    def _widget_has_text(widget, texts):
        """For ``class`` with ``texts``: label, current text or a list entry matches."""
        candidates = []
        for getter in ("currentText", "text", "title"):
            fn = getattr(widget, getter, None)
            if callable(fn):
                try:
                    candidates.append(fn())
                except TypeError:
                    pass
        count = getattr(widget, "count", None)
        item_text = getattr(widget, "itemText", None)
        if callable(count) and callable(item_text):
            try:
                candidates.extend(item_text(i) for i in range(min(count(), 50)))
            except TypeError:
                pass
        return any(match_text(c, texts) == 0 for c in candidates)

    def _resolve_button(self, spec, root):
        texts = spec.get("texts", [])
        best = None
        for btn in root.findChildren(QAbstractButton):
            if not btn.isVisible():
                continue
            q = match_text(btn.text(), texts)
            if q is None:
                q2 = match_text(btn.toolTip(), texts)
                q = None if q2 is None else q2 + 2  # tooltip matches rank lower
            if q is not None and (best is None or q < best[0]):
                best = (q, btn)
                if q == 0:
                    break
        return ResolvedTarget(best[1]) if best else None

    def _toolbar_containing(self, act, root=None):
        root = root or self.main
        for tb in root.findChildren(QToolBar):
            if act in tb.actions():
                return tb
        for btn in root.findChildren(QToolButton):
            menu = btn.menu()
            if btn.defaultAction() == act or (menu is not None and act in menu.actions()):
                parent = btn.parentWidget()
                while parent is not None and not isinstance(parent, QToolBar):
                    parent = parent.parentWidget()
                if parent is not None:
                    return parent
        return None

    def _prepare_one(self, spec):
        kind = spec.get("type")
        ensure = spec.get("ensure_visible", True)
        name = spec.get("name", "")
        if spec.get("window") and self.find_window(spec["window"]) is None:
            return False  # window not open -> prepare the next alternative
        if spec.get("in_dock"):
            root = self.find_window(spec.get("window"))
            dock = self.find_by_name(QDockWidget, spec["in_dock"], root)
            if dock is None:
                return False
            if ensure:
                if not dock.isVisible():
                    dock.setVisible(True)
                dock.raise_()
            return True
        root = self.find_window(spec.get("window"))
        if kind == "dock":
            dock = self.find_by_name(QDockWidget, name, root)
            if dock is None:
                return False
            if ensure:
                if not dock.isVisible():
                    dock.setVisible(True)
                dock.raise_()  # brings the tab to the front in grouped panels
            return True
        if kind == "toolbar":
            tb = self.find_by_name(QToolBar, name, root)
            if tb is None:
                return False
            if ensure and not tb.isVisible():
                tb.setVisible(True)
            return True
        if kind == "action":
            act = self.action(name)
            if act is None:
                return False
            if ensure and self._resolve_action(act, root) is None:
                tb = self._toolbar_containing(act, root)
                if tb is not None:
                    tb.setVisible(True)
            return True
        return self._resolve_one(spec) is not None
