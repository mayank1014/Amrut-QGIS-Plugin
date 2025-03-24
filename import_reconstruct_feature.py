from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QMessageBox,
    QTableWidget, QTableWidgetItem, QGroupBox, QSizePolicy, QHeaderView,
    QScrollArea, QGroupBox, QApplication, QWidget
)
from PyQt5.QtCore import Qt, QThread, QEventLoop
from PyQt5.QtGui import QPixmap, QColor
from qgis.core import (
    QgsProject, QgsRectangle, QgsMessageLog, Qgis, QgsWkbTypes, QgsFeature, QgsFeatureRequest, edit, QgsVectorLayer, QgsProcessingFeatureSourceDefinition, QgsCategorizedSymbolRenderer, QgsRenderContext, QgsSingleSymbolRenderer,
    QgsRendererCategory,
    QgsSymbol,
    QgsVectorFileWriter, 
    QgsCoordinateTransformContext
)
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from . import import_workers
import processing
import random
import base64
from osgeo import ogr

class ReconstructFeatures:
    def __init__(self, selected_layer, selected_raster_layer, data, progress_bar, progress_lable):
        self.selected_layer_for_processing = selected_layer
        self.saved_temp_layer = self.get_layer_by_name("Temporary_"+selected_layer.name())
        self.selected_raster_layer = selected_raster_layer
        self.data = data 
        self.reprojected_raster_layer = None
        self.current_feature_index = 0  # Initialize current_feature_index
        self.progress_bar = progress_bar
        self.progress_lable = progress_lable

    def apply_colour(self, layer):
        renderer = QgsCategorizedSymbolRenderer("$id", [])  # Use $id (QGIS internal unique feature ID)

        for feature in layer.getFeatures():
            unique_id = feature.id()  # Use feature ID to ensure uniqueness
            color = QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))  # Generate random color
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            if layer.geometryType() == QgsWkbTypes.LineGeometry:
                symbol.setWidth(symbol.width() * 5)  # Apply width increase again
            
            category = QgsRendererCategory(unique_id, symbol, f"Feature {unique_id}")
            renderer.addCategory(category)

        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def increase_line_width(self, layer):
        if layer.geometryType() == QgsWkbTypes.LineGeometry:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setWidth(symbol.width() * 5)  # Increase width
            
            # Apply a new renderer with the modified symbol
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()  # Refresh the layer

    def apply_colour(self, layer):
        renderer = QgsCategorizedSymbolRenderer("$id", [])  # Use $id (QGIS internal unique feature ID)

        for feature in layer.getFeatures():
            unique_id = feature.id()  # Use feature ID to ensure uniqueness
            color = QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))  # Generate random color
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            if layer.geometryType() == QgsWkbTypes.LineGeometry:
                symbol.setWidth(symbol.width() * 5)  # Apply width increase again
            
            category = QgsRendererCategory(unique_id, symbol, f"Feature {unique_id}")
            renderer.addCategory(category)

        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def increase_line_width(self, layer):
        if layer.geometryType() == QgsWkbTypes.LineGeometry:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setWidth(symbol.width() * 5)  # Increase width
            
            # Apply a new renderer with the modified symbol
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()  # Refresh the layer

    def merge_attribute_dialog(self):
        """Show the dialog for verifying features in full-screen mode."""
        dialog = QDialog(None)
        dialog.setWindowTitle("Merge Feature Attribute")
        # Set the dialog to full-screen (or maximized)
        dialog.setWindowState(Qt.WindowMaximized)

        main_layout = QVBoxLayout(dialog)  # Main vertical layout

        # Create a horizontal layout for left and right canvases (Top Section)
        top_canvas_layout = QHBoxLayout()
        self.apply_colour(self.saved_temp_layer)
        self.increase_line_width(self.selected_layer_for_processing)
        # Ensure raster transformation if needed
        self.transform_raster_CRS(self.selected_layer_for_processing, self.selected_raster_layer)

        # Create left (Original Data) and right (Vetted Data) canvases
        left_canvas_frame = self.create_canvas_frame("Original Data", self.selected_layer_for_processing)
        right_canvas_frame = self.create_canvas_frame("Vetted Data", self.saved_temp_layer)

        top_canvas_layout.addWidget(left_canvas_frame)
        top_canvas_layout.addWidget(right_canvas_frame)
        # Add the top section with a stretch factor (e.g., 1/3 of the screen)
        main_layout.addLayout(top_canvas_layout, stretch=1)

        # Create the bottom section: a frame that shows attribute tables for the broken features.
        bottom_attr_frame = self.create_attribute_tables_frame()
        # Add the bottom section with a higher stretch factor (e.g., 2/3 of the screen)
        main_layout.addWidget(bottom_attr_frame, stretch=2)

        self.current_feature_index = 0
        self.dialog = dialog
        self.left_canvas = left_canvas_frame.findChild(QgsMapCanvas)
        self.right_canvas = right_canvas_frame.findChild(QgsMapCanvas)
        # No canvas is created in the bottom section, so we do not assign self.bottom_canvas

        # Synchronize the views of both canvases
        self.is_synchronizing = False  # Flag to avoid recursive synchronization
        self.left_canvas.extentsChanged.connect(self.synchronize_right_canvas)
        self.right_canvas.extentsChanged.connect(self.synchronize_left_canvas)
        self.setup_panning()

        self.update_canvases()
        dialog.exec_()

    def transform_raster_CRS(self, layer, raster_layer):
        """ Initiate raster transformation with a blocking progress bar """
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.progress_bar.show()
        if raster_layer:
            reprojected_raster_layer_name = "Temporary_"+raster_layer.name()
            print(reprojected_raster_layer_name)
            self.reprojected_raster_layer = self.get_layer_by_name(reprojected_raster_layer_name)

        if not raster_layer or self.reprojected_raster_layer:
            self.progress_bar.setRange(0, 100)  # Reset progress range
            self.progress_bar.setValue(100)
            self.progress_lable.setText("")
            self.progress_bar.setVisible(False)
            return  # Skip if no raster or already transformed

        # Show progress bar (indeterminate state)
        self.progress_bar.show()
        QApplication.processEvents()

        self.worker = import_workers.RasterTransformWorker(layer, raster_layer)
        self.thread = QThread()

        # Move worker to thread
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.progress_signal.connect(self.progress_bar.setValue)

        event_loop = QEventLoop()  # Create an event loop to block execution

        def on_transformation_finished(raster_layer):
            """ Handle raster transformation completion """
            self.reprojected_raster_layer = raster_layer
            if raster_layer:
                QgsProject.instance().addMapLayer(self.reprojected_raster_layer)
            else:
                QMessageBox.warning(None, "Error", "Raster transformation failed.")

            self.progress_bar.setRange(0, 100)  # Reset progress range
            self.progress_bar.setValue(100)
            self.progress_lable.setText("")
            self.progress_bar.setVisible(False)
            event_loop.quit()  # Exit event loop, allowing execution to continue

        # Connect the finished signal to event loop quit
        self.worker.finished_signal.connect(on_transformation_finished)
        self.worker.finished_signal.connect(self.thread.quit)
        self.worker.finished_signal.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # Start thread
        self.thread.start()

        # Block execution until transformation is complete
        event_loop.exec_()

    def create_attribute_tables_frame(self):
        """
        Create a QFrame that displays attribute tables (horizontally)
        for all the broken features in the current feature entry.
        """
        container = QFrame()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        if self.current_feature_index < len(self.data):
            feature_id = list(self.data.keys())[self.current_feature_index]
            broken_features = self.data[feature_id]

            if broken_features:
                # Create a list to store the tables for synchronization
                tables = []

                for idx, broken_feature in enumerate(broken_features, start=1):
                    group_box = QGroupBox(f"Broken Feature {idx}")
                    group_layout = QVBoxLayout(group_box)

                    table = QTableWidget()
                    table.setWordWrap(True)
                    table.resizeColumnsToContents()
                    table.resizeRowsToContents()
                    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
                    table.horizontalHeader().setStretchLastSection(True)
                    table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

                    if isinstance(broken_feature, QgsFeature):
                        fields = broken_feature.fields()
                        num_fields = len(fields)
                        table.setColumnCount(2)
                        table.setRowCount(num_fields)
                        table.setHorizontalHeaderLabels(["Attribute", "Value"])

                        for row in range(num_fields):
                            field_name = fields.at(row).name()
                            value = broken_feature.attribute(field_name)

                            table.setItem(row, 0, QTableWidgetItem(field_name))

                            # Check if the field is "Photo" or "photo"
                            if field_name.lower() == "photo" and value:
                                button = QPushButton("View Photo")
                                button.setFixedSize(120, 25)  # Set the button size
                                button.clicked.connect(lambda _, v=value: self.show_photo_dialog(v))
                                
                                # Create a widget for padding inside the cell
                                button_container = QWidget()
                                button_layout = QHBoxLayout(button_container)
                                button_layout.setContentsMargins(5, 0, 0, 0)  # Add horizontal padding
                                button_layout.addWidget(button)
                                button_layout.setAlignment(Qt.AlignLeft)  # Align to the left

                                table.setCellWidget(row, 1, button_container)

                                # Adjust row height to fit button size
                                table.setRowHeight(row, 35)  # Adjust the height to fit button
                            else:
                                table.setItem(row, 1, QTableWidgetItem(str(value)))
                    else:
                        table.setColumnCount(1)
                        table.setRowCount(1)
                        table.setHorizontalHeaderLabels(["Value"])
                        table.setItem(0, 0, QTableWidgetItem(str(broken_feature)))

                    group_layout.addWidget(table)
                    accept_button = QPushButton("Accept")
                    accept_button.clicked.connect(lambda checked, bf=broken_feature: self.accept_and_next_feature(bf))
                    group_layout.addWidget(accept_button)

                    layout.addWidget(group_box)

                    # Add the table to the tables list for synchronization
                    tables.append(table)

                # Synchronize the scrolls
                def sync_scrolls(value):
                    for table in tables:
                        table.verticalScrollBar().setValue(value)

                # Connect each table's vertical scroll bar to synchronize all others
                for table in tables:
                    table.verticalScrollBar().valueChanged.connect(lambda value, table=table: sync_scrolls(value))

            else:
                layout.addWidget(QLabel("No broken features available."))
        else:
            layout.addWidget(QLabel("All features reviewed."))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(container)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        return scroll_area

    def show_photo_dialog(self, base64_string):
        """Decode the base64 image and display it in a dynamically sized popup dialog."""
        try:
            # Decode the base64 string
            image_data = base64.b64decode(base64_string)
            
            # Convert to QPixmap
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_data):
                raise ValueError("Failed to load image data")

            # Get original image size
            img_width = pixmap.width()
            img_height = pixmap.height()

            # Define max and preferred sizes
            max_width = 9000
            max_height = 700
            min_width = 600  # Ensure it's not too small
            min_height = 500

            # Compute new size while preserving aspect ratio
            aspect_ratio = img_width / img_height

            if img_width > max_width or img_height > max_height:
                # Scale down while preserving aspect ratio
                if aspect_ratio > 1:
                    scaled_width = max_width
                    scaled_height = int(max_width / aspect_ratio)
                else:
                    scaled_height = max_height
                    scaled_width = int(max_height * aspect_ratio)
            else:
                # Scale up smaller images while maintaining minimums
                scaled_width = max(min_width, img_width)
                scaled_height = max(min_height, img_height)

            # Resize pixmap to ensure it appears larger
            pixmap = pixmap.scaled(scaled_width, scaled_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Create dialog
            dialog = QDialog()
            dialog.setWindowTitle("Photo Preview")
            dialog.resize(scaled_width, scaled_height)  # Set dynamic size

            # Create layout and label
            layout = QVBoxLayout(dialog)
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)

            layout.addWidget(label)
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to load image: {str(e)}")
    

    def accept_and_next_feature(self, accepted_feature):
        """
        Store the accepted feature separately and move to the next feature.
        Updates features in saved_temp_layer based on feature_id, excluding primary keys.
        """
        self.selected_layer_for_processing.setSubsetString("")  # Reset the filter to show all features
        self.saved_temp_layer.setSubsetString("")
        if not self.data or self.current_feature_index >= len(self.data):
            QMessageBox.information(None, "Review Complete", "All features have been reviewed.")
            self.dialog.accept()
            return

        print(f"Accepted Feature (ID: {accepted_feature.id()}):")

        if self.saved_temp_layer is not None:
            # Get primary key attribute indices
            primary_key_indices = self.saved_temp_layer.primaryKeyAttributes()
            print(f"Primary key indices are : {primary_key_indices}")

            # Identify the feature_id field name and value from the accepted feature
            # Assuming 'feature_id' is a field in your layer. Adjust if different.
            feature_id_field_name = 'feature_id'  # Replace with the actual field name
            accepted_feature_id = accepted_feature[feature_id_field_name]

            # Prepare attribute map for updating existing features
            attributes = {}
            fields = accepted_feature.fields() # gets the fields of accepted_feature
            for field in fields: # looping in all the fields
                field_index = fields.indexOf(field.name()) # get field index to check if it is a primary key
                if field_index not in primary_key_indices: # if field is not a primary key
                    attributes[field.name()] = accepted_feature[field.name()] # append attribute value to update in layer

            # Update features in saved_temp_layer
            with edit(self.saved_temp_layer):
                request = QgsFeatureRequest()
                request.setFilterExpression(f'"{feature_id_field_name}" = \'{accepted_feature_id}\'')
                for feat in self.saved_temp_layer.getFeatures(request):
                    # Update attributes
                    for key, value in attributes.items():
                        feat[key] = value
                    self.saved_temp_layer.updateFeature(feat)

            print(f"Updated features in saved_temp_layer with {feature_id_field_name} = {accepted_feature_id}")
        else:
            print("saved_temp_layer is None. Layer might not be initialized yet.")

        # Move to the next feature
        self.current_feature_index += 1
        if self.current_feature_index < len(self.data):
            new_attr_frame = self.create_attribute_tables_frame()
            self.dialog.layout().replaceWidget(self.dialog.layout().itemAt(1).widget(), new_attr_frame)
            self.update_canvases()
        else:
            QMessageBox.information(None, "Review Complete", "All features have been reviewed.")

            merged_layer = self.merge_features_by_attribute(self.saved_temp_layer, "feature_id")

            if self.saved_temp_layer is not None:
                original_path = self.saved_temp_layer.dataProvider().dataSourceUri().split("|")[0]  
                print(f"Original file path of saved_temp_layer: {original_path}")

                layer_name = self.saved_temp_layer.name()

                if layer_name.startswith("Temporary_"):
                    layer_name = layer_name[len("Temporary_"):]

                new_layer_name = layer_name + "_vetted"
                project = QgsProject.instance()
                root = project.layerTreeRoot()
                layer_node = root.findLayer(self.saved_temp_layer.id())

                if layer_node is not None:
                    layer_node.setName(new_layer_name)
                    print(f"Layer renamed in project to: {new_layer_name}")
                else:
                    print("Layer node not found in layer tree.")

                if merged_layer is not None and merged_layer.isValid():
                    # Get the file path of the existing saved layer
                    temp_layer_path = self.saved_temp_layer.source()  

                    # Remove the old layer from the project
                    QgsProject.instance().removeMapLayer(self.saved_temp_layer.id())

                    # Save merged_layer to the same file location (overwriting)
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.driverName = "GPKG"
                    options.fileEncoding = "UTF-8"
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
                    QgsVectorFileWriter.writeAsVectorFormatV2(merged_layer, temp_layer_path, QgsCoordinateTransformContext(), options)

                    # Reload the updated layer
                    new_layer = QgsVectorLayer(temp_layer_path, new_layer_name, "ogr")

                    if new_layer.isValid():
                        QgsProject.instance().addMapLayer(new_layer)
                        self.saved_temp_layer = new_layer  # Update reference
                    else:
                        print("Error: Failed to reload the updated layer.")
                else:
                    self.saved_temp_layer.setName(new_layer_name)
                    print("Merged layer is invalid. Only renaming existing layer.")      

                self.saved_temp_layer.setName(new_layer_name)
                self.saved_temp_layer.setSubsetString("")
            else:
                print("saved_temp_layer is None, cannot rename.")

            self.dialog.accept()
            
    def merge_features_by_attribute(self, input_layer, attribute):
        """
        Merges features in a given layer based on a common attribute using QGIS's Dissolve algorithm.
        :param input_layer: The input vector layer (QgsVectorLayer)
        :param attribute: The attribute name to dissolve by (string)
        :return: The output layer containing merged features
        """
        print(input_layer)
        if not input_layer or not isinstance(input_layer, QgsVectorLayer):
            print("Invalid input layer")
            return None
        
        # Define the parameters for the dissolve algorithm
        params = {
            'INPUT': QgsProcessingFeatureSourceDefinition(input_layer.source(), selectedFeaturesOnly=False),
            'FIELD': [attribute],  # Field to dissolve by
            'OUTPUT': 'memory:'  # Output to a temporary memory layer
        }

        # Run the dissolve algorithm
        result = processing.run("native:dissolve", params)

        # Get the output layer
        output_layer = result['OUTPUT']    
        return output_layer
    
    def remove_layer_by_name(self, layer_name):
        """Remove a layer from the QGIS project by its name."""
        try:
            for layer in QgsProject.instance().mapLayers().values():
                if layer.name() == layer_name:
                    QgsProject.instance().removeMapLayer(layer.id())
                    break
            return None
        except Exception as e:
            QgsMessageLog.logMessage(f"Error in remove_layer_by_name: {str(e)}", 'AMRUT', Qgis.Critical)
            return None
        
    def create_canvas_frame(self, label_text, layer):
        """Create a frame with a label and a map canvas."""
        frame = QFrame()  # Create a container frame
        frame_layout = QVBoxLayout(frame)  # Set a vertical layout for the frame

        label = QLabel(label_text)  # Create a label with the provided text
        label.setAlignment(Qt.AlignCenter)  # Center-align the label text
        label.setStyleSheet("font-size: 12px; font-weight: bold;")  # Set font size and bold style
        frame_layout.addWidget(label)  # Add the label to the frame layout

        canvas = QgsMapCanvas()  # Create a map canvas
        self.set_colour_opacity(self.saved_temp_layer, 0.6)  # Adjust the opacity for better visualization
        self.set_colour_opacity(self.selected_layer_for_processing, 0.6)
        canvas.setLayers([layer, self.reprojected_raster_layer])
        canvas.setCanvasColor(QColor("white"))  # Set the canvas background color to white

        canvas.refresh()  # Refresh the canvas to ensure proper visualization
        
        frame_layout.addWidget(canvas)  # Add the canvas to the frame layout

        return frame  # Return the completed frame
    
    def set_colour_opacity(self, layer, opacity):
        """Set the opacity of the layer for visualization."""
        context = QgsRenderContext()
        symbols = layer.renderer().symbols(context)
         
        for symbol in symbols:  # Iterate over all symbols in the list
            symbol.setOpacity(opacity)  # Set the opacity for each symbol
        layer.triggerRepaint()  # Trigger a repaint to apply the change

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

    def update_canvases(self):
        """
        Update canvases to focus on the current feature.
        Zooms both canvases to the bounding box of the feature being verified.
        """
        if self.current_feature_index < len(self.data):  # Check if there are remaining features
            feature_ids = list(self.data.keys())
            feature_id = feature_ids[self.current_feature_index]
            feature = next(self.selected_layer_for_processing.getFeatures(f"feature_id = {feature_id}"), None)  # Fetch the feature

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
                self.zoom_to_feature_on_canvas(extent, self.left_canvas, self.selected_layer_for_processing, feature_id)  # Zoom the left canvas to the feature
                self.zoom_to_feature_on_canvas(extent, self.right_canvas, self.saved_temp_layer, feature_id)  # Zoom the right canvas to the feature
            else:
                # Log a warning if the feature cannot be found
                QgsMessageLog.logMessage(
                    f"Feature with feature_id {feature_id} not found in the .amrut file.",
                    "AMRUT",
                    Qgis.Warning
                )            

    def zoom_to_feature_on_canvas(self, extent, canvas, layer, feature_id):
        """Zoom to the feature's bounding box on the canvas."""
        if layer:
            # Apply a filter to show only the specific feature
            layer.setSubsetString(f"feature_id = {feature_id}")
        canvas.setExtent(extent)  # Set the extent of the canvas
        canvas.refresh()  # Refresh the canvas to apply the changes

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
    
    def get_layer_by_name(self, layer_name):
        """Retrieve a layer from the QGIS project by its name."""
        try:
            for layer in QgsProject.instance().mapLayers().values():
                if layer.name() == layer_name:
                    return layer
            return None
        except Exception as e:
            QgsMessageLog.logMessage(f"Error in get_layer_by_name: {str(e)}", 'AMRUT', Qgis.Critical)
            return None
