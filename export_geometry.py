
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant,Qt
from qgis.PyQt.QtGui import QIcon, QFont
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QProgressDialog
from qgis.core import (
    QgsProcessingFeatureSourceDefinition,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsWkbTypes,
    QgsProject,
    QgsRectangle,
    QgsField,
    QgsFeature,
    QgsMapLayer,
    QgsGeometry,
    QgsProcessingFeedback,
    QgsSpatialIndex, 
    QgsPalLayerSettings, 
    QgsTextFormat, 
    QgsVectorLayerSimpleLabeling
)
from qgis.core import QgsMessageLog, Qgis

import processing
import os

def check_geometries_and_extents(layers):
    """Check for invalid geometries and ensure layer extents overlap."""
    invalid_geometries = []
    all_extents = []
    valid = True
    one_raster = False

    for i, layer in enumerate(layers):
        if not layer.isValid():
            raise Exception(f"The layer {layer.name()} is invalid or has been deleted. Please restart QGIS.")

        if layer.type() == QgsVectorLayer.VectorLayer:
            for feature in layer.getFeatures():
                if not feature.geometry().isGeosValid():
                    invalid_geometries.append((layer.name(), feature.id()))
                    valid = False
            all_extents.append(layer.extent())
        if layer.type() == QgsRasterLayer.RasterLayer :
            if one_raster :
                valid = False
                raise Exception(f"More than One Raster Layer found, the process only supports One raster layer.")
            else :
                one_raster = True


    combined_extent = QgsRectangle()
    for extent in all_extents:
        combined_extent.combineExtentWith(extent)

    if combined_extent.isEmpty() and all_extents:
            valid = False
            raise Exception("No overlapping extents found among layers.")

    if invalid_geometries:
        valid = False
        msg = "Invalid geometries detected:\n" + "\n".join(
            [f"Layer: {layer}, Feature ID: {fid}" for layer, fid in invalid_geometries]
        )
        raise Exception(msg)

    return valid

def check_polygon_in_a_layer(layer):
    valid = True
    invalid_geometries = []
    geometry_type = QgsWkbTypes.flatType(layer.wkbType())

    if geometry_type not in [QgsWkbTypes.MultiPolygon, QgsWkbTypes.Polygon]:
        raise Exception("The grid/segmentation Layer should be of type: Polygon")

    # Check if "id" attribute exists
    provider = layer.dataProvider()
    existing_fields = [field.name() for field in provider.fields()]
    
    if "id" not in existing_fields:
        print("ID field not found. Adding 'id' field and assigning values...")
        
        # Add "id" field
        provider.addAttributes([QgsField("id", QVariant.Int)])
        layer.updateFields()  # Update layer to reflect new field
        
        # Assign auto-increment values to "id"
        layer.startEditing()
        for i, feature in enumerate(layer.getFeatures(), start=1):
            feature["id"] = i
            layer.updateFeature(feature)
        layer.commitChanges()

    # Check for invalid geometries
    for feature in layer.getFeatures():
        if not feature.geometry().isGeosValid():
            invalid_geometries.append((layer.name(), feature.id()))
            valid = False

    if invalid_geometries:
        msg = "Invalid geometries detected:\n" + "\n".join(
            [f"Layer: {layer}, Feature ID: {fid}" for layer, fid in invalid_geometries]
        )
        raise Exception(msg)

    return valid

def validate_layer(layer):
    """
    Validate a QgsVectorLayer and return any issues found.

    :param layer: QgsVectorLayer to validate.
    :return: List of error messages or empty list if valid.
    """
    errors = []

    # Check if the layer is valid
    if not layer.isValid():
        errors.append("The layer is not valid. Check the file path or data source.")
        return errors
    else :
        QgsMessageLog.logMessage('Layers valid : '+ str(layer.name()), 'AMRUT_Export', Qgis.Info)

    # Check CRS validity
    if layer.crs().isValid():
        crs = layer.crs().authid()
    else:
        errors.append("The layer's CRS is invalid or not defined.")
        crs = "Undefined"

    # Check for features
    features = list(layer.getFeatures())
    if not features:
        errors.append("The layer contains no features.")

    # Check feature geometries
    for i, feature in enumerate(features):
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            errors.append(f"Feature ID {feature.id()} has no geometry.")
        elif not geom.isGeosValid():
            errors.append(f"Feature ID {feature.id()} has an invalid geometry.")

        # Check for 'id' attribute
        if feature.id() == -1:  # Check if the feature ID is invalid
            print("Feature ID is null or invalid.")

    # Check attribute fields
    if not layer.fields():
        errors.append("The layer contains no attribute fields.")
    else:
        for field in layer.fields():
            if not field.name():
                errors.append("A field has an empty name.")
            if field.type() == QVariant.Invalid:
                errors.append(f"Field '{field.name()}' has an invalid type.")


    return errors


def getExtent(layers):
    all_extents = []

    # Collect extents of vector layers
    for i, layer in enumerate(layers):
        if layer.type() == QgsMapLayer.VectorLayer:  # Correct layer type check
            all_extents.append(layer.extent())

    # Combine extents
    if all_extents:  # Ensure there are extents to combine
        combined_extent = all_extents[0]
        for extent in all_extents[1:]:
            combined_extent.combineExtentWith(extent)
        return combined_extent
    else:
        return QgsRectangle()  # Return an empty extent if no layers are valid


