Running MEA-NAP on HPC
===========================

1. SSH into your remote server
-------------------------------

.. code-block:: bash

    ssh remote_username@remote_host

``remote_username`` and ``remote_host`` are specific to your remote server

2. Download MEA pipeline directory to your remote server
------------------------------------------------------------

There are **2 ways** to download the MEA pipeline directory to your remote server

1. Download the most recent version of the MEA pipeline GitHub repository directly to your remote server

   - SSH into your remote server (see step 1 above)
   - Change to your preferred working directory

   .. code-block:: bash

       cd [myDir]

   ``myDir``: preferred working directory

   - Clone GitHub repository on remote server

   .. code-block:: bash

       git clone https://github.com/SAND-Lab/Supercloud-David.git

   MEA pipeline directory called ``MEA-NAP`` will be downloaded to your current directory

   - Lines indicating successful download of MEA pipeline GitHub repository should appear

   .. code-block:: bash

       Cloning into 'MEA-NAP'...
       remote: Enumerating objects: 2879, done.
       remote: Counting objects: 100% (2879/2879), done.
       remote: Compressing objects: 100% (1111/1111), done.
       remote: Total 2879 (delta 1806), reused 2823 (delta 1760), pack-reused 0
       Receiving objects: 100% (2879/2879), 18.35 MiB | 35.46 MiB/s, done.
       Resolving deltas: 100% (1806/1806), done.
       Updating files: 100% (486/486), done.

2. Download pre-existing, local MEA pipeline directory to your remote server

   - Open another terminal window that is not logged into your remote server to use this command

   - Download modified version of MEA pipeline directory to run on the remote server
     - Modified version of MEA pipeline directory designed to run on the remote SSH server: `https://github.com/SAND-Lab/Supercloud-David/blob/main`

   - Create secure copy of the local MEA pipeline directory on the remote server

   .. code-block:: bash

       scp -r [myDir] remote_username@remote_host:[/remote/directory]

   ``myDir``: path of your local MEA pipeline directory
   ``/remote/directory``: path of the remote server directory where you want to copy your local directory

   - After successfully running the command, switch back to the terminal window that is logged into your remote server

3. Change your current directory to the MEA pipeline directory
----------------------------------------------------------------

.. code-block:: bash

   cd [myDir]

``myDir``: path of the MEA pipeline directory on your remote server

4. Create a directory for mat files in your MEA-NAP directory
---------------------------------------------------------------

.. code-block:: bash

   mkdir [mat_file_dir]

``mat_file_dir``: name of the directory where you will store mat files

5. Download mat files locally
-------------------------------

- Can convert the data acquired by the following systems into mat files
    - **MEA Axion Maestro Acquisition System**
        1. Open MC_DataTool
        2. Select File - Open Multiple
        3. Select files of interest
        4. Click “bin”
        5. Click “All”
        6. Make sure “Write header” and “Signed 16bit” are checked in the lower right
        7. Click save
        8. When done, click close
        9. Open Matlab
        10. Add the analysis pipeline code to the path
        11. Navigate in Matlab to the folder containing the ‘.mcd’ files you want to convert
        12. In the Matlab command window, type **MEAbatchConvert** and press return to run

    - **Multichannel Acquisition system**
        1. Save .raw files from MEA Axion Maeastro system to one folder
        2. Copy the directory path of the folder containing .raw files
        3. Check that rawConvert.m and fillBatchFile.m are installed and saved in the same folder as AxIS MATLAB Files
        4. Open rawConvert.m
        5. Fill out user parameters in Rawconvert.m according to instructions provided in rawConvert.m
        6. Click run
        7. When Rawconvert.m has successfully run, open the folder where .raw files were initially stored
        8. Navigate through the folder to check that all .mat files have been successfully created and saved

6. Upload mat files to the remote server
------------------------------------------

There are **3 ways** to upload mat files:

**For these methods, open another terminal window that is not logged into your remote server**

