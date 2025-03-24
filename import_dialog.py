from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QLabel, QLineEdit, QHBoxLayout, QComboBox
)
from PyQt5.QtCore import Qt
import tempfile
import os
import shutil
import zipfile
import json
from qgis.core import (
    QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsRectangle, QgsMapLayer, QgsMessageLog, Qgis
)

from . import export_ui as ui
from . import qc_visualization_dialog as qc
from . import import_reconstruct_dialog as reconstruct_dialog


class ImportDialog(QDialog):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface

    def reconstruct_or_qc_dialog(self):
        """Main dialog to choose between reconstructing a layer or performing a quality check"""
        dialog = self.create_dialog("AMRUT 2.0", 500, 250)
        layout = QVBoxLayout(dialog)

        # Add logo layout
        logo_layout = ui.createLogoLayout("SANKALAN 2.0", "Data From Mobile")
        layout.addLayout(logo_layout)

        # Add buttons for "Reconstruct Layer" and "Quality Check"
        self.add_centered_button(
            layout, 
            "Quality Check", 
            lambda: self._open_dialog(dialog, self.quality_check_dialog)
        )
        self.add_centered_button(
            layout, 
            "Reconstruct Layer", 
            lambda: self._open_dialog(dialog, self.reconstruct_dialog)
        )
        footer_note = ui.get_footer_note()
        layout.addWidget(footer_note, alignment=Qt.AlignCenter)

        dialog.exec_()

    def create_dialog(self, title, width, height):
        """Helper function to create a generic dialog window"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(width, height)
        return dialog

    def add_centered_button(self, layout, text, callback):
        """Helper function to add a centered button to a layout"""
        button = QPushButton(text)
        button.setFixedSize(200, 25)
        button.clicked.connect(callback)
        layout.addWidget(button, alignment=Qt.AlignCenter)

    def _open_dialog(self, current_dialog, next_dialog):
        """Close the current dialog and open the next one"""
        current_dialog.accept()
        try:
            next_dialog()
        except Exception as e:
            QgsMessageLog.logMessage(f"Error opening dialog: {str(e)}", 'AMRUT', Qgis.Critical)

    def reconstruct_dialog(self):
        """Placeholder for the "Reconstruct Layer" dialog"""
        self.reconstructDialog = reconstruct_dialog.ReconstructLayerTabDialog(self.iface)
        self.reconstructDialog.exec_()
        pass

    def quality_check_dialog(self):
        """Quality check dialog for layer selection and validation"""
        try:
            qc_dialog = self.create_dialog("AMRUT 2.0", 500, 350)
            layout = QVBoxLayout(qc_dialog)

            # Add logo layout
            logo_layout = ui.createLogoLayout("Quality Check")
            layout.addLayout(logo_layout)
            layout.addSpacing(10)

            # Add file input field
            self.file_input = self._add_file_input(layout)

            # Add dropdowns for layer and optional raster layer selection
            self.layer_dropdown = QComboBox(qc_dialog)
            self.raster_layer_dropdown = QComboBox(qc_dialog)

            layout.addSpacing(15)
            self._add_dropdown_with_placeholder(
                layout,
                "Select a Raster layer: (Optional)",
                self.raster_layer_dropdown,
                "Select a Raster Layer",
                populate=False
            )
            layout.addSpacing(15)
            self._add_dropdown_with_placeholder(
                layout,
                "Select layer to check:",
                self.layer_dropdown,
                "Select any layer for Quality Check"
            )
            layout.addSpacing(20)

            # Populate raster layers in the dropdown
            raster_layers = [
                layer.name() for layer in QgsProject.instance().mapLayers().values()
                if layer.type() == QgsMapLayer.RasterLayer
            ]
            self.raster_layer_dropdown.addItems(raster_layers)

            # Add proceed button for quality check
            proceed_button = QPushButton("Proceed Quality Check")
            proceed_button.setFixedSize(150, 25)
            proceed_button.clicked.connect(self.proceed_quality_check)
            layout.addWidget(proceed_button, alignment=Qt.AlignCenter)

            qc_dialog.exec_()
        except Exception as e:
            QgsMessageLog.logMessage(f"Error in quality_check_dialog: {str(e)}", 'AMRUT', Qgis.Critical)

    def _add_file_input(self, layout):
        """Add file input layout with a browse button"""
        file_layout = QHBoxLayout()
        file_input = QLineEdit()
        file_input.setPlaceholderText("Select a .amrut file...")
        file_layout.addWidget(file_input)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(browse_button)

        layout.addLayout(file_layout)
        return file_input

    def _add_dropdown_with_placeholder(self, layout, label_text, dropdown, placeholder, populate=True):
        """Add a dropdown with a label and placeholder text"""
        dropdown_layout = QHBoxLayout()  # Use a horizontal layout for label and dropdown
        label = QLabel(label_text)
        dropdown_layout.addWidget(label)

        dropdown.addItem(placeholder)
        
        if populate:
            dropdown.addItems([])  # Populate dropdown if needed

        dropdown_layout.addWidget(dropdown)
        layout.addLayout(dropdown_layout)

    def browse_file(self):
        """Open file dialog to select an .amrut file"""
        try:
            file, _ = QFileDialog.getOpenFileName(
                self, 
                "Select a File", 
                "", 
                "AMRUT Files (*.amrut);;All Files (*)"
            )

            if file:
                if file.endswith(".amrut"):
                    self.selected_file=file
                    self.validate_amrut_file(file)
                else:
                    QMessageBox.warning(self, "Invalid File", "Please select a valid .amrut file.")
                    self.file_input.clear()
        except Exception as e:
            QgsMessageLog.logMessage(f"Error in browse_file: {str(e)}", 'AMRUT', Qgis.Critical)

    def validate_amrut_file(self, file_path):
        """Validate the selected .amrut file"""
        try:
            self.layer_dropdown.clear()
            self.layer_dropdown.addItem("Select any layer for Quality Check")  
            self.layer_dropdown.model().item(0).setEnabled(False)

            temp_dir = tempfile.mkdtemp()

            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                if 'metadata.json' not in zip_ref.namelist():
                    QMessageBox.warning(self, "Missing Metadata File", "The .amrut file does not contain 'metadata.json'.")
                    self.file_input.clear()
                    return
                
                zip_ref.extractall(temp_dir)
                metadata_path = os.path.join(temp_dir, "metadata.json")

                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                except (json.JSONDecodeError, FileNotFoundError):
                    QMessageBox.critical(self, "Invalid Metadata", "Failed to parse metadata.json.")
                    self.file_input.clear()
                    return

                if metadata.get("qc_status") == "verified":
                    QMessageBox.information(self, "File Verified", "All layers of this file have been verified.")
                    self.file_input.clear()
                    return

                if 'layers' not in metadata or not isinstance(metadata['layers'], list):
                    QMessageBox.warning(self, "Invalid Metadata", "'layers' array is missing or invalid in metadata.json.")
                    self.file_input.clear()
                    return

                # Extract layer names
                layer_names = [layer.split(" : ")[0].strip("{}").strip() for layer in metadata['layers']]
                
                # Validate against QGIS layers
                project_layers = [layer.name().strip().lower() for layer in QgsProject.instance().mapLayers().values()]
                missing_in_project = [layer for layer in layer_names if layer.lower() not in project_layers]

                if missing_in_project:
                    QMessageBox.warning(self, "Missing Layers in QGIS", f"The following layers are missing in the project: {', '.join(missing_in_project)}")
                    self.file_input.clear()
                    return

                # Identify pending QC layers
                if 'layers_qc_completed' not in metadata:
                    metadata['layers_qc_completed'] = [
                        layer for layer in layer_names if f"{layer}.geojson" not in zip_ref.namelist()
                    ]
                    if set(metadata['layers_qc_completed']) == set(layer_names):
                        metadata["qc_status"] = "verified"

                layers_qc_pending = [layer for layer in layer_names if layer not in metadata['layers_qc_completed']]

                # Update metadata.json
                with open(metadata_path, "w", encoding="utf-8") as metadata_file:
                    json.dump(metadata, metadata_file, indent=4)

            # Create a new .amrut file with updated metadata
            temp_amrut_path = file_path + ".tmp"
            with zipfile.ZipFile(temp_amrut_path, 'w') as new_zip:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        temp_file_path = os.path.join(root, file)
                        arcname = os.path.relpath(temp_file_path, temp_dir)
                        new_zip.write(temp_file_path, arcname)

            # Replace the original .amrut file with the updated one
            os.replace(temp_amrut_path, file_path)

            # Extract bounds from metadata
            self.metadata_bounds = {key: metadata[key] for key in ["north", "south", "east", "west"] if key in metadata}

            self.file_input.setText(file_path)
            if layers_qc_pending:
                self.layer_dropdown.addItems(layers_qc_pending)
            else:
                QMessageBox.information(self, "All Layers Verified", "All layers of this file have been verified.")
                self.file_input.clear()
                
        except Exception as e:
            QgsMessageLog.logMessage(f"Error in validate_amrut_file: {str(e)}", 'AMRUT', Qgis.Critical)
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")

        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


    def proceed_quality_check(self):
        """Proceed with the quality check process for the selected layer"""
        try:
            selected_layer_name = self.layer_dropdown.currentText()

            # Ensure a valid layer is selected
            if selected_layer_name == "Select any layer for Quality Check" or not selected_layer_name:
                QMessageBox.warning(self, "No Layer Selected", "Please select a valid layer for quality check.")
                return

            # Create grid extent from metadata bounds
            grid_extent = QgsRectangle(
                self.metadata_bounds['west'],
                self.metadata_bounds['south'],
                self.metadata_bounds['east'],
                self.metadata_bounds['north']
            )

            # Check if a raster layer is selected
            selected_raster_layer_name = self.raster_layer_dropdown.currentText()
            if selected_raster_layer_name != "Select a Raster Layer":
                # Find the selected raster layer
                raster_layer = next(
                    (layer for layer in QgsProject.instance().mapLayers().values()
                     if layer.name() == selected_raster_layer_name and layer.type() == QgsMapLayer.RasterLayer),
                    None
                )

                if not raster_layer:
                    QMessageBox.warning(self, "Raster Layer Not Found", "The selected raster layer could not be found.")
                    return

                # Get raster extent in its original CRS (EPSG:32644)
                extent = raster_layer.extent()
                raster_bounds = {
                    "north": extent.yMaximum(),
                    "south": extent.yMinimum(),
                    "east": extent.xMaximum(),
                    "west": extent.xMinimum()
                }

                # Transform raster bounds to WGS 84
                raster_crs = QgsCoordinateReferenceSystem("EPSG:32644")
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                coord_transform_raster_to_wgs84 = QgsCoordinateTransform(raster_crs, wgs84, QgsProject.instance())

                transformed_northwest = coord_transform_raster_to_wgs84.transform(raster_bounds["west"], raster_bounds["north"])
                transformed_southeast = coord_transform_raster_to_wgs84.transform(raster_bounds["east"], raster_bounds["south"])

                transformed_raster_extent = QgsRectangle(
                    transformed_northwest.x(), 
                    transformed_southeast.y(),
                    transformed_southeast.x(), 
                    transformed_northwest.y()
                )

                # Check if raster extent covers the vector extent
                if not (transformed_raster_extent.contains(grid_extent)):
                    QMessageBox.warning(self, "Extent Validation Failed", "The grid's extent does not fall within the raster layer's extent.")
                    return
            else:
                selected_raster_layer_name = None

            # Open the Quality Check Visualization Dialog
            qualityCheckVisualizationDialog = qc.QualityCheckVisualizationDialog(
                self,
                selected_layer_name=selected_layer_name,
                amrut_file_path=self.file_input.text(),
                selected_raster_layer_name=selected_raster_layer_name,
                grid_extent=grid_extent
            )

            qualityCheckVisualizationDialog.exec_()

            self.validate_amrut_file(self.selected_file)

        except Exception as e:
            QgsMessageLog.logMessage(f"Error in proceed_quality_check: {str(e)}", 'AMRUT', Qgis.Critical)
