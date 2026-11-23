# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guided Tour – interactive introduction to the QGIS user interface."""


def classFactory(iface):  # noqa: N802 (QGIS convention)
    from .plugin import GuidedTourPlugin

    return GuidedTourPlugin(iface)
