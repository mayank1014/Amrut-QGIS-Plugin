from qgis.PyQt.QtWidgets import (
    QInputDialog, 
    QListWidget, 
    QListWidgetItem, 
    QDialog, 
    QVBoxLayout, 
    QPushButton, 
    QHBoxLayout,
    QLabel,QRadioButton, 
    QComboBox, 
    QSpinBox,
    QSizePolicy
    )
from qgis.core import (
    QgsProcessingFeatureSourceDefinition,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsWkbTypes,
    QgsProject,
    QgsRectangle,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsProcessingFeedback,
    QgsSpatialIndex, 
    QgsPalLayerSettings, 
    QgsTextFormat, 
    QgsVectorLayerSimpleLabeling
)
from qgis.PyQt.QtGui import QIcon, QFont, QPixmap
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant,Qt
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QProgressDialog

import processing
import os

selectedLayer = None
gridLayer = None


def getLayerSelectionLayout(parent,allLayers, selectedLayers) :
    
    selectionLayout = QVBoxLayout()
    selectionLayout.setParent(parent)
    logo_layout = createLogoLayout()
    selectionLayout.addLayout(logo_layout)

    # Add list widget to show layers
    layer_list_widget = QListWidget()
    for layer in allLayers:
        item = QListWidgetItem(layer.name())
        item.setCheckState(Qt.Unchecked)
        layer_list_widget.addItem(item)

    selectionLayout.addWidget(layer_list_widget)

    # Collect selected layers
    for i in range(layer_list_widget.count()):
        item = layer_list_widget.item(i)
        if item.checkState() == Qt.Checked:
            layer_name = item.text()
            for layer in allLayers:
                if layer.name() == layer_name:
                    selectedLayers.append(layer)
                    break
    return selectionLayout

def getGridLayerInput(selectedLayersName, allLayers) :
    gridLayerSlectionDialog = QDialog()
    gridLayerSlectionDialog.setWindowTitle("Provide Grid")
    gridLayerSlectionDialog.setMinimumSize(400,400)
    dialogLayout = QVBoxLayout()

    logolayout = createLogoLayout()
    selectedLayersDisplayLayout = getListLayout(selectedLayersName, "Selected Layers")
    dialogLayout.addLayout(logolayout)
    dialogLayout.addLayout(selectedLayersDisplayLayout)

    question = "Do you already have grid / segmentation Layer to clip ?"
    questoionLable = QLabel(question)
    
    radio_layout = QHBoxLayout()
    yes_radio = QRadioButton("Yes")
    no_radio = QRadioButton("No")
    radio_layout.addWidget(yes_radio)
    radio_layout.addWidget(no_radio)

    dialogLayout.addLayout(questoionLable)
    dialogLayout.addLayout(radio_layout)

    dropdown_lable = QLabel("")
    dropdown_lable.setVisible(False)
    layer_dropdown = QComboBox()
    layer_map = {}
    
    for layer in QgsProject.instance().mapLayers().values():
        layer_dropdown.addItem(layer.name())
        layer_map[layer.name()] = layer

    def on_layer_selected(index):
        global selectedLayer
        selected_layer_name = layer_dropdown.itemText(index)
        selectedLayer = layer_map.get(selected_layer_name)

    layer_dropdown.currentIndexChanged.connect(on_layer_selected)
    layer_dropdown.setVisible(False) 

    number_input = QSpinBox()
    number_input.setRange(100, 10000)  # Set range as needed
    number_input.setVisible(False)  # Initially hidden

    number_label = QLabel("Input Grid Size")  # To be shown with number input
    number_label.setVisible(False)

    dialogLayout.addWidget(layer_dropdown)
    dialogLayout.addWidget(number_label)
    dialogLayout.addWidget(number_input)

    def on_radio_button_toggled():
        if yes_radio.isChecked():
            layer_dropdown.setVisible(True)
            dropdown_lable.setText("Select Grid / Segmentation Layer : ")
            dropdown_lable.setVisible(True)
            number_input.setVisible(False)
            number_label.setVisible(False)
        elif no_radio.isChecked():
            layer_dropdown.setVisible(True)
            dropdown_lable.setText("Select Area Boundary Layer : ")
            dropdown_lable.setVisible(True)
            number_input.setVisible(True)
            number_label.setVisible(True)
    
    yes_radio.toggled.connect(on_radio_button_toggled)
    no_radio.toggled.connect(on_radio_button_toggled)

    def on_accept_input() :
        if selectedLayer is None : 
            showErrorDialog("No Layer Selected")
        else :
            if yes_radio.isChecked() : 
                global gridLayer
                gridLayer = selectedLayer
            
            if no_radio.isChecked() : 
                grid_size = number_input.value()
                boundaryLayer = selectedLayer






    
    

