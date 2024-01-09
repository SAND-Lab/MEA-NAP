Setting up MEA-NAP
======================================

1. Download MEA-NAP Folder from GitHub:
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

2. Prepare Your Data for MEA-NAP:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


The MEA-NAP pipeline is currently optimized for single MEA recordings made on the Multichannel Systems MEA2100 60-channel MEA system and for multi-well plates using the Axion Maestro MEA System. However, these recordings must be converted to `*.mat` files first.

- **Converting .mcd files acquired from a Multichannel Systems MEA system with MC_Rack to .mat files**:

   1. Open MC_DataTool.
   2. Select File - Open Multiple.
   3. Choose files of interest.
   4. Click "bin."
   5. Click "All."
   6. Ensure "Write header" and "Signed 16bit" are checked in the lower right.
   7. Click save.
   8. When done, click close.
   9. Open MATLAB.
   10. Add the analysis pipeline code to the path.
   11. Navigate in MATLAB to the folder containing the ".mcd" files you want to convert.
   12. In the MATLAB command window, type ``MEAbatchConvert`` and press return to run.

- **Converting .raw files acquired from an Axion Maestro MEA system to .mat files**:

   1. Save `.raw` files from MEA Axion Maestro system to one folder.
   2. Copy the directory path of the folder containing `.raw` files.
   3. Verify that `rawConvert.m` and `fillBatchFile.m` are installed and saved in the same folder as AxIS MATLAB Files.
   4. Open `rawConvert.m`.
   5. Fill out user parameters in `rawConvert.m` according to instructions provided in `rawConvert.m`.
   6. Click run.
   7. When `rawConvert.m` has successfully run, open the folder where `.raw` files were initially stored.
   8. Navigate through the folder to check that all `.mat` files have been successfully created and saved.

3. Organize Your Data:
^^^^^^^^^^^^^^^^^^^^^^^
After preparing your data, it is essential to organize the `.mat` files you plan to analyze in a batch. Ensure that all relevant `.mat` files are saved in the same folder. This organized structure is crucial for the MEA-NAP pipeline to seamlessly process and compare the data during the analysis.
   
- Keep all the `.mat` files intended for a specific batch analysis in a dedicated folder.
- Maintain a concise and consistent naming convention for these batch analysis folders.
- As filenames and group names are included in many plots, it is important to keep the names concise and informative (e.g., NGN2230101_P1_A1_DIV14, where
   NGN2 is the experiment code, 230101 is the date the culture was started, P1_A1 is the plate and well number, and DIV14 is the age).

4. Prepare Batch Analysis CSV File
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









