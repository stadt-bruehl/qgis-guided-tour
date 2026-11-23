# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Loads the tour content (topics and steps) from content/<tour>_<language>.json.

There can be several tours (e.g. ``tour_de.json`` for QGIS and
``my_plugin_de.json`` for another plugin). Each file is a
separate tour; the dock widget offers a selection at the top.

JSON file structure::

    {
      "tour": {                          # optional – information about the tour itself
        "id": "qgis",                    # unique ID (default: file name)
        "title": "QGIS basics",          # name in the tour selection
        "welcome_title": "Welcome …",    # heading of the start page
        "order": 10,                     # order in the selection
        "requires_plugin": "my_plugin"  # only offer if the plugin is installed
      },
      "welcome": "<html>…",              # start page text in the dock widget
      "finished": "<html>…",             # text shown after the complete tour
      "topics": [
        {
          "id": "navigation",
          "title": "Navigating the map",
          "description": "Short description (tooltip)",
          "steps": [
            {
              "id": "navigation.pan",
              "title": "Pan the map",
              "text": "<p>Explanation (HTML allowed)</p>",
              "targets": [ {"type": "action", "name": "actionPan"} ],
              "task": "Optional task for the user",
              "complete_on": {"type": "map_tool", "action": "actionPan"},
              "helpers": ["load_osm"],
              "keywords": ["pan", "move"]
            }
          ]
        }
      ]
    }

``targets`` is a list of alternatives – the first one found in the current
interface is highlighted (see targets.py).
``complete_on`` describes how to detect that the task is done
(see watchers.py). ``helpers`` are buttons that e.g. load sample data
(see helpers.py).
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from qgis.core import QgsSettings

from .compat import WARNING, log

logger = logging.getLogger(__name__)


@dataclass
class Step:
    id: str
    title: str
    text: str
    topic_id: str
    targets: List[dict] = field(default_factory=list)
    task: str = ""
    complete_on: Optional[dict] = None
    helpers: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    def search_text(self):
        plain = re.sub(r"<[^>]+>", " ", self.text)
        return " ".join([self.title, plain, self.task, " ".join(self.keywords)]).lower()


@dataclass
class Topic:
    id: str
    title: str
    description: str = ""
    steps: List[Step] = field(default_factory=list)

    def search_text(self):
        return (self.title + " " + self.description).lower()


class TourContent:
    def __init__(self, data, default_id="tour"):
        meta = data.get("tour", {}) or {}
        self.id = meta.get("id") or default_id
        self.title = meta.get("title") or "QGIS basics"
        self.welcome_title = meta.get("welcome_title") or "Welcome to QGIS!"
        self.order = int(meta.get("order", 50))
        self.requires_plugin = meta.get("requires_plugin") or ""
        self.welcome = data.get("welcome", "")
        self.finished = data.get("finished", "")
        self.topics = []
        self._steps = {}
        for t in data.get("topics", []):
            topic = Topic(id=t["id"], title=t["title"], description=t.get("description", ""))
            for s in t.get("steps", []):
                step = Step(
                    id=s["id"],
                    title=s["title"],
                    text=s.get("text", ""),
                    topic_id=topic.id,
                    targets=s.get("targets", []),
                    task=s.get("task", ""),
                    complete_on=s.get("complete_on"),
                    helpers=s.get("helpers", []),
                    keywords=s.get("keywords", []),
                )
                if step.id in self._steps:
                    log("Duplicate step ID in the tour content: {}".format(step.id), WARNING)
                self._steps[step.id] = step
                topic.steps.append(step)
            self.topics.append(topic)

    def all_steps(self):
        return [s for t in self.topics for s in t.steps]

    def step(self, step_id):
        return self._steps.get(step_id)

    def topic(self, topic_id):
        for t in self.topics:
            if t.id == topic_id:
                return t
        return None


def _language():
    locale = QgsSettings().value("locale/userLocale", "de") or "de"
    return str(locale)[:2].lower()


def _norm(name):
    """'Layer-Verwaltung', 'layer_verwaltung', 'LayerVerwaltung' -> 'layerverwaltung'."""
    return re.sub(r"[\s_\-]+", "", str(name)).lower()


def _plugin_available(name):
    """True if a plugin with this folder name OR display name is installed.

    Case, spaces, '_' and '-' are ignored. Several alternatives are possible
    with '|', e.g. "my_plugin|my_plugin_alt".
    """
    if not name:
        return True
    try:
        from qgis.utils import available_plugins, pluginMetadata, plugins
    except Exception:
        return True
    installed = set()
    for folder in set(plugins) | set(available_plugins):
        installed.add(_norm(folder))
        meta_name = pluginMetadata(folder, "name")
        if meta_name == "__error__":
            logger.debug("No metadata name for plugin '%s'", folder)
        else:
            installed.add(_norm(meta_name))
    wanted = [_norm(n) for n in str(name).split("|") if n.strip()]
    found = any(w in installed for w in wanted)
    if not found:
        log("Tour skipped: plugin '{}' not found (installed: {})".format(
            name, ", ".join(sorted(set(plugins) | set(available_plugins)))), WARNING)
    return found


def load_tours(plugin_dir):
    """All tours from content/ – per tour the file in the user language, else German."""
    content_dir = os.path.join(plugin_dir, "content")
    lang = _language()
    files = {}  # tour name -> {language: path}
    for name in sorted(os.listdir(content_dir)):
        m = re.match(r"^(.+)_([a-z]{2})\.json$", name)
        if m:
            files.setdefault(m.group(1), {})[m.group(2)] = os.path.join(content_dir, name)
    tours = []
    for base, variants in files.items():
        path = variants.get(lang) or variants.get("de")
        if path is None:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                tour = TourContent(json.load(f), default_id=base)
        except (OSError, ValueError, KeyError) as e:
            log("Tour {} could not be loaded: {}".format(path, e), WARNING)
            continue
        if _plugin_available(tour.requires_plugin):
            tours.append(tour)
    if not tours:
        raise FileNotFoundError("No tour content found in {}".format(content_dir))
    tours.sort(key=lambda t: (t.order, t.title.lower()))
    return tours


def load_content(plugin_dir):
    """First (main) tour – for backward compatibility."""
    return load_tours(plugin_dir)[0]
