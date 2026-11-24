# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Helper actions a step can offer as a button (e.g. load sample data)."""

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .compat import INFO, SUCCESS, WARNING
from .translate import tr

TAG = "guided_tour/helper"

# Sample data: cities in North Rhine-Westphalia (rounded values, for practice only).
# Field names, type values and the layer name stay German: the German tour content refers to them.
SAMPLE_CITIES = [
    ("Köln", 6.9603, 50.9375, 1084000, "Metropole"),
    ("Düsseldorf", 6.7735, 51.2277, 620000, "Metropole"),
    ("Dortmund", 7.4653, 51.5136, 590000, "Metropole"),
    ("Essen", 7.0116, 51.4556, 580000, "Metropole"),
    ("Duisburg", 6.7623, 51.4344, 500000, "Metropole"),
    ("Bonn", 7.0982, 50.7374, 330000, "Großstadt"),
    ("Münster", 7.6261, 51.9607, 320000, "Großstadt"),
    ("Wuppertal", 7.1500, 51.2562, 355000, "Großstadt"),
    ("Bielefeld", 8.5325, 52.0302, 335000, "Großstadt"),
    ("Aachen", 6.0839, 50.7753, 250000, "Großstadt"),
]


def _message(iface, text, level=INFO):
    iface.messageBar().pushMessage(tr("Guided Tour"), text, level=level, duration=4)


def _existing(tag_value):
    for layer in QgsProject.instance().mapLayers().values():
        if layer.customProperty(TAG) == tag_value:
            return layer
    return None


def _zoom_to(iface, layer, factor=1.3):
    canvas = iface.mapCanvas()
    xform = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(), QgsProject.instance())
    extent = xform.transformBoundingBox(layer.extent())
    extent.scale(factor)
    canvas.setExtent(extent)
    canvas.refresh()


def load_osm(iface):
    if _existing("osm") is not None:
        _message(iface, tr("The OpenStreetMap map is already loaded."))
        return
    uri = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0"
    layer = QgsRasterLayer(uri, "OpenStreetMap", "wms")
    if not layer.isValid():
        _message(iface, tr("OpenStreetMap could not be loaded – please check your internet connection or proxy."), WARNING)
        return
    layer.setCustomProperty(TAG, "osm")
    project = QgsProject.instance()
    project.addMapLayer(layer, False)
    root = project.layerTreeRoot()
    root.insertLayer(len(root.children()), layer)  # very bottom = background
    _message(iface, tr("OpenStreetMap was loaded as the background map."), SUCCESS)


def load_sample_points(iface):
    layer = _existing("sample")
    if layer is None:
        uri = "Point?crs=EPSG:4326&field=name:string(50)&field=einwohner:integer&field=typ:string(30)"
        layer = QgsVectorLayer(uri, "Beispielstädte (Tour)", "memory")
        features = []
        for name, x, y, population, city_type in SAMPLE_CITIES:
            f = QgsFeature(layer.fields())
            f.setAttributes([name, population, city_type])
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            features.append(f)
        layer.dataProvider().addFeatures(features)
        layer.updateExtents()
        layer.setCustomProperty(TAG, "sample")
        QgsProject.instance().addMapLayer(layer)
        _message(iface, tr("A sample point layer with ten cities is now available."), SUCCESS)
    iface.setActiveLayer(layer)
    _zoom_to(iface, layer)


def zoom_full(iface):
    iface.zoomFull()


def open_dsm(iface):
    iface.actionDataSourceManager().trigger()


def open_layout(iface):
    from qgis.core import QgsPrintLayout

    project = QgsProject.instance()
    manager = project.layoutManager()
    name = "Tour layout"
    n = 2
    while manager.layoutByName(name) is not None:
        name = "Tour layout {}".format(n)
        n += 1
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(name)
    manager.addLayout(layout)
    iface.openLayoutDesigner(layout)


def open_buffer(iface):
    try:
        import processing
    except ImportError:
        _message(iface, tr("The Processing plugin is not active (Plugins → Processing)."), WARNING)
        return
    params = {}
    sample = _existing("sample")
    if sample is not None:
        params = {"INPUT": sample.id(), "DISTANCE": 0.1}
    processing.execAlgorithmDialog("native:buffer", params)


