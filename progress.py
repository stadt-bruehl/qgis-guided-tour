# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stores tour progress and options in the QGIS settings."""

import json

from qgis.core import QgsSettings

PREFIX = "guided_tour/"


def get_bool(key, default=False):
    value = QgsSettings().value(PREFIX + key, default)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "ja")
    return bool(value)


def get_value(key, default=None):
    return QgsSettings().value(PREFIX + key, default)


def set_value(key, value):
    QgsSettings().setValue(PREFIX + key, value)


class Progress:
    KEY = "completed_steps"

    def __init__(self):
        raw = QgsSettings().value(PREFIX + self.KEY, "")
        try:
            self._done = set(json.loads(raw)) if raw else set()
        except (TypeError, ValueError):
            self._done = set()

    def _save(self):
        set_value(self.KEY, json.dumps(sorted(self._done)))

    def is_done(self, step_id):
        return step_id in self._done

    def mark(self, step_id):
        if step_id not in self._done:
            self._done.add(step_id)
            self._save()

    def count(self, step_ids):
        return sum(1 for s in step_ids if s in self._done)

    def reset(self, step_ids=None):
        """Clear progress – only for the given steps, or completely."""
        if step_ids is None:
            self._done.clear()
        else:
            self._done.difference_update(step_ids)
        self._save()
