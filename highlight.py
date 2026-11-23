# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Spotlight overlay: dims a window and highlights a UI element.

An overlay is a transparent child widget of the respective window that lets all
mouse events through – the user can keep working normally.
Because dialogs and the layout window are separate windows, the
``OverlayManager`` keeps one overlay per window.
"""

import math

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QRect, QRectF, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QRegion
from qgis.PyQt.QtWidgets import QWidget

ACCENT = QColor(255, 171, 0)
DIM = QColor(0, 0, 0, 110)


class SpotlightOverlay(QWidget):
    PAD = 6
    RADIUS = 8

    def __init__(self, host):
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._target = None
        self._label = ""
        self._dim = True
        self._exclude = None
        self._font_scale = 1.0
        self._phase = 0.0
        self._rect = None
        self._excl_rect = None
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self.hide()

    # ------------------------------------------------------------ API
    def set_target(self, target, label=""):
        self._target = target
        self._label = label
        self._rect = None
        if target is None:
            self._timer.stop()
            self.hide()
            return
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self._timer.start()
        self._tick(force=True)

    def target(self):
        return self._target

    def set_dim(self, enabled):
        self._dim = bool(enabled)
        self.update()

    def set_exclude_widget(self, widget):
        """Widget that is never dimmed (the tour dock widget)."""
        self._exclude = widget

    def set_font_scale(self, scale):
        self._font_scale = float(scale)
        self.update()

    # ------------------------------------------------------------ internal
    def _map_global(self, rect):
        return QRect(self.mapFromGlobal(rect.topLeft()), rect.size())

    def _current_rect(self):
        t = self._target
        if t is None or not t.is_valid():
            return None
        r = self._map_global(t.global_rect()).intersected(self.rect())
        return r if not r.isEmpty() else None

    def _exclude_rect(self):
        w = self._exclude
        try:
            if w is None or sip.isdeleted(w) or not w.isVisible():
                return None
            if w.window() is not self.parentWidget():
                return None  # lies in another window (e.g. floating)
            return self._map_global(QRect(w.mapToGlobal(w.rect().topLeft()), w.size()))
        except RuntimeError:
            return None

    def _hole(self, rect):
        return rect.adjusted(-self.PAD, -self.PAD, self.PAD, self.PAD)

    def _tick(self, force=False):
        parent = self.parentWidget()
        if parent is None:
            return
        if self.geometry() != parent.rect():
            self.setGeometry(parent.rect())
            force = True
        self.raise_()
        self._phase += 0.18
        rect = self._current_rect()
        excl = self._exclude_rect()
        if force or rect != self._rect or excl != self._excl_rect:
            self._rect = rect
            self._excl_rect = excl
            self.update()
            return
        if rect is not None:
            # only repaint the pulsing frame
            hole = self._hole(rect)
            outer = QRegion(hole.adjusted(-4, -4, 4, 4))
            inner = QRegion(hole.adjusted(4, 4, -4, -4))
            self.update(outer.subtracted(inner))

    def paintEvent(self, event):  # noqa: N802
        rect = self._rect
        if rect is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hole = QRectF(self._hole(rect))

        if self._dim:
            area = QPainterPath()
            area.addRect(QRectF(self.rect()))
            cut = QPainterPath()
            cut.addRoundedRect(hole, self.RADIUS, self.RADIUS)
            area = area.subtracted(cut)
            if self._excl_rect is not None:
                excl = QPainterPath()
                excl.addRect(QRectF(self._excl_rect))
                area = area.subtracted(excl)
            p.fillPath(area, DIM)

        color = QColor(ACCENT)
        color.setAlpha(int(165 + 90 * math.sin(self._phase)))
        pen = QPen(color)
        pen.setWidth(4)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(hole, self.RADIUS, self.RADIUS)

        if self._label:
            self._draw_callout(p, hole)
        p.end()

    def _draw_callout(self, p, hole):
        font = QFont(self.font())
        font.setBold(True)
        size = font.pointSizeF() if font.pointSizeF() > 0 else 9.0
        font.setPointSizeF(size * self._font_scale)
        fm = QFontMetrics(font)
        text = self._label
        w = fm.horizontalAdvance(text) + 24
        h = fm.height() + 12
        bounds = QRectF(self.rect())
        excl = QRectF(self._excl_rect) if self._excl_rect is not None else None
        x = min(max(hole.left(), bounds.left() + 4), bounds.right() - w - 4)
        y_side = min(max(hole.top(), bounds.top() + 4), bounds.bottom() - h - 4)
        below = QRectF(x, hole.bottom() + 10, w, h)
        above = QRectF(x, hole.top() - 10 - h, w, h)
        right = QRectF(hole.right() + 10, y_side, w, h)
        left = QRectF(hole.left() - 10 - w, y_side, w, h)
        inside = QRectF(x, hole.top() + 10, w, h)
        # order: beside the element for vertical toolbars, else below/above it;
        # never on top of the tour panel
        if getattr(self._target, "prefer_side", False):
            candidates = [right, left, below, above, inside]
        else:
            candidates = [below, above, right, left, inside]
        box = candidates[-1]
        for c in candidates:
            if bounds.contains(c) and (excl is None or not excl.intersects(c)):
                box = c
                break
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ACCENT)
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor(40, 28, 0))
        p.setFont(font)
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)


class OverlayManager:
    """Keeps one overlay per window (main window, dialogs, layout window)."""

    def __init__(self, main_window):
        self._main = main_window
        self._overlays = []  # list of (host, overlay)
        self._active = None
        self._dim = True
        self._exclude = None
        self._font_scale = 1.0

    def _alive(self):
        alive = []
        for host, ov in self._overlays:
            if not sip.isdeleted(host) and not sip.isdeleted(ov):
                alive.append((host, ov))
        self._overlays = alive
        return alive

    def _overlay_for(self, host):
        for h, ov in self._alive():
            if h is host:
                return ov
        ov = SpotlightOverlay(host)
        ov.set_dim(self._dim)
        ov.set_exclude_widget(self._exclude)
        ov.set_font_scale(self._font_scale)
        self._overlays.append((host, ov))
        return ov

    def set_target(self, target, label=""):
        host = target.host_window() if target is not None else None
        for h, ov in self._alive():
            if h is not host:
                ov.set_target(None)
        if target is None or host is None:
            self._active = None
            return
        self._active = self._overlay_for(host)
        self._active.set_target(target, label)

    def target(self):
        if self._active is None or sip.isdeleted(self._active):
            self._active = None
            return None
        return self._active.target()

    def set_dim(self, enabled):
        self._dim = bool(enabled)
        for _, ov in self._alive():
            ov.set_dim(enabled)

    def set_exclude_widget(self, widget):
        self._exclude = widget
        for _, ov in self._alive():
            ov.set_exclude_widget(widget)

    def set_font_scale(self, scale):
        self._font_scale = float(scale)
        for _, ov in self._alive():
            ov.set_font_scale(scale)

    @property
    def dim(self):
        return self._dim

    def cleanup(self):
        for _, ov in self._alive():
            ov.set_target(None)
            ov.setParent(None)
            ov.deleteLater()
        self._overlays = []
        self._active = None
