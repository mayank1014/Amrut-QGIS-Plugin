# Sankalan 2.0 Data Transfer Plugin

## Overview

Sankalan 2.0 is a powerful data transfer plugin designed for seamless integration with QGIS. Developed by IIRS under ISRO, this plugin facilitates efficient data exchange and management, ensuring smooth workflows for geospatial applications. The main purpose of this plugin is to transfer data from a QGIS project to the Sankalan Mobile App to vet attributes on the ground. Target users are planning and administrative bodies under the AMRUT 2.0 Scheme of the Ministry of Urban and Housing Affairs.

## Features

- **Data Transfer for Mobile App**: Enables exporting of geospatial data to the Sankalan Mobile App.
- **Layer Validation and Clipping**: Includes features for validating grid layers and clipping data.
- **Seamless Integration**: Works natively within QGIS.
- **Efficient Workflow**: Ensures data integrity and consistency for AMRUT 2.0 workflows.

## System Requirements

- Minimum QGIS Version: 3.0
- QGIS Core Plugin: Processing
- Supported Operating Systems: Windows and Linux

## Installation

1. Clone the repository from GitHub:
   ```bash
   https://github.com/mayank1014/Amrut-QGIS-Plugin/
   ```
2. Open QGIS.
3. Navigate to `Plugins > Manage and Install Plugins`.
4. Install the plugin by adding the cloned directory.

## Usage

1. Open the plugin from the `Plugins` menu in QGIS.
2. Use the main menu to select "Data to Mobile."
3. Follow these steps:

   ### Layer Selection
   - Select the grid or segmentation layer for clipping.
   - Validate the selected layer to ensure compatibility.

   ### Grid Creation
   - Create a grid layer if no segmentation layer is available.

   ### Clipping and Export
   - Specify an output directory for the exported files.
   - Run the clipping process. A progress bar will indicate the process, and a confirmation dialog will appear upon completion.

## Screenshots

### Main Menu
![Main Menu](Screenshot%20from%202025-01-17%2017-17-58.png)

### Clipping and Export
![Clipping and Export](Screenshot%20from%202025-01-17%2017-19-13.png)

### Layer Validation
![Layer Validation](Screenshot%20from%202025-01-17%2017-18-54.png)

### Output Directory Selection
![Output Directory Selection](Screenshot%20from%202025-01-17%2017-19-04.png)

## Contribution

We welcome contributions to enhance the plugin. Please follow these steps:

1. Fork the repository on GitLab.
2. Create a new branch for your feature or bug fix.
3. Commit your changes and push them to your fork.
4. Create a merge request with a detailed description.

## License

(C) 2025 Indian Institute of Remote Sensing (IIRS), Indian Space Research Organisation (ISRO). All rights reserved.

For any queries, contact us through the documentation portal.

---

*Empowering geospatial innovation through advanced tools.*

