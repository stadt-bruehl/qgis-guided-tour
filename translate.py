# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""UI translation: English source strings, Qt translation files in ``i18n/``.

The language follows the QGIS user locale (Settings → Options → General), or the system
locale if QGIS has no override. Missing translations fall back to the English source text.
"""

import os

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator

CONTEXT = "GuidedTour"
_translator = None


def tr(text):
    """Translate a UI string (English source text)."""
    return QCoreApplication.translate(CONTEXT, text)


def _language():
    settings = QgsSettings()
    if settings.value("locale/overrideFlag", False, type=bool):
        name = settings.value("locale/userLocale", "")
    else:
        name = QLocale.system().name()
    return str(name or "en")[:2].lower()


def install(plugin_dir):
    """Load ``i18n/guided_tour_<lang>.qm`` if it exists (English needs no file)."""
    global _translator
    remove()
    path = os.path.join(plugin_dir, "i18n", "guided_tour_{}.qm".format(_language()))
    if not os.path.isfile(path):
        return
    translator = QTranslator()
    if translator.load(path):
        QCoreApplication.installTranslator(translator)
        _translator = translator


def remove():
    global _translator
    if _translator is not None:
        QCoreApplication.removeTranslator(_translator)
        _translator = None