1. Upload one local mat file to the remote server

   .. code-block:: bash

       scp [mat_file] remote_username@DEST_HOST:[mat_file_dir]

   ``mat_file``: path of a mat file on your local device
   ``mat_file_dir``: path of the remote server directory where you store your mat files (see step 4 above)

2. Upload multiple local mat files to the remote server

   .. code-block:: bash

       scp [mat_file1 mat_file2 mat_file3 ...] remote_username@remote_host:[mat_file_dir]

   ``mat_file1 mat_file2 mat_file3 …``: paths of mat files on your local device

   - The mat file paths should be separated by spaces
   ``mat_file_dir``: path of the remote server directory where you store your mat files (see step 4 above)

3. Upload a local directory containing mat files to the remote server

   .. code-block:: bash

       scp -r [myDir] remote_username@remote_host:[mat_file_dir]

   ``myDir``: path of a local directory containing mat files
   ``mat_file_dir``: path of the remote server directory where you store your mat files (see step 4 above)

7. On your local device, create CSV file(s) for mat files that you plan to analyze
-----------------------------------------------------------------------------------

- More detailed documentation about CSV formatting: `https://analysis-pipeline.readthedocs.io/en/latest/pipeline-steps.html#table-with-your-data-filenames-for-batch-analysis-with-age-and-group-identifiers`

- Example CSV file:

.. image:: ../imgs/csv_file_example.png
   :alt: Example CSV file
   :align: center

8. Upload CSV file(s) to the MEA pipeline directory on the remote server
-------------------------------------------------------------------------

There are **3 ways** to upload mat files:

**For these methods, open another terminal window that is not logged into your remote server**

1. Upload a single CSV file to the MEA pipeline directory on the remote SSH server

   .. code-block:: bash

       scp [csv_file] remote_username@remote_host:[/remote/directory]

   ``csv_file``: path of a local CSV file
  
2. Upload multiple CSV files to the MEA pipeline directory on the

       scp [csv_file1 csv_file2 csv_file3 ...] remote_username@remote_host:[/remote/directory]

   ``csv_file1 csv_file2 csv_file3 ...``: paths of local CSV files

   - The CSV file paths should be separated by spaces
   **/remote/directory**: path of the MEA pipeline directory on the remote server (see Step 2 above)

   **/remote/directory**: path of the MEA pipeline directory on the remote server (see Step 2 above)

3. Move all CSV files located in a local directory to the remote server directory

   .. code-block:: bash

       scp -r [myDir] remote_username@remote_host:[/remote/directory]

   ``myDir``: path of a local directory containing CSV files
   ``/remote/directory``: path of the MEA pipeline directory on the remote server (see Step 2 above)


9. Create a bash script to submit jobs for MEApipeline.m
---------------------------------------------------------

- Check available MATLAB versions on your server

  .. code-block:: bash

     module avail matlab

- If not available, check available R modules on your server

  .. code-block:: bash

     module avail R

- Get the full path of your MEA pipeline directory on the remote server

  .. code-block:: bash

     cd /remote/directory
     pwd

``/remote/directory``: path of the MEA pipeline directory on the remote server

- Create a new bash script

   .. code-block:: bash

       nano bash_script_name.sh

``bash_script_name``: name of the bash script
- must end with .sh

- Example bash script:

   .. code-block:: bash

       #!/bin/bash
       #SBATCH -n 4
       #SBATCH -N 1
       #SBATCH -o MEApipeline.sh.log-%j

       cd /remote/directory

       # Load the module
       module load module_name

       # Run MATLAB script
       matlab -nodisplay -nosplash -r "run('MEApipeline.m'); exit;"

``/remote/directory``: path of the MEA pipeline directory on the remote server (see Step 2 above)
``module_name``: name of the MATLAB or R module that you chose

- Line Overview
    - ``cd /remote/directory`` allows the remote server to easily access files necessary for running MEApipeline.m **(required)**
    - ``#SBATCH -o MEApipeline.sh.log-%j``: include this line in your bash script to save log files that can be distinguished by their job ID **(recommended)**
        - Log files are useful for viewing progress and error messages related to the MEApipeline.m


