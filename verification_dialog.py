from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QMessageBox
from PyQt5.QtCore import Qt
from qgis.core import QgsProject, QgsRectangle, QgsMessageLog, Qgis, QgsWkbTypes, QgsVectorFileWriter, QgsFeature, QgsCoordinateTransformContext
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from PyQt5.QtGui import QColor
from math import cos, radians
import zipfile
import os
import tempfile
import shutil
import json

class VerificationDialog:
    def __init__(self, selected_layer_name, selected_raster_layer_name, amrut_file_path, grid_extent):
        # Fetch the layer based on its name
        self.selected_layer = self.get_layer_by_name(selected_layer_name)
        self.selected_raster_layer = self.get_layer_by_name(f"Temporary_{selected_raster_layer_name}")
        self.temporary_layer = self.get_layer_by_name(f"Temporary_{selected_layer_name}")

        self.amrut_file_path = amrut_file_path
        self.grid_extent = grid_extent
        self.new_features_checked = False

    def check_for_new_features(self):
        """
        Compare feature IDs of the selected layer and the temporary layer to identify new features.
        If new features are found, prompt the user with a dialog.
        """
        if self.selected_layer and self.temporary_layer:
            # Collect feature IDs from the selected layer into a set
            selected_feature_ids = {f['feature_id'] for f in self.selected_layer.getFeatures()}
            self.new_feature_ids = set()  # Initialize a set to store IDs of new features

            for feature in self.temporary_layer.getFeatures():
                temp_feature_id = feature['feature_id']  # Extract feature ID from the temporary layer
                if temp_feature_id not in selected_feature_ids:  # Check if it's a new feature
                    self.new_feature_ids.add(temp_feature_id)

            self.show_new_features_dialog(self.new_feature_ids, "New Features")
    
    def check_for_geom_changes(self):
        grid_inward_buffer = self.create_inward_buffer(self.grid_extent)
        if self.selected_layer and self.temporary_layer:
            changed_geometry_features = set()  # Set to store feature IDs with geometry changes

            # Iterate over all features in the selected layer
            for selected_feature in self.selected_layer.getFeatures():
                feature_id = selected_feature['feature_id']  # Get the feature ID

                # Find the corresponding feature in the temporary layer with the same feature ID
                temp_feature = next(self.temporary_layer.getFeatures(f"feature_id = {feature_id}"), None)
                if temp_feature:
                    # Compare the geometries of the features
                    selected_geom = selected_feature.geometry()
                    temp_geom = temp_feature.geometry()

                    if selected_geom and temp_geom:
                        geometry_type = QgsWkbTypes.geometryType(selected_feature.geometry().wkbType())  # Get the geometry type

                        # Determine the buffer size based on the geometry type
                        if geometry_type == QgsWkbTypes.PointGeometry:
                            if selected_geom.distance(temp_geom) > 1:  # Check if distance > 1 meter
                                changed_geometry_features.add(feature_id)
                        elif not selected_geom.equals(temp_geom):  # For non-point geometries
                            feature_extent = temp_geom.boundingBox()  # Get the bounding box of the feature
                            if (grid_inward_buffer.xMinimum() <= feature_extent.xMinimum() and
                                grid_inward_buffer.yMinimum() <= feature_extent.yMinimum() and
                                grid_inward_buffer.xMaximum() >= feature_extent.xMaximum() and
                                grid_inward_buffer.yMaximum() >= feature_extent.yMaximum()):
                                # Add the feature ID to the set if the condition is satisfied
                                changed_geometry_features.add(feature_id)

            # Store the changed geometry feature IDs for further processing
            self.changed_geometry_features = changed_geometry_features
            self.show_new_features_dialog(self.changed_geometry_features, "Geometry Changes")


    def show_new_features_dialog(self, feature_ids, title):
        """
        Display a dialog showing the number of new features found.
        If features are found, allow the user to proceed to verification.
        """
        feature_count = len(feature_ids)  # Count the number of new features
        message = f"{feature_count} {title} found in the temporary layer."  # Prepare the message
        Window_title = f"{title} Found"
        # Create a dialog box to display the message
        dialog = QDialog(None)
        dialog.setWindowTitle(Window_title)  # Set the title of the dialog
        dialog.setMinimumSize(300, 150)  # Set minimum size for the dialog window
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowSystemMenuHint)
        layout = QVBoxLayout(dialog)  # Use a vertical layout for the dialog

        message_label = QLabel(message)
        message_label.setAlignment(Qt.AlignCenter)  # Center-align the message text
        layout.addWidget(message_label)  # Add the label to the layout
        button_layout = QHBoxLayout()
        if feature_count > 0:
            # If there are new features, add a "Proceed" button
            proceed_button = QPushButton("Proceed to Verify")  # Create the button
            button_layout.addWidget(proceed_button, alignment=Qt.AlignCenter)  # Add button to the layout
            proceed_button.setFixedWidth(150)  # Set a fixed width for the button
            layout.addLayout(button_layout)  # Add the button layout to the main layout
            proceed_button.clicked.connect(lambda: self.show_verification_dialog(dialog, feature_ids)) # Connect the button click event to open the verification dialog
        else:
            proceed_button = QPushButton("OK")  # Create the button
            button_layout.addWidget(proceed_button, alignment=Qt.AlignCenter)  # Add button to the layout
            proceed_button.setFixedWidth(75)  # Set a fixed width for the button
            layout.addLayout(button_layout)  # Add the button layout to the main layout
            if(self.new_features_checked == False):
                self.new_features_checked = True
                proceed_button.clicked.connect(lambda: self.close_dialog_and_execute(dialog, self.check_for_geom_changes))
            else:
                proceed_button.clicked.connect(lambda: self.close_dialog_and_execute(dialog, self.approve_or_reject_layer))
        dialog.exec_()  # Display the dialog

    def close_dialog_and_execute(self, dialog, function):
        dialog.close()  # Close the dialog
        function()  # Execute the given function

    def get_layer_by_name(self, layer_name):
        """Retrieve a layer by its name from the QGIS project. If layer not found return None"""
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == layer_name:
                return layer 
        return None

    def show_verification_dialog(self, parent_dialog, feature_ids):
        """Show the dialog for verifying features."""
        parent_dialog.close()  # Close the parent dialog

        # Create a new dialog for verification
        dialog = QDialog(None)
        dialog.setWindowTitle("Verify Features")  # Set the dialog title
        dialog.setMinimumSize(800, 600)  # Set minimum size for the dialog window

        # Disable the close button and system menu options
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowSystemMenuHint)

        main_layout = QVBoxLayout(dialog)
        canvas_layout = QHBoxLayout()  # Layout for map canvases
        # Add canvases for selected and temporary layers
        left_canvas_frame = self.create_canvas_frame("Original Data", self.selected_layer)
        canvas_layout.addWidget(left_canvas_frame)  # Add the left canvas to the layout
        right_canvas_frame = self.create_canvas_frame("Vetted Data", self.temporary_layer)
        canvas_layout.addWidget(right_canvas_frame)  # Add the right canvas to the layout
        main_layout.addLayout(canvas_layout)  # Add the canvas layout to the main layout

        # Add buttons for accepting or rejecting features
        button_layout = QHBoxLayout()
        button_layout.setSpacing(25) 
        reject_button = QPushButton("Reject Vetted Feature") 
        accept_button = QPushButton("Accept Vetted Feature")
        # Modify the width of the buttons
        accept_button.setFixedWidth(120)  # Set a fixed width for the accept button
        reject_button.setFixedWidth(120)  # Set a fixed width for the reject button

        # Modify the color of the buttons
        accept_button.setStyleSheet("background-color: green; color: white;")
        reject_button.setStyleSheet("background-color: red; color: white;")
        accept_button.setCursor(Qt.PointingHandCursor)
        reject_button.setCursor(Qt.PointingHandCursor)
        button_layout.addWidget(reject_button)  # Add the reject button to the layout
        button_layout.addWidget(accept_button)  # Add the accept button to the layout
        button_layout.setAlignment(Qt.AlignCenter)
        main_layout.addLayout(button_layout)  # Add the button layout to the main layout

        self.current_feature_index = 0  # Track the index of the current feature being verified
        self.dialog = dialog  # Store the dialog reference
        self.left_canvas = left_canvas_frame.findChild(QgsMapCanvas)  # Retrieve the left canvas
        self.right_canvas = right_canvas_frame.findChild(QgsMapCanvas)  # Retrieve the right canvas

        # Synchronize the views of both canvases
        self.is_synchronizing = False  # Flag to avoid recursive synchronization
        self.left_canvas.extentsChanged.connect(self.synchronize_right_canvas)
        self.right_canvas.extentsChanged.connect(self.synchronize_left_canvas)
        self.setup_panning()

        accept_button.clicked.connect(lambda: self.move_to_next_feature(feature_ids))
        reject_button.clicked.connect(lambda: self.reject_feature(feature_ids))

        # Update the canvases to focus on the first feature
        self.update_canvases(feature_ids)
        dialog.exec_()  # Display the dialog

    def synchronize_right_canvas(self):
        """Synchronize the right canvas with the left canvas."""
        if not self.is_synchronizing:  # Prevent infinite loop 
            self.is_synchronizing = True  # Mark synchronization in progress
            self.right_canvas.setExtent(self.left_canvas.extent())  # Set the extent of the right canvas to match the left canvas
            self.right_canvas.refresh()  # Refresh the right canvas to update its display
            self.is_synchronizing = False  # Reset the synchronization flag

    def synchronize_left_canvas(self):
        """Synchronize the left canvas with the right canvas."""
        if not self.is_synchronizing:  # Prevent infinite loop
            self.is_synchronizing = True  # Mark synchronization in progress
            self.left_canvas.setExtent(self.right_canvas.extent())  # Set the extent of the left canvas to match the right canvas
            self.left_canvas.refresh()  # Refresh the left canvas to update its display
            self.is_synchronizing = False  # Reset the synchronization flag

    def setup_panning(self):
        """Enable panning on both canvases."""
        try:
            if self.left_canvas and self.right_canvas:
                self.left_pan_tool = QgsMapToolPan(self.left_canvas)
                self.right_pan_tool = QgsMapToolPan(self.right_canvas)

                self.left_canvas.setMapTool(self.left_pan_tool)
                self.right_canvas.setMapTool(self.right_pan_tool)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error in setup_panning: {str(e)}", 'AMRUT', Qgis.Critical)

    def create_canvas_frame(self, label_text, layer):
        """Create a frame with a label and a map canvas."""
        frame = QFrame()  # Create a container frame
        frame_layout = QVBoxLayout(frame)  # Set a vertical layout for the frame

        label = QLabel(label_text)  # Create a label with the provided text
        label.setAlignment(Qt.AlignCenter)  # Center-align the label text
        label.setStyleSheet("font-size: 12px; font-weight: bold;")  # Set font size and bold style
        frame_layout.addWidget(label)  # Add the label to the frame layout

        canvas = QgsMapCanvas()  # Create a map canvas
        self.set_colour_opacity(self.temporary_layer, 0.6)  # Adjust the opacity for better visualization
        self.set_colour_opacity(self.selected_layer, 0.6)
        canvas.setLayers([layer, self.selected_raster_layer])
        canvas.setCanvasColor(QColor("white"))  # Set the canvas background color to white
        canvas.setMapTool(QgsMapToolPan(canvas))  # Enable panning on the canvas
        frame_layout.addWidget(canvas)  # Add the canvas to the frame layout

        return frame  # Return the completed frame

    def update_canvases(self,feature_ids):
        """
        Update canvases to focus on the current feature.
        Zooms both canvases to the bounding box of the feature being verified.
        """
        if self.current_feature_index < len(feature_ids):  # Check if there are remaining features
            feature_id = int(list(feature_ids)[self.current_feature_index])  # Get the current feature ID
            feature = next(self.temporary_layer.getFeatures(f"feature_id = {feature_id}"), None)  # Fetch the feature

            if feature:
                centroid_geom = feature.geometry().centroid()  # Calculate the centroid of the feature
                centroid_point = centroid_geom.asPoint()  # Get the centroid as a point
                buffer = self.calculate_dynamic_buffer(feature.geometry())  # Calculate a dynamic buffer size

                # Define the bounding box for the feature with the buffer
                extent = QgsRectangle(
                    centroid_point.x() - buffer,
                    centroid_point.y() - buffer,
                    centroid_point.x() + buffer,
                    centroid_point.y() + buffer
                )
                self.zoom_to_feature_on_canvas(extent, self.left_canvas,self.selected_layer,feature_id)  # Zoom the left canvas to the feature
                self.zoom_to_feature_on_canvas(extent, self.right_canvas,self.temporary_layer,feature_id)  # Zoom the right canvas to the feature
            else:
                # Log a warning if the feature cannot be found
                QgsMessageLog.logMessage(
                    f"Feature with feature_id {feature_id} not found in the .amrut file.",
                    "AMRUT",
                    Qgis.Warning
                )            

    def zoom_to_feature_on_canvas(self, extent, canvas,layer,feature_id):
        """Zoom to the feature's bounding box on the canvas."""
        if layer:
            # Apply a filter to show only the specific feature
            layer.setSubsetString(f"feature_id = {feature_id}")
        canvas.setExtent(extent)  # Set the extent of the canvas
        canvas.refresh()  # Refresh the canvas to apply the changes

    def reject_feature(self, feature_ids):
        """
        Handle rejecting the current feature.
        Deletes the feature from the temporary layer(layer from .amrut file) and moves to the next feature.
      l  """
        feature_id = int(list(feature_ids)[self.current_feature_index])  # Get the current feature ID
        feature = next(self.temporary_layer.getFeatures(f"feature_id = {feature_id}"), None)  # Fetch the feature
        selected_attributes = feature.attributes()
        self.temporary_layer.startEditing()  # Start editing the temporary layer
        self.temporary_layer.deleteFeature(feature.id())  # Delete the feature from the ayer

        if (self.new_features_checked):
            # Copy the feature from selected layer having the same feature_id to temporary layer
            selected_feature = next(self.selected_layer.getFeatures(f"feature_id = {feature_id}"), None)
            if selected_feature:
                # Get the attributes from the selected feature and create a new feature for the temporary layer
                selected_geometry = selected_feature.geometry()

                # Create a new feature with the selected attributes and geometry
                temp_feature = QgsFeature()
                temp_feature.setGeometry(selected_geometry)
                
                # Set the attributes, matching the temporary layer's attribute order
                temp_feature.setAttributes(selected_attributes)
                
                # Add the feature to the temporary layer
                self.temporary_layer.addFeature(temp_feature)
        self.temporary_layer.commitChanges()  # Save the changes
        self.move_to_next_feature(feature_ids)  # Move to the next feature in the list

    def move_to_next_feature(self, feature_ids):
        """
        Move to the next feature in the list.
        If no more features remain, close the dialog.
        """
        self.selected_layer.setSubsetString("")  # Reset the filter to show all features
        self.temporary_layer.setSubsetString("")
        self.current_feature_index += 1  # Increment the feature index
        if self.current_feature_index < len(feature_ids):  # Check if there are more features
            self.update_canvases(feature_ids)  # Update canvases to display the next feature
        else:
            self.dialog.close()  # Close the verification dialog
            if(self.new_features_checked == False):
                self.new_features_checked = True
                self.check_for_geom_changes()
            else:
                self.set_colour_opacity(self.temporary_layer, 1)  # Reset the opacity 
                self.set_colour_opacity(self.selected_layer, 1)
                self.approve_or_reject_layer()

    def set_colour_opacity(self, layer, opacity):
        """Set the opacity of the layer for visualization."""
        symbol = layer.renderer().symbol()  # Get the symbol for the layer          
        if symbol:
            symbol.setOpacity(opacity)  # Set the opacity of the symbol
        layer.triggerRepaint()  # Trigger a repaint to apply the changes

    def calculate_dynamic_buffer(self, geometry):
        """Calculate a dynamic buffer size based on the geometry type and size."""
        geometry_type = QgsWkbTypes.geometryType(geometry.wkbType())  # Get the geometry type

        # Determine the buffer size based on the geometry type
        if geometry_type == QgsWkbTypes.PointGeometry:
            buffer = 0.0001  # Small buffer for point geometries
        elif geometry_type == QgsWkbTypes.LineGeometry:
            line_length = geometry.length()  # Calculate the length of the line
            buffer = line_length * 0.25  # Use half the line length as the buffer
        elif geometry_type == QgsWkbTypes.PolygonGeometry:
            bbox = geometry.boundingBox()  # Get the bounding box of the polygon
            bbox_width = bbox.width()  # Width of the bounding box
            bbox_height = bbox.height()  # Height of the bounding box
            diagonal = (bbox_width**2 + bbox_height**2) ** 0.5  # Calculate the diagonal length
            buffer = diagonal * 0.5  # Use half the diagonal length as the buffer
        else:
            buffer = 0.0001  # Default buffer size for unsupported geometry types

        return buffer  # Return the calculated buffer size

    def create_inward_buffer(self, grid_extent):
        # Calculate the conversion factor for meters to degrees based on latitude
        avg_lat = (grid_extent.yMinimum() + grid_extent.yMaximum()) / 2
        meters_to_degrees_lat = 10 / 111320  # 1 meter in latitude degrees
        meters_to_degrees_lon = 10 / (111320 * cos(radians(avg_lat)))  # 1 meter in longitude degrees

        # Create a new extent by shrinking the grid extent inward by 1 meter
        inward_buffered_extent = QgsRectangle(
            grid_extent.xMinimum() + meters_to_degrees_lon,
            grid_extent.yMinimum() + meters_to_degrees_lat,
            grid_extent.xMaximum() - meters_to_degrees_lon,
            grid_extent.yMaximum() - meters_to_degrees_lat,
        )

        return inward_buffered_extent
    
    def approve_or_reject_layer(self):
        dialog = QDialog(None)
        dialog.setWindowTitle("Confirmation Dialog")  # Set the title of the dialog
        dialog.setMinimumSize(300, 150)  # Set minimum size for the dialog window
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowSystemMenuHint)
        layout = QVBoxLayout(dialog)  # Use a vertical layout for the dialog

        message_label = QLabel("All changes have been processed. Save the changes to AMRUT File?")
        message_label.setAlignment(Qt.AlignCenter)  # Center-align the message text
        message_label.setStyleSheet("font-size: 12px; font-weight: bold;")  # Set font size and bold style
        layout.addWidget(message_label)  # Add the label to the layout
        button_layout = QHBoxLayout()
        accept_button = QPushButton("Accept Vetted Data")
        # Modify the width of the buttons
        accept_button.setFixedWidth(120)  # Set a fixed width for the accept button

        # Modify the color of the buttons
        accept_button.setStyleSheet("background-color: green; color: black;")
        accept_button.setCursor(Qt.PointingHandCursor)
        button_layout.addWidget(accept_button)  # Add the accept button to the layout
        layout.addLayout(button_layout)  # Add the button layout to the main layout

        accept_button.clicked.connect(lambda: self.close_dialog_and_execute(dialog, self.accept_data))
        dialog.exec_()  # Display the dialog

    def accept_data(self):
        """Replace old GeoJSON file in .amrut file with new GeoJSON file and update metadata.json."""
        temp_dir = None
        try:
            geojson_filename = f"{self.selected_layer.name()}.geojson"
            geojson_name_without_ext = os.path.splitext(geojson_filename)[0]


            # Create a temporary directory for extraction
            temp_dir = tempfile.mkdtemp()


            # Extract the contents of the .amrut file to the temporary directory
            with zipfile.ZipFile(self.amrut_file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
                # Read metadata.json from the archive
                metadata = json.loads(zip_ref.read('metadata.json'))

                # Check for 'layers' array in metadata
                if 'layers' not in metadata or not isinstance(metadata['layers'], list):
                    QMessageBox.warning(self, "Invalid Metadata", "'layers' array is missing or invalid in metadata.json.")
                    self.file_input.clear()
                    return

                # Extract layer names from the 'layers' array
                layer_names = [
                    layer.split(" : ")[0].strip("{}").strip()
                    for layer in metadata['layers']
                ]

                # Ensure 'layers_qc_completed' exists in metadata
                if "layers_qc_completed" not in metadata:
                    metadata["layers_qc_completed"] = []

                # Append the current GeoJSON name to 'layers_qc_completed' if not already present
                if geojson_name_without_ext not in metadata["layers_qc_completed"]:
                    metadata["layers_qc_completed"].append(geojson_name_without_ext)

                qc_status = None
                
                # Check if all layers are in 'layers_qc_completed'
                all_verified = all(layer in metadata["layers_qc_completed"] for layer in layer_names)
                # Update the qc_status field
                if all_verified:
                    qc_status = "verified"

            # Check if the GeoJSON file exists in the archive
            geojson_file_path = os.path.join(temp_dir, geojson_filename)
            if not os.path.exists(geojson_file_path):
                raise FileNotFoundError(f"GeoJSON file '{geojson_filename}' not found in the AMRUT file.")

            # Validate the temporary layer
            if not self.temporary_layer or not self.temporary_layer.isValid():
                raise ValueError("Temporary layer is invalid.")

            # Export the temporary layer to the GeoJSON format
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GeoJSON"
            options.forceMulti = True  # Ensures consistent geometry type
            error = QgsVectorFileWriter.writeAsVectorFormatV2(
                self.temporary_layer,
                geojson_file_path,
                QgsCoordinateTransformContext(),
                options
            )
            if error[0] != QgsVectorFileWriter.NoError:
                raise ValueError(f"Failed to write the temporary layer to GeoJSON format: {error}")

            # Write the updated metadata.json back to the temporary directory
            metadata_path = os.path.join(temp_dir, "metadata.json")
            with open(metadata_path, "w") as metadata_file:
                if qc_status != None:
                    metadata["qc_status"] = qc_status  # Update QC status
                json.dump(metadata, metadata_file, indent=4)

            # Create a new .amrut file with the updated GeoJSON and metadata
            temp_amrut_path = self.amrut_file_path + ".tmp"
            with zipfile.ZipFile(temp_amrut_path, 'w') as zip_ref:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zip_ref.write(file_path, arcname)

            # Replace the original .amrut file with the updated one
            os.replace(temp_amrut_path, self.amrut_file_path)
            QgsMessageLog.logMessage(
                f"GeoJSON file '{geojson_filename}' successfully replaced in the AMRUT file. QC Status: {qc_status}",
                "AMRUT",
                Qgis.Info
            )  
        except Exception as e:
            QgsMessageLog.logMessage(f"Error replacing GeoJSON in AMRUT file: {str(e)}", "AMRUT", Qgis.Critical)
        finally:
            # Cleanup: Delete the temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