_open_dialogs = []  # keep references so non-modal dialogs are not garbage-collected immediately


def _work_layer(iface):
    """Sample layer, else the active vector layer – or None with a hint."""
    layer = _existing("sample")
    if layer is None:
        active = iface.activeLayer()
        if active is not None and hasattr(active, "subsetString"):
            layer = active
    if layer is None:
        _message(iface, tr("Please select a vector layer in the Layers panel first "
                           "(or create the sample point layer)."), WARNING)
        return None
    iface.setActiveLayer(layer)
    return layer


def _trigger(iface, action_name, fallback_text):
    attr = getattr(iface, action_name, None)
    act = attr() if callable(attr) else None
    if act is None:
        _message(iface, fallback_text, WARNING)
        return
    act.trigger()


def open_filter(iface):
    layer = _work_layer(iface)
    if layer is None:
        return
    from qgis.gui import QgsQueryBuilder
    from qgis.PyQt.QtCore import Qt

    dlg = QgsQueryBuilder(layer, iface.mainWindow())
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    _open_dialogs[:] = [d for d in _open_dialogs if not _deleted(d)] + [dlg]
    dlg.open()


def _deleted(obj):
    from qgis.PyQt import sip

    return sip.isdeleted(obj)


def clear_filters(iface):
    n = 0
    for layer in QgsProject.instance().mapLayers().values():
        if hasattr(layer, "subsetString") and layer.subsetString().strip():
            layer.setSubsetString("")
            n += 1
    _message(iface, tr("{} filter(s) removed.").format(n) if n else tr("No filter is currently set."))


def open_save_as(iface):
    if _work_layer(iface) is None:
        return
    _trigger(iface, "actionLayerSaveAs",
             tr("Please right-click the layer → Export → Save Features As … to open it."))


def open_new_gpkg(iface):
    _trigger(iface, "actionNewGeoPackageLayer", tr("Please open it via Layer → Create Layer → New GeoPackage Layer."))


def open_new_shp(iface):
    _trigger(iface, "actionNewVectorLayer", tr("Please open it via Layer → Create Layer → New Shapefile Layer."))


def open_styling(iface):
    from qgis.PyQt.QtWidgets import QDockWidget

    dock = iface.mainWindow().findChild(QDockWidget, "LayerStyling")
    if dock is None:
        _message(iface, tr("Please press F7 to open the Layer Styling panel."), WARNING)
        return
    dock.setVisible(True)
    dock.raise_()


def enable_labels(iface):
    layer = _work_layer(iface)
    if layer is None:
        return
    from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling

    names = layer.fields().names()
    field = "name" if "name" in names else (names[0] if names else None)
    if field is None:
        _message(iface, tr("The layer has no fields that could be labeled."), WARNING)
        return
    settings = QgsPalLayerSettings()
    settings.fieldName = field
    fmt = settings.format()
    buf = fmt.buffer()
    buf.setEnabled(True)
    buf.setSize(1.0)
    fmt.setBuffer(buf)
    settings.setFormat(fmt)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    _message(iface, tr("Labeling enabled with field “{}”.").format(field), SUCCESS)


HELPERS = {
    "load_osm": ("Load OpenStreetMap background", load_osm),
    "load_sample_points": ("Create sample point layer", load_sample_points),
    "zoom_full": ("Zoom to all layers", zoom_full),
    "open_dsm": ("Open Data Source Manager", open_dsm),
    "open_layout": ("Open new print layout", open_layout),
    "open_buffer": ("Open buffer tool", open_buffer),
    "open_filter": ("Open filter dialog for the layer", open_filter),
    "clear_filters": ("Remove all filters", clear_filters),
    "open_save_as": ("Open “Save Features As …”", open_save_as),
    "open_new_gpkg": ("Create new GeoPackage layer", open_new_gpkg),
    "open_new_shp": ("Create new shapefile layer", open_new_shp),
    "open_styling": ("Open Layer Styling panel", open_styling),
    "enable_labels": ("Enable labeling automatically", enable_labels),
}


def label(name):
    return tr(HELPERS.get(name, (name, None))[0])


def run(name, iface):
    entry = HELPERS.get(name)
    if entry is None:
        _message(iface, tr("Unknown helper action: {}").format(name), WARNING)
        return
    entry[1](iface)
