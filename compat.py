# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Small compatibility layer for Qt5/Qt6 builds of QGIS."""

try:  # Qt6
    from qgis.PyQt.QtGui import QAction  # noqa: F401
except ImportError:  # Qt5
    from qgis.PyQt.QtWidgets import QAction  # noqa: F401

from qgis.core import Qgis, QgsMessageLog

LOG_TAG = "Guided Tour"


def _level(name):
    level = getattr(Qgis, name, None)
    if level is None:
        level = getattr(Qgis.MessageLevel, name)
    return level


INFO = _level("Info")
WARNING = _level("Warning")
SUCCESS = _level("Success")


def log(message, level=INFO):
    QgsMessageLog.logMessage(str(message), LOG_TAG, level)
