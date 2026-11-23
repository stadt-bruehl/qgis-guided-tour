# How to create a new tour package

A tour is one JSON file in this folder. The plugin finds it automatically – no Python code
needs to be changed. The reference documentation lives in the docstrings of `content.py`
(file format), `targets.py` (target types) and `watchers.py` (task types).

## 1. Create the file

File name: `<tourname>_<language>.json`

- `<tourname>`: any name, e.g. `processing`
- `<language>`: two lowercase letters, e.g. `de`, `en`

Other file names (including this `.md` file) are ignored.

Per tour the plugin loads the file in the QGIS user language. If that language does not
exist, it falls back to `_de`. A tour without a `_de` file and without a file in the user
language is skipped. So always provide the `_de` file, or a file for every language you
want to support.

Files are read once when the plugin starts. Restart QGIS (or reload the plugin) after
adding or changing a file.

## 2. Minimal structure

```json
{
  "tour": {
    "id": "processing",
    "title": "Processing basics",
    "welcome_title": "Welcome to Processing!",
    "order": 20
  },
  "welcome": "<p>HTML shown on the start page.</p>",
  "finished": "<p>HTML shown after the complete tour.</p>",
  "topics": [
    {
      "id": "toolbox",
      "title": "The Processing Toolbox",
      "description": "Short description (tooltip)",
      "steps": [
        {
          "id": "toolbox.open",
          "title": "Open the toolbox",
          "text": "<p>Explanation. <b>HTML</b> is allowed.</p>",
          "targets": [
            {"type": "dock", "name": "ProcessingToolbox"}
          ],
          "task": "Open the Processing Toolbox.",
          "complete_on": {"type": "dock_shown", "name": "ProcessingToolbox"},
          "helpers": [],
          "keywords": ["processing", "toolbox"]
        }
      ]
    }
  ]
}
```

### The `tour` block (optional)

| Key | Meaning | Default |
|---|---|---|
| `id` | Unique ID of the tour | file name without `_<language>.json` |
| `title` | Name in the tour selection | `QGIS basics` |
| `welcome_title` | Heading of the start page | `Welcome to QGIS!` |
| `order` | Position in the selection (lower = earlier) | `50` |
| `requires_plugin` | Only offer the tour if this plugin is installed | none |

`requires_plugin` accepts a plugin folder name or display name. Case, spaces, `_` and `-`
are ignored. Alternatives are separated with `|`, e.g. `"my_plugin|my_plugin_alt"`.

The selection at the top of the dock only appears if more than one tour is available.

### Topics and steps

- Topics group steps. Every topic and step needs a unique `id`. Step IDs must be unique
  across the whole tour (a duplicate is reported in the QGIS log). A common scheme is
  `<topic>.<step>`.
- Required for a step: `id`, `title`. All other keys are optional.

| Step key | Meaning |
|---|---|
| `text` | Explanation (HTML) |
| `targets` | List of alternatives to highlight – the first one found wins |
| `task` | Task shown to the user |
| `complete_on` | How the plugin detects that the task is done |
| `helpers` | Buttons that perform an action (e.g. load sample data) |
| `keywords` | Extra search terms for the search box |

A step without `complete_on` is an info step: it counts as done when the user clicks *Next*.

## 3. Targets (what is highlighted)

`targets` is a list. Put the best candidate first and fallbacks after it. The highlight
jumps to a better alternative as soon as it appears (e.g. when a dialog opens).

| `type` | Finds | Typical keys |
|---|---|---|
| `canvas` | the map view | – |
| `dock` | a panel | `name` = objectName, e.g. `Layers`, `Browser`, `ProcessingToolbox`, `LayerStyling` |
| `toolbar` | a toolbar | `name`, e.g. `mMapNavToolBar` |
| `action` | a tool button | `name` = iface method, e.g. `actionPan` |
| `menu` | a main menu | `name` (objectName) and/or `titles` (visible titles, e.g. `["Projekt", "Project"]`) |
| `menubar`, `statusbar` | the bars | – |
| `object` | any widget | `name` = objectName |
| `class` | first visible widget of a Qt class | `name` = class, optional `texts` |
| `window` | a whole window | `window` |
| `item` | entry in a list/tree | `texts`, optional `depth`, `scroll_to`, `view_class` |
| `button` | a button | `texts` (label or tooltip) |
| `tour_dock` | this plugin's dock | – |

Optional keys for every target:

- `"window": "<Qt class or objectName>"` – search only in that window or dialog. If it is not
  open, the target counts as not found and the next alternative is used.
- `"in_dock": "<objectName>"` – search only inside that panel.
- `"ensure_visible": false` – do not show a hidden panel or toolbar automatically.

Texts are matched exactly first, then as a substring, ignoring case and `&`.
List several spellings in `texts` and `titles` to support several QGIS languages.

## 4. Task detection (`complete_on`)

| `type` | Done when … |
|---|---|
| `action_triggered` | the action `{"action": "…"}` is triggered |
| `map_tool` | the map tool `{"action": "…"}` is active |
| `extent_changed` | the map extent changes |
| `layer_added` | a layer is added |
| `current_layer_changed` | another layer is selected |
| `visibility_changed` | a layer checkbox is toggled |
| `selection_changed` | the feature selection changes |
| `editing_toggled` | editing is toggled; optional `"state": true/false` |
| `project_saved` | the project is saved |
| `dock_shown` | the panel `{"name": "…"}` is shown |
| `layout_opened` | a print layout window opens |
| `window_opened` / `window_closed` | `{"window": "…"}` opens / closes |
| `item_selected` | an entry is selected (`window`/`in_dock`, `texts`) |
| `text_entered` | text is typed into an input field (`window`/`in_dock`, `texts`) |
| `button_checked` | a toggle button is switched (`in_dock`, `texts`, `state`) |
| `context_menu` | a context menu opens (`in_dock`) |
| `layout_item_added` | an item is added to the layout (`item_type`, e.g. `QgsLayoutItemMap`) |
| `layer_filtered` | a filter is set; `{"state": false}` = removed |
| `labels_enabled` | labeling is enabled for a layer |

Some types use polling every 400 ms; the exact list is in `watchers.py`.

The polling types accept `"in_class": "<Qt class>"` in addition to `window` and `in_dock`: only
the first visible widget of that class is searched (e.g. `"in_class": "QgsLocatorWidget"` for
the locator bar). Without any of the three, `text_entered` looks at every visible input field of
the main window.

## 5. Helpers

`helpers` is a list of IDs. Each becomes a button below the step text. Available IDs
(see `helpers.py`):

`load_osm`, `load_sample_points`, `zoom_full`, `open_dsm`, `open_layout`, `open_buffer`,
`open_filter`, `clear_filters`, `open_save_as`, `open_new_gpkg`, `open_new_shp`,
`open_styling`, `enable_labels`

Helpers whose ID starts with `open_` are hidden while a modal dialog is open.
A new helper needs a function and an entry in the `HELPERS` dictionary in `helpers.py`.

## 6. Checklist

1. The file name matches `<tourname>_<language>.json` and the JSON is valid.
2. All `id` values are unique.
3. Every target has a fallback if the element may be hidden or in a dialog.
4. Technical names (objectNames, class names) match your QGIS version. Elements that are
   not found are reported in the dock; the tour continues anyway.
5. Restart QGIS and check the QGIS log (message panel, tab *Guided Tour*) for warnings such
   as `Tour … could not be loaded` or `Duplicate step ID`.
