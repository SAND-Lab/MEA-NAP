Setting up MEA-NAP
======================================

1. Download MEA-NAP folder from GitHub:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Navigate to the home page of the MEA-NAP GitHub repository using your web browser.

.. image:: imgs/github_repo.png
   :width: 600
   :align: center
   :alt: Screenshot of MEA-NAP GitHub repository home page.

.. raw:: html

   <div style="margin-bottom: 20px;"></div>

- Once on the repository page, look for the **green "Code" button**. Click on it to reveal a dropdown menu.

- In the dropdown menu, select the **"Download ZIP" option.** This will prompt GitHub to compress the latest version of the MEA-NAP repository into a zip folder.

- Once the zip folder is downloaded, navigate to the location where you saved it and extract its contents.

2. Prepare your data for MEA-NAP:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The MEA-NAP pipeline is currently optimized for single MEA recordings made on the Multichannel Systems MEA2100 60-channel MEA system and for multi-well plates using the Axion Maestro MEA System. However, these recordings must be converted to `*.mat` files first.

- **Converting raw MEA data acquired with Multi Channel Experimenter to .mat files**:

   1. Open Multi Channel Data Manager on the computer where your raw data is stored.
   2. Select files and export as HDF5.  n.b. Although Multi Channel Experimenter may save multiple files per recording, the exported HDF5 should have all of the data necessary.
   3. Open the MEA-NAP folder and navigate to Functions→ RawConvert
   4. Open converter_hdf5.m in MATLAB.  
   5. If you acquired data at a rate other than 25000 Hz, update line 58 (fs=25000) with your data acquisition rate.  Save.
   6. Run script (click on green arrow in editor tab). 

- **Converting .mcd files acquired from a Multichannel Systems MEA system with MC_Rack to .mat files**:

   There are 2 ways to convert .raw files from Multichannel Systems MEA system. 
   
   **Method 1:**

   1. Open MC_DataTool.
   2. Select File - Open Multiple.
   3. Choose .mcd files of interest.
   4. Click "bin."
   5. Click "All."
   6. Ensure "Write header" and "Signed 16bit" are checked in the lower right.
   7. Click "save" to save .raw files that are generated.
   8. When done, click close.
   9. Open MATLAB.
   10. Add the analysis pipeline code to the path. 
   11. Navigate in MATLAB to the folder containing the ".raw" files, which were produced by MC_DataTool, you want to convert.
   12. In the MATLAB command window, type ``MEAbatchConvert`` and press return to run.

   **Method 2:**

   1. Open MC_DataTool.
   2. Select File - Open Multiple.
   3. Choose .mcd files of interest.
   4. Click "bin."
   5. Click "All."
   6. Ensure "Write header" and "Signed 16bit" are checked in the lower right.
   7. Click "save" to save .raw files that are generated.
   8. When done, click close.
   9. Open MATLAB.
   10. Open `MEApipeline.m`.
   11. Run script (click green arrow in editor tab) to open GUI.
   12. Specify MEA-NAP Folder in "General" tab.

   .. image:: imgs/MEANAP_dir_gui.png
      :width: 300
      :align: center

   - **MEA-NAP Folder:** Location of the MEA-NAP folder you downloaded from our Github page.
   13. Navigate to "File Conversion" tab. 
   14. Specify parameters for .raw file conversion.

   .. image:: imgs/mcs_file_conversion_gui.png
      :width: 300
      :align: center

   - **File Type:** The type of .raw file that you are converting. Make sure it is set to ".raw from Multichannel Systems".
   - **File location:** Location of .raw file that you want to convert to .mat format.

- **Converting .raw files acquired from an Axion Maestro MEA system to .mat files**:

   There are 2 ways to convert .raw files acquired from Axion Maestro MEA system.

   **Method 1:**

   1. Save `.raw` files from MEA Axion Maestro system to one folder.
   2. Open MATLAB.
   3. Open `rawConvert.m` which is located in ConvertRawtoMat subfolder inside Functions folder.

   .. image:: imgs/ConvertRawtoMat.png
      :width: 300
      :align: center

   4. Fill out user parameters in `rawConvert.m` according to instructions provided in `rawConvert.m`.

   .. image:: imgs/rawConvert.png
      :width: 600
      :align: center

   5. Run script (click green arrow in editor tab).
   6. When `rawConvert.m` has successfully run, open the folder where `.raw` files were initially stored.
   7. Navigate through the folder to check that all `.mat` files have been successfully created and saved.

   **Method 2:** 

   1. Open MATLAB.
   2. Open `MEApipeline.m`.
   3. Run script (click green arrow in editor tab) to open GUI.
   4. Specify MEA-NAP Folder in "General" tab.

   .. image:: imgs/MEANAP_dir_gui.png
      :width: 300
      :align: center

   - **MEA-NAP Folder:** Location of the MEA-NAP folder you downloaded from our Github page.

   5. Navigate to "File Conversion" tab. 
   6. Specify parameters for .raw file conversion.

   .. image:: imgs/axion_file_conversion_gui.png
      :width: 300
      :align: center

   - **File Type:** The type of .raw file that you are converting. Make sure it is set to ".raw from Axion Maestro".
   - **File location:** Location of .raw file that you want to convert to .mat format.
   - **Batch CSV name:** Name of batch analysis CSV file that will be generated. See step 4 for more details.
   - **DIV included?:** Specify whether you .raw file has DIV included.
   - **One genotype?:** Specify whether you included only one genotype in your recording.
   - **Genotype Group:** Name of genotype group that you used if you only included one

   6. Click 'Run file conversion'.


3. Organize your data:
^^^^^^^^^^^^^^^^^^^^^^^
After preparing your data, it is essential to organize the `.mat` files you plan to analyze in a batch. Ensure that all relevant `.mat` files are saved in the same folder. This organized structure is crucial for the MEA-NAP pipeline to seamlessly process and compare the data during the analysis.
   
- Keep all the `.mat` files intended for a specific batch analysis in a dedicated folder.
- Maintain a concise and consistent naming convention for these batch analysis folders.
- As filenames and group names are included in many plots, it is important to keep the names concise and informative (e.g., NGN2230101_P1_A1_DIV14, where
   NGN2 is the experiment code, 230101 is the date the culture was started, P1_A1 is the plate and well number, and DIV14 is the age).

4. Prepare batch analysis CSV file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   
.. _prepare-batch-analysis-csv-file:

- Create a ``*.csv`` or ``*.xlsx`` file with the following columns:

   1. **Recording filename**: column containing filenames of the ``*.mat`` files for analysis, excluding extension (.mat).
   2. **Age group**: column containing the age (e.g., DIV group) (should be a number for each file).
   3. **Group**: column containing the group (e.g., genotype such as WT or KO). Important, group names cannot start with a number.
   4. **Ground**: column containing any electrodes that should be grounded for each file.

Here is an example spreadsheet in CSV format opened in Microsoft Excel.

.. image:: imgs/example-spreadsheet-input.png
   :width: 500
   :align: center

.. raw:: html

   <div style="margin-bottom: 20px;"></div>

**Note:** If you using Axion Maestro MEA data, rawConvert.m will generate a batch analysis csv file for you. However, **you will still need to be modify the columns based on the descriptions above.**


Congratulations! With the completion of the data preparation steps outlined above, your data is now ready for analysis using MEA-NAP. 