10. Change the working directory to the MEA pipeline directory on the remote server
------------------------------------------------------------------------------------

**Make sure the terminal window is logged into the SSH server**

- Change the working directory

   .. code-block:: bash

       cd [/remote/directory]

``/remote/directory``: path of the MEA pipeline directory on the remote server

11. Modify MEApipeline.m
--------------------------

There are 3 **ways** to edit MEApipeline.m

For all methods, edit MEApipeline.m according to this documentation: `https://analysis-pipeline.readthedocs.io/en/latest/pipeline-steps.html`

1. Modify MEApipeline.m with the edit command

   .. code-block:: bash

       edit [/path/to/remote_MEApipeline.m]

``/path/to/remote_MEApipeline.m``: path of MEApipeline.m on your remote server

2. Modify MEApipeline.m with the nano command

   .. code-block:: bash

       nano [/path/to/remote_MEApipeline.m]

``/path/to/remote_MEApipeline.m``: path of MEApipeline.m on your remote server

3. Modify MEApipeline.m locally before transferring the file to the MEA pipeline directory on the remote server

   .. code-block:: bash

       scp [/path/to/local_MEApipeline.m] remote_username@remote_host:[/remote/directory]

``/path/to/local_MEApipeline.m``: path of MEApipeline.m on your local device
``/remote/directory``: path of the MEA pipeline directory on the remote server (see Step 2 above)

12. Create a bash script to submit jobs for MEApipeline.m
----------------------------------------------------------

- Check available MATLAB versions on your server

   .. code-block:: bash

       module avail matlab

Note the MATLAB module that you want to use

- If not available, check available R modules on your server

   .. code-block:: bash

       module avail R

Note the R module that you want to use

- Get the full path of your MEA pipeline directory on the remote server

   .. code-block:: bash

       cd [/remote/directory]
       pwd

``/remote/directory``: path of the MEA pipeline directory on the remote server

- Create a new bash script

   .. code-block:: bash

       nano [bash_script_name]

``bash_script_name``: name of the bash script

   - must end with .sh

- Example bash script:

   .. code-block:: bash

       #!/bin/bash
       #SBATCH -n 4
       #SBATCH -N 1
       #SBATCH -o MEApipeline.sh.log-%j

       cd [/remote/directory]

       # Load the module
       module load [module_name]

       # Run MATLAB script
       matlab -nodisplay -nosplash -r "run('MEApipeline.m'); exit;"

``/remote/directory``: path of the MEA pipeline directory on the remote server (see Step 2 above)
``module_name``: name of the MATLAB or R module that you chose

- Line Overview
    - ``cd [/remote/directory]`` allows the remote server to easily access files necessary for running MEApipeline.m **(required)**
    - ``#SBATCH -o MEApipeline.sh.log-%j``: include this line in your bash script to save log files that can be distinguished by their job ID **(recommended)**
        - Log files are useful for viewing progress and error messages related to the MEApipeline.m
    - ``matlab -nodisplay -nosplash -r "run('MEApipeline.m'); exit;":`` automatically runs MEApipeline.m once the job is submitted **(required)**

13. Submit a job with your bash script
----------------------------------------

- Submit the job

   .. code-block:: bash

       sbatch [bash_script]

``bash_script``: path of the bash script needed for job submission

- A Job ID (number) should appear on your screen

14. Check log files to view progress and error messages
--------------------------------------------------------

- Open the log file

   .. code-block:: bash

       nano [log_file]

``log_file``: path of the log file

- If you included ``#SBATCH -o MEApipeline.sh.log-%j`` in your bash script, the Job ID can be used to locate the relevant log file

15. Download MEA pipeline outputs from the remote SSH server
-------------------------------------------------------------

**Open another terminal window that is not logged into your remote server**

- Download MEA pipeline outputs

   .. code-block:: bash

       scp -r remote_username@remote_host:[/remote/directory] [myDir]

``/remote/directory``: remote output directory to download to the local device
