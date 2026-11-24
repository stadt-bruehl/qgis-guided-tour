# Guided Tour – QGIS plugin (0.0.2)

Interactive introduction to the QGIS user interface as a dock widget. UI elements are
highlighted directly in the QGIS window (spotlight with an orange frame) – also in dialogs
such as the Data Source Manager, the Processing dialog and the layout window. Small tasks
are detected automatically, and all topics remain available as a reference after the tour
(search + double-click on a topic/step).

The tour content is currently available in German only (`content/tour_de.json`).

## Installation from a ZIP file

Download `guided_tour-<version>.zip` from the
[releases page](https://github.com/stadt-bruehl/qgis-guided-tour/releases), then in QGIS:
*Plugins → Manage and Install Plugins → Install from ZIP*. The plugin is marked as
experimental, so enable *Show also experimental plugins* in the settings if it does not appear.

Releases are built by a GitHub Actions workflow when a tag `v<version>` is pushed
(for example `v0.0.2`; the tag must match `version` in `metadata.txt`).

## Installation for development

Copy or link the folder `guided_tour` into the plugin folder of your QGIS profile,
e.g. on Windows:

    %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\guided_tour

Then start QGIS → *Plugins → Manage and Install Plugins* → enable **Guided Tour**.
The easiest way to reload code changes is the **Plugin Reloader** plugin.

On the very first load the dock widget opens automatically. Otherwise use the plugin icon
in the toolbar or *Help → Guided Tour through QGIS*.

## Structure

| File | Purpose |
|---|---|
| `plugin.py` | Entry point: action, menus, dock widget, first start |
| `tour_dock.py` | Dock widget: progress, search, topic tree, step display, navigation |
| `engine.py` | Flow control (complete tour / single topic), Next/Back, auto-advance |
| `targets.py` | Finds UI elements (docks, toolbars, actions, menus, list entries, buttons – also in other windows) |
| `highlight.py` | Spotlight overlay (transparent to mouse events), one overlay per window/dialog |
| `watchers.py` | Task detection via QGIS signals (layer added, tool active, …) |
| `helpers.py` | Buttons such as “Load OpenStreetMap background”, “Create sample point layer”, “Open buffer tool”, “Open new print layout”, “Open filter dialog for the layer”, “Create new GeoPackage layer”, “Open ‘Save Features As …’”, “Enable labeling automatically” |
| `translate.py` | UI translation (loads `i18n/guided_tour_<lang>.qm` for the QGIS/system language) |
| `progress.py` | Progress/options in the QGIS settings (`guided_tour/…`) |
| `content/tour_de.json` | **All texts** (informal German “Du” form): 15 topics, 82 steps |

## Editing the content

Texts, targets and tasks live exclusively in `content/tour_de.json` – no Python needs to be
touched for new steps. For the format see the docstring in `content.py`, for possible
target types see `targets.py`, for task types see `watchers.py`.
Additional languages: put a `tour_en.json` next to it (selected via the QGIS language).

### Targets in dialogs and other windows

Every target can be restricted to a separate window with `"window": "<Qt class>"`,
e.g. `QgsDataSourceManagerDialog`, `QgsProcessingAlgorithmDialogBase`,
`QgsLayoutDesignerDialog` (base classes count too). If the window is not open, the next
alternative in `targets` is used – usually the button in the main window that opens it.
As soon as the window opens, the highlight jumps there automatically.

Further target types: `item` (entry in a list/tree by text), `button` (button by label),
`window`; further task types: `window_opened`, `window_closed`, `item_selected`,
`text_entered`, `layout_item_added`, `layer_filtered`, `labels_enabled`.
`class` targets can additionally have `texts` (e.g. the combo box “Single Labels”),
`item` targets also find entries via their tooltip (icon tabs without text).

## Translations of the user interface

The UI language follows the QGIS language (*Settings → Options → General*) or the system
language. English is the source language; German is included. Tour content has its own files
(see above).

- Strings in code are wrapped in `tr("…")` (`translate.py`).
- Translations live in `tools/translations/<lang>.json` (`{"English text": "translation"}`).
- Run `python3 tools/build_translations.py` (needs Qt's `lrelease`) to write
  `i18n/guided_tour_<lang>.ts` and compile `i18n/guided_tour_<lang>.qm`. Commit both files.
- A new language: add `tools/translations/<lang>.json` and run the script.

## Separate window / second screen

Click **⧉ Separate window** at the bottom of the panel: the panel becomes a normal window with
a title bar (including taskbar entry and maximize) and can be dragged to a second screen.
**⇤ Dock** brings it back. Optionally **Always on top**. Mode and window position are saved
(`guided_tour/window_mode`, `window_geometry`); if the second screen is not connected at
the next start, the window appears centered over QGIS.

## Font size

The default is 1.3 times the QGIS font; adjustable at the bottom of the dock widget with
**A−/A+** (stored under `guided_tour/font_scale`). The label on the spotlight grows with it.

## Open points

- Verify objectNames/class names in the QGIS version in use (among others the CRS button,
  `mOptionsListWidget` of the Data Source Manager, `ItemDock`/`mToolsToolbar` in the layout
  window, `lstFields`/`lstValues`/`mTxtSql` in the filter dialog, `mFormatComboBox` in the
  export dialog, `iface.actionLayerSaveAs()`) – elements that are not found are reported by
  the dock widget, and the tour continues anyway

## License

GPL-2.0-or-later, see `LICENSE`.
