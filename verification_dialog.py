from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QMessageBox, QLineEdit, QTextEdit
from PyQt5.QtCore import Qt, QVariant
from qgis.core import QgsProject, QgsRectangle, QgsGeometry, QgsMessageLog, QgsCoordinateTransform, Qgis, QgsWkbTypes, QgsVectorFileWriter, edit, QgsFeature, QgsCoordinateTransformContext
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from PyQt5.QtGui import QColor, QFont, QTextOption
from math import cos, radians
import zipfile
import os
import tempfile
import shutil
import json
import random

class VerificationDialog:
    def __init__(self, selected_layer_name, selected_raster_layer_name, amrut_file_path, grid_extent):
        # Fetch the layer based on its name
        self.selected_layer_name = selected_layer_name
        self.selected_layer = self.get_layer_by_name(self.selected_layer_name)
        self.selected_raster_layer = self.get_layer_by_name(f"Temporary_{selected_raster_layer_name}")
        self.temporary_layer = self.get_layer_by_name(f"Temporary_{selected_layer_name}")

        self.amrut_file_path = amrut_file_path
        self.grid_extent = grid_extent
        self.new_features_checked = False
        self.deleted_features_checked = False
        self.is_feature_merged = False
        self.removed_features = set()
        self.merged_ids = []
        self.resurvey = []

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

    def check_for_deleted_features(self):
        """
        Check for features in the temporary layer that have the 'delete' attribute set to True.
        Only consider the attribute if it exists in the feature's fields.
        """
        if self.temporary_layer:
            deleted_feature_ids = set()

            for feature in self.temporary_layer.getFeatures():
                # Check if 'delete' attribute exists in the feature
                if 'delete' in feature.fields().names():
                    delete_value = feature.attribute('delete')
                    if delete_value is True:
                        feature_id = feature.attribute('feature_id')
                        if feature_id is not None:
                            deleted_feature_ids.add(feature_id)

            self.show_new_features_dialog(deleted_feature_ids, "Deleted Features")

    def check_for_geom_changes(self):
        grid_inward_buffer = self.create_inward_buffer(self.grid_extent)
        if self.selected_layer and self.temporary_layer:
            changed_geometry_features = set()  # Set to store feature IDs with geometry changes
            removed_features = set()  # Set to store feature IDs of removed features

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
                else:
                    removed_features.add(feature_id)

            # Store the changed geometry feature IDs for further processing
            self.changed_geometry_features = changed_geometry_features
            self.removed_features = removed_features
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
                proceed_button.clicked.connect(lambda: self.close_dialog_and_execute(dialog, self.check_for_deleted_features))
            elif(self.deleted_features_checked == False):
                self.deleted_features_checked = True
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
        right_canvas_frame = self.create_canvas_frame("Vetted Data", self.temporary_layer,show_cross=self.new_features_checked and not self.deleted_features_checked)
        canvas_layout.addWidget(right_canvas_frame)  # Add the right canvas to the layout
        main_layout.addLayout(canvas_layout)  # Add the canvas layout to the main layout

        # Add buttons for accepting or rejecting features
        button_layout = QHBoxLayout()
        button_layout.setSpacing(25) 
        reject_button = QPushButton("Reject Vetted Feature") 
        accept_button = QPushButton("Accept Vetted Feature")
        resurvey_button = QPushButton("Resurvey Area")
        # Modify the width of the buttons
        accept_button.setFixedWidth(120)  # Set a fixed width for the accept button
        reject_button.setFixedWidth(120)  # Set a fixed width for the reject button

        # Modify the color of the buttons
        accept_button.setStyleSheet("background-color: green; color: white;")
        reject_button.setStyleSheet("background-color: red; color: white;")
        resurvey_button.setStyleSheet("background-color: orange; color: white;")
        accept_button.setCursor(Qt.PointingHandCursor)
        reject_button.setCursor(Qt.PointingHandCursor)
        resurvey_button.setCursor(Qt.PointingHandCursor)
        if((self.new_features_checked and self.deleted_features_checked) or (not self.new_features_checked and not self.deleted_features_checked)):
            button_layout.addWidget(reject_button)  # Add the reject button to the layout
        button_layout.addWidget(accept_button)  # Add the accept button to the layout
        button_layout.addWidget(resurvey_button) # Add the resurvey button to the layout
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

        accept_button.clicked.connect(lambda: self.accept_feature(feature_ids))
        reject_button.clicked.connect(lambda: self.reject_feature(feature_ids))
        resurvey_button.clicked.connect(lambda: self.resurvey_feature(feature_ids))

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

    def create_canvas_frame(self, label_text, layer, show_cross=False):
        """Create a frame with a label and a map canvas."""
        frame = QFrame()
        frame_layout = QVBoxLayout(frame)

        label = QLabel(label_text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 12px; font-weight: bold;")
        frame_layout.addWidget(label)

        canvas = QgsMapCanvas()
        self.set_colour_opacity(self.temporary_layer, 0.6)
        self.set_colour_opacity(self.selected_layer, 0.6)
        canvas.setLayers([layer, self.selected_raster_layer])
        canvas.setCanvasColor(QColor("white"))
        canvas.setMapTool(QgsMapToolPan(canvas))

        canvas_container = QFrame()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(canvas)

        if show_cross:
            cross_label = QLabel("✖")
            cross_label.setAlignment(Qt.AlignCenter)
            cross_label.setStyleSheet("color: red; font-size: 80px;")  # Slightly smaller and cleaner
            cross_label.setFont(QFont("Arial", 80, QFont.Normal))  # Use Normal instead of Bold
            cross_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            cross_label.setParent(canvas)
            cross_label.resize(canvas.size())
            cross_label.show()

            # Resize cross with canvas
            original_resize_event = canvas.resizeEvent

            def on_resize(event):
                cross_label.resize(canvas.size())
                if original_resize_event:
                    original_resize_event(event)

            canvas.resizeEvent = on_resize

        frame_layout.addWidget(canvas_container)
        return frame

    def update_canvases(self, feature_ids):
        """
        Update canvases to focus on all features with the same feature_id.
        Zooms both canvases to the bounding box of all features being verified.
        """
        if self.current_feature_index < len(feature_ids):  # Check if there are remaining features
            feature_id = int(list(feature_ids)[self.current_feature_index])  # Get the current feature ID
            features = [f for f in self.temporary_layer.getFeatures(f"feature_id = {feature_id}")]  # Fetch all features with the same feature_id

            if features:
                if self.new_features_checked and len(features) == 1:
                    merged_feature = features[0]  # The new merged feature

                    merged_ids = []

                    # Get original feature IDs from removed_features that were merged
                    for old_id in self.removed_features:
                        old_feature = next(self.selected_layer.getFeatures(f"feature_id = {old_id}"), None)
                        
                        if old_feature:
                            old_geom = old_feature.geometry()
                            new_geom = merged_feature.geometry()

                            # Step 1: Check if the old feature is fully within the new feature
                            if new_geom.intersects(old_geom):
                                # Step 2: Compute the difference and ensure the old feature is fully merged
                                difference = old_geom.difference(new_geom)
                                if difference.isEmpty():
                                    merged_ids.append(old_id)

                    if len(merged_ids) > 0 :
                        self.merged_ids = merged_ids
                        self.is_feature_merged = True

                # Compute a bounding box that includes all matching features
                bbox = None
                for feature in features:
                    geom = feature.geometry()
                    
                    if bbox is None:
                        bbox = geom.boundingBox()
                    else:
                        bbox.combineExtentWith(geom.boundingBox())

                # Ensure valid bounding box (for single points, use a small default box)
                if bbox is None or (bbox.width() == 0 and bbox.height() == 0):
                    centroid = features[0].geometry().centroid().asPoint()
                    buffer = self.calculate_dynamic_buffer(features[0].geometry())
                    extent = QgsRectangle(
                        centroid.x() - buffer,
                        centroid.y() - buffer,
                        centroid.x() + buffer,
                        centroid.y() + buffer
                    )
                else:
                    # Apply a buffer for better visibility
                    buffer = self.calculate_dynamic_buffer(QgsGeometry.fromRect(bbox))
                    extent = QgsRectangle(
                        bbox.xMinimum() - buffer,
                        bbox.yMinimum() - buffer,
                        bbox.xMaximum() + buffer,
                        bbox.yMaximum() + buffer
                    )

                # Zoom both canvases to the combined bounding box
                if self.is_feature_merged:
                    self.zoom_to_merged_features_on_canvas(extent, self.left_canvas, self.selected_layer, feature_id)
                else:
                    self.zoom_to_feature_on_canvas(extent, self.left_canvas, self.selected_layer, feature_id)
                self.zoom_to_feature_on_canvas(extent, self.right_canvas, self.temporary_layer, feature_id)

    def zoom_to_merged_features_on_canvas(self, extent, canvas, layer, feature_id):
        """Zoom to the bounding box of all features with the same feature_id."""
        if layer:
            # Combine feature_id with merged_ids
            all_feature_ids = set(self.merged_ids)  # Convert to set to avoid duplicates
            all_feature_ids.add(feature_id)    # Ensure the original feature_id is included

            # Convert to SQL-friendly format
            feature_ids_str = ", ".join(map(str, all_feature_ids))
            layer.setSubsetString(f"feature_id IN ({feature_ids_str})")  # Filter layer to show all matching features
        canvas.setExtent(extent)
        canvas.refresh()

    def zoom_to_feature_on_canvas(self, extent, canvas, layer, feature_id):
        """Zoom to the bounding box of all features with the same feature_id."""
        if layer:
            layer.setSubsetString(f"feature_id = {feature_id}")  # Filter layer to show all matching features
        canvas.setExtent(extent)
        canvas.refresh()

    def accept_feature(self, feature_ids):
        feature_id = int(list(feature_ids)[self.current_feature_index])  # Get the current feature ID
        features = [f for f in self.temporary_layer.getFeatures(f"feature_id = {feature_id}")]  # Fetch all matching features

        if len(features) > 1:
            self.temporary_layer.startEditing()  # Start editing the layer
            
            # Keep the first feature's ID unchanged
            remaining_features = features[1:]  # Other features

            for feature in remaining_features:
                new_feature_id = random.randint(100001, 999999999)  # Increased limit for feature ID
                feature.setAttribute("feature_id", new_feature_id)  # Update the feature ID
                self.temporary_layer.updateFeature(feature)  # Apply the change
            
            self.temporary_layer.commitChanges()  # Save changes

        # Delete the feature if condition is met
        if self.new_features_checked and not self.deleted_features_checked:
            self.temporary_layer.startEditing()
            ids_to_delete = [f.id() for f in self.temporary_layer.getFeatures(f"feature_id = {feature_id}")]
            self.temporary_layer.deleteFeatures(ids_to_delete)
            self.temporary_layer.commitChanges()

        self.move_to_next_feature(feature_ids)  # Move to the next feature

    def reject_feature(self, feature_ids):
        """
        Handle rejecting the current feature.
        Deletes the feature from the temporary layer(layer from .amrut file) and moves to the next feature.
        """
        feature_id = int(list(feature_ids)[self.current_feature_index])  # Get the current feature ID
        features = [f for f in self.temporary_layer.getFeatures(f"feature_id = {feature_id}")]  # Fetch all matching features
        if features:
            self.temporary_layer.startEditing()  # Start editing the temporary layer
            
            for feature in features:
                self.temporary_layer.deleteFeature(feature.id())  # Delete each feature

            if self.new_features_checked:
                if self.is_feature_merged:
                    # Restore both feature_id and all merged features from removed_features
                    feature_ids_to_restore = {feature_id} | set(self.merged_ids)  # Combine into a set to avoid duplicates

                    for fid in feature_ids_to_restore:
                        selected_feature = next(self.selected_layer.getFeatures(f"feature_id = {fid}"), None)
                        if selected_feature:
                            # Get the attributes and geometry
                            selected_geometry = selected_feature.geometry()

                            # Create a new feature for the temporary layer
                            temp_feature = QgsFeature()
                            temp_feature.setGeometry(selected_geometry)

                            # Get fields from the temporary layer
                            temp_layer_fields = self.temporary_layer.fields()
                            primary_key_fields = self.temporary_layer.primaryKeyAttributes()  # Get primary key(s)

                            # Get the selected feature's attributes
                            selected_fields = selected_feature.fields()

                            # Prepare final attributes (excluding primary key)
                            final_attributes = []

                            for field in temp_layer_fields:
                                field_name = field.name()

                                # Skip primary key fields
                                if field_name in primary_key_fields:
                                    continue

                                # Assign value or set NULL
                                if field_name in selected_fields.names():
                                    value = selected_feature[field_name]
                                    final_attributes.append(value if value is not None else QVariant())  # QGIS treats QVariant() as NULL
                                else:
                                    final_attributes.append(QVariant())  # Missing fields set to NULL

                            # Set attributes
                            temp_feature.setAttributes(final_attributes)

                            self.temporary_layer.addFeature(temp_feature)
                else:
                    # Copy the feature from selected layer having the same feature_id to temporary layer
                    selected_feature = next(self.selected_layer.getFeatures(f"feature_id = {feature_id}"), None)
                    if selected_feature:
                        # Get the attributes from the selected feature and create a new feature for the temporary layer
                        selected_geometry = selected_feature.geometry()

                        # Create a new feature with the selected attributes and geometry
                        temp_feature = QgsFeature()
                        temp_feature.setGeometry(selected_geometry)
                        
                        # Get fields from the temporary layer
                        temp_layer_fields = self.temporary_layer.fields()
                        primary_key_fields = self.temporary_layer.primaryKeyAttributes()  # Get primary key(s)

                        # Get the selected feature's attributes
                        selected_feature = features[0]
                        selected_fields = selected_feature.fields()

                        # Prepare final attributes (excluding primary key)
                        final_attributes = []

                        for field in temp_layer_fields:
                            field_name = field.name()

                            # Skip primary key fields
                            if field_name in primary_key_fields:
                                continue

                            # Assign value or set NULL
                            if field_name in selected_fields.names():
                                value = selected_feature[field_name]
                                final_attributes.append(value if value is not None else QVariant())  # QGIS treats QVariant() as NULL
                            else:
                                final_attributes.append(QVariant())  # Missing fields set to NULL

                        # Set attributes
                        temp_feature.setAttributes(final_attributes)

                        self.temporary_layer.addFeature(temp_feature)

        self.temporary_layer.commitChanges()  # Save the changes
        self.move_to_next_feature(feature_ids)  # Move to the next feature in the list

    def resurvey_feature(self, feature_ids):
        feature_id = int(list(feature_ids)[self.current_feature_index])  # Get the current feature ID
        features = [f for f in self.temporary_layer.getFeatures(f"feature_id = {feature_id}")]  # Fetch all matching features
        
        if features:
            feature = features[0]
            geometry = feature.geometry()
            centroid = geometry.pointOnSurface()  # or .centroid()
            coordinate_value = centroid.asPoint()

            # Convert the centroid to a string or tuple of coordinates (x, y)
            coordinate_value = (coordinate_value.y(), coordinate_value.x())

        # Create the resurvey dialog
        resurvey_dialog = QDialog(self.dialog)
        resurvey_dialog.setWindowTitle("Resurvey Area - Add Reason")
        resurvey_dialog.setMinimumSize(400, 100)

        layout = QVBoxLayout(resurvey_dialog)

        label = QLabel("Please enter a reason for resurveying this area:")
        layout.addWidget(label)

        # Create the QTextEdit and the countdown label
        reason_input = QTextEdit()
        reason_input.setFixedHeight(70)
        reason_input.setFixedWidth(400)
        reason_input.setWordWrapMode(True)

        char_limit = 100
        char_count_label = QLabel(f"{char_limit} / {char_limit}")
        char_count_label.setAlignment(Qt.AlignRight)

        # Update countdown on text change
        def on_text_changed():
            text = reason_input.toPlainText()
            if len(text) > char_limit:
                reason_input.blockSignals(True)
                reason_input.setPlainText(text[:char_limit])  # Trim extra characters
                reason_input.moveCursor(reason_input.textCursor().End)  # Move cursor to end
                reason_input.blockSignals(False)
            remaining = char_limit - len(reason_input.toPlainText())
            char_count_label.setText(f"{remaining} / {char_limit}")

        reason_input.textChanged.connect(on_text_changed)

        # Add both to layout
        layout.addWidget(reason_input)
        layout.addWidget(char_count_label)

        send_button = QPushButton("Send to Resurvey")
        send_button.setEnabled(False)  # Initially disabled
        layout.addWidget(send_button)

        # Enable button only if there is some input
        def on_text_changed():
            send_button.setEnabled(bool(reason_input.toPlainText().strip()))

        # The textChanged signal provides a text argument, so we modify the function to accept it.
        reason_input.textChanged.connect(on_text_changed)

        def on_send_clicked():
            resurvey_message = reason_input.toPlainText().strip()  # Store message in instance variable
            # Create a dictionary with the required key-value pairs
            resurvey_obj = {
                "message": resurvey_message,
                "layer": self.selected_layer_name,
                "coordinate": coordinate_value
            }
            # Convert the dictionary to a JSON string
            self.resurvey.append(resurvey_obj)
            resurvey_dialog.accept()  # Close the dialog
            self.move_to_next_feature(feature_ids)  # Move to the next feature in the list

        send_button.clicked.connect(on_send_clicked)

        resurvey_dialog.exec_()

    def move_to_next_feature(self, feature_ids):
        """
        Move to the next feature in the list.
        If no more features remain, close the dialog.
        """
        self.is_feature_merged = False
        self.merged_ids = []
        self.selected_layer.setSubsetString("")  # Reset the filter to show all features
        self.temporary_layer.setSubsetString("")
        self.current_feature_index += 1  # Increment the feature index
        if self.current_feature_index < len(feature_ids):  # Check if there are more features
            self.update_canvases(feature_ids)  # Update canvases to display the next feature
        else:
            self.dialog.close()  # Close the verification dialog
            if(self.new_features_checked == False) :
                self.new_features_checked = True
                self.check_for_deleted_features()
            elif(self.deleted_features_checked == False) :
                self.deleted_features_checked = True
                self.check_for_geom_changes()
            else:
                self.set_colour_opacity(self.temporary_layer, 1)  # Reset the opacity 
                self.set_colour_opacity(self.selected_layer, 1)
                self.removed_features = set()
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
        has_resurvey_data = bool(getattr(self, "resurvey", []))
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
                if has_resurvey_data:
                    # Check if 'resurvey' key exists and is a list
                    if "resurvey" in metadata and isinstance(metadata["resurvey"], list):
                        metadata["resurvey"].extend(self.resurvey)
                    else:
                        metadata["resurvey"] = list(self.resurvey)

                else: 
                    if qc_status != None:
                        metadata["qc_status"] = qc_status  # Update QC status

                if "resurvey" in metadata and len(metadata["resurvey"]) > 0 and set(metadata['layers_qc_completed']) == set(layer_names):
                    print(f"Layers : {layer_names}")
                    print(f"QC_Completed : {metadata['layers_qc_completed']}")
                    metadata.pop("qc_status", None)
                    metadata.pop("layers_qc_completed", None)
                
                json.dump(metadata, metadata_file, indent=4)

            # Create a new .amrut file with the updated GeoJSON and metadata
            temp_amrut_path = self.amrut_file_path + ".tmp"
            with zipfile.ZipFile(temp_amrut_path, 'w') as zip_ref:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zip_ref.write(file_path, arcname)

            # Rename output if resurvey data is present
            if "resurvey" in metadata and len(metadata["resurvey"]) > 0 and "layers_qc_completed" not in metadata and "qc_status" not in metadata:
                directory = os.path.dirname(self.amrut_file_path)
                original_filename = os.path.basename(self.amrut_file_path)
                new_filename = f"resurvey_required_{original_filename}"
                new_amrut_path = os.path.join(directory, new_filename)

                # Rename the original file
                os.rename(self.amrut_file_path, new_amrut_path)

                # Replace the renamed file with updated content
                os.replace(temp_amrut_path, new_amrut_path)
            else:
                # Replace original file with updated one
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

