# SPDX-License-Identifier: GPL-2.0-or-later
"""Write i18n/guided_tour_<lang>.ts from tools/translations/<lang>.json and compile .qm files.

Usage: python3 tools/build_translations.py   (needs Qt's ``lrelease`` for the .qm step)
Add a language: create tools/translations/<lang>.json ({"English text": "translation"}).
"""
import glob
import json
import os
import shutil
import subprocess
from xml.sax.saxutils import escape

from extract_strings import ROOT, extract

CONTEXT = "GuidedTour"


def build(lang, translations, sources):
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<!DOCTYPE TS>",
           '<TS version="2.1" language="{}">'.format(lang), "<context>", "    <name>{}</name>".format(CONTEXT)]
    for text, (filename, line) in sources.items():
        tr = translations.get(text)
        out += ["    <message>",
                '        <location filename="../{}" line="{}"/>'.format(filename, line),
                "        <source>{}</source>".format(escape(text)),
                ("        <translation>{}</translation>".format(escape(tr)) if tr
                 else '        <translation type="unfinished"></translation>'),
                "    </message>"]
    out += ["</context>", "</TS>", ""]
    path = os.path.join(ROOT, "i18n", "guided_tour_{}.ts".format(lang))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    return path


if __name__ == "__main__":
    sources = extract()
    lrelease = shutil.which("lrelease") or shutil.which("lrelease-qt5") or shutil.which("lrelease-qt6")
    for tfile in sorted(glob.glob(os.path.join(ROOT, "tools", "translations", "*.json"))):
        lang = os.path.splitext(os.path.basename(tfile))[0]
        translations = json.load(open(tfile, encoding="utf-8"))
        unknown = set(translations) - set(sources)
        missing = set(sources) - set(translations)
        print(lang, "obsolete:", sorted(unknown), "missing:", sorted(missing))
        ts = build(lang, translations, sources)
        if lrelease:
            subprocess.run([lrelease, ts, "-qm", ts[:-3] + ".qm"], check=True)
        else:
            print("lrelease not found - .qm not built")