def getListLayout(itemList, lable) : 
    layout = QVBoxLayout()
    
    list_lable = QLabel(lable + ":")
    layout.addWidget(list_lable)
    
    list_widget = QListWidget()
    layout.addWidget(list_widget)
    
    for item in itemList:
        list_widget.addItem(item)
    
    return layout


def createLogoLayout(heading_name, sub_heading_name=""):
    pwd = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(pwd, "assets")
    logo1_name = "iirs.png"
    logo2_name = "amrut.png"
    logo_size = (100, 100)

    logo1_path = os.path.join(assets_dir, logo1_name)
    logo2_path = os.path.join(assets_dir, logo2_name)

    if not os.path.exists(logo1_path) or not os.path.exists(logo2_path):
        QMessageBox.critical(None, "Error", f"Logos not found!\n{logo1_path}\n{logo2_path}")
        return QHBoxLayout()

    logo_layout = QHBoxLayout()
    heading_layout = QVBoxLayout()

    # **Ensure No Extra Spacing**
    heading_layout.setSpacing(0)
    heading_layout.setContentsMargins(0, 0, 0, 0)

    logo1_label = QLabel()
    logo2_label = QLabel()
    heading_label = QLabel(heading_name)
    sub_heading_label = QLabel(sub_heading_name)

    logo1_pixmap = QPixmap(logo1_path).scaled(logo_size[0], logo_size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
    logo2_pixmap = QPixmap(logo2_path).scaled(logo_size[0], logo_size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)

    if not logo1_pixmap or logo1_pixmap.isNull():
        logo1_label.setText("Logo 1 Missing")
    else:
        logo1_label.setPixmap(logo1_pixmap)

    if not logo2_pixmap or logo2_pixmap.isNull():
        logo2_label.setText("Logo 2 Missing")
    else:
        logo2_label.setPixmap(logo2_pixmap)

    font = QFont()
    font.setBold(True)
    heading_label.setFont(font)

    heading_label.setAlignment(Qt.AlignCenter)
    sub_heading_label.setAlignment(Qt.AlignCenter)

    # **Ensure No Extra Height Contribution**
    sub_heading_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    sub_heading_label.setFixedHeight(sub_heading_label.sizeHint().height())  # Set exact height
    sub_heading_label.adjustSize()  # Force correct sizing

    heading_layout.addWidget(heading_label)
    heading_layout.addWidget(sub_heading_label)

    logo_layout.addWidget(logo1_label)
    logo_layout.addStretch()
    logo_layout.addLayout(heading_layout)
    logo_layout.addStretch()
    logo_layout.addWidget(logo2_label)

    return logo_layout

def get_footer_note () :
    # Footer Note
    footer_text = "This QGIS Plugin is Designed and Developed by India Institute of Remote Sensing, ISRO Dehradun under AMRUT Phase -2 Programme of Ministry of Housing and Urban Affairs, Government of India, © IIRS, ISRO"
    footer_label = QLabel(footer_text)

    font = QFont()
    font.setFamily("Monospace")  # Set font family
    font.setPointSize(7)  # Set font size

    # Apply font to QLabel
    footer_label.setFont(font)
    footer_label.setWordWrap(True)
    footer_label.setFixedWidth(400)
    footer_label.setAlignment(Qt.AlignCenter)
    return footer_label

def showErrorDialog(message) :
    dialog = QDialog()
    dialog.setWindowTitle("Error")
    layout = QVBoxLayout()
    message = QLabel(message)
    message.setWordWrap(True)
    close = QPushButton("Close")
    close.clicked.connect(dialog.close)
    layout.addWidget(message)
    layout.addWidget(close)
    dialog.exec_()
def get_warning_icon () :
    pwd = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(pwd, "assets")
    warning_name = "warning.png"

    warning_logo_path = os.path.join(assets_dir, warning_name)
    logo_size = (24, 24)
    warning_logo = QPixmap(warning_logo_path).scaled(logo_size[0], logo_size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return warning_logo


def get_checked_icon():
    pwd = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(pwd, "assets")
    checked_name = "checked.png"

    checked_logo_path = os.path.join(assets_dir, checked_name)
    logo_size = (24, 24)
    checked_logo = QPixmap(checked_logo_path).scaled(logo_size[0], logo_size[1], Qt.KeepAspectRatio,Qt.SmoothTransformation)
    return checked_logo
def get_icon():
    pwd = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(pwd, "assets")
    icon_name = "iirs.png"
    icon_path = os.path.join(assets_dir, icon_name)
    icon = QIcon(icon_path)
    return icon



