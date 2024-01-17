Running MEA-NAP on High-Performance Computing (HPC)
===================================================

HPC can be useful when analysing large datasets (e.g., more than 100 recordings) with MEA-NAP.  
We have adapted MEA-NAP for HPC and include the methods we used here for advanced users. These 
steps may need to be modified depending on the user's institution's HPC resources. 

=========================

.. _HPC_step1:

1. SSH into your remote server
-------------------------------

.. code-block:: bash

    ssh remote_username@remote_host

- ``remote_username`` and ``remote_host`` are specific to your remote server

.. _HPC_step2:

2. Upload the HPC version of MEA-NAP to your remote server
------------------------------------------------------------

There are **2 ways** to download the HPC version of MEA-NAP to your remote server

1. Upload HPC version of MEA-NAP directly to your remote server

   - SSH into your remote server (:ref:`see step 1 above <HPC_step1>`)
   - Switch to your preferred working directory

   .. code-block:: bash

       cd [myDir]

   - ``myDir``: preferred working directory

   - Clone HPC version of MEA-NAP on remote server

   .. code-block:: bash

       git clone https://github.com/SAND-Lab/MEA-NAP-HPC.git

   - MEA-NAP directory called ``MEA-NAP-HPC`` will be downloaded to your current directory

   - Lines indicating successful download of HPC version of MEA-NAP should appear

   .. code-block:: bash

       Cloning into 'MEA-NAP'...
       remote: Enumerating objects: 2879, done.
       remote: Counting objects: 100% (2879/2879), done.
       remote: Compressing objects: 100% (1111/1111), done.
       remote: Total 2879 (delta 1806), reused 2823 (delta 1760), pack-reused 0
       Receiving objects: 100% (2879/2879), 18.35 MiB | 35.46 MiB/s, done.
       Resolving deltas: 100% (1806/1806), done.
       Updating files: 100% (486/486), done.

2. Download HPC version of MEA-NAP locally and upload to your remote server

   - Download `here <https://github.com/SAND-Lab/MEA-NAP-HPC>`__ 
   
   - Open another terminal window that is not logged into your remote server to use this command

   - Upload secure copy of the local directory to your remote server

   .. code-block:: bash

       scp -r [myDir] remote_username@remote_host:[/remote/directory]

   - ``myDir``: path of your local MEA-NAP directory
   - ``/remote/directory``: path of your remote server directory where you want to copy your local directory

   - After successfully running the command, switch back to the terminal window that is logged into your remote server

.. _HPC_step3:

3. Change your current directory to the MEA-NAP directory on your remote server
---------------------------------------------------------------------------------

.. code-block:: bash

   cd [myDir]

- ``myDir``: path of the MEA-NAP directory on your remote server

.. _HPC_step4:

4. Create a directory for mat files in the MEA-NAP directory on your remote server
----------------------------------------------------------------------------------

.. code-block:: bash

   mkdir [mat_file_dir]

- ``mat_file_dir``: name of the directory where you will store mat files

.. _HPC_step5:

5. Upload mat files to your remote server
------------------------------------------

There are **3 ways** to upload mat files:

**For these methods, open another terminal window that is not logged into your remote server**

1. Upload one local mat file to your remote server

   .. code-block:: bash

       scp [mat_file] remote_username@DEST_HOST:[mat_file_dir]

   - ``mat_file``: path of a mat file on your local device
   - ``mat_file_dir``: path of your remote server directory where you store your mat files (:ref:`see step 4 above <HPC_step4>`)

2. Upload multiple local mat files to your remote server

   .. code-block:: bash

       scp [mat_file1 mat_file2 mat_file3 ...] remote_username@remote_host:[mat_file_dir]

   - ``mat_file1 mat_file2 mat_file3 …``: paths of mat files on your local device (**should be separated by spaces**)
   - ``mat_file_dir``: path of your remote server directory where you store your mat files (:ref:`see step 4 above <HPC_step4>`)

3. Upload a local directory containing mat files to your remote server

   .. code-block:: bash

       scp -r [myDir] remote_username@remote_host:[mat_file_dir]

   - ``myDir``: path of a local directory containing mat files
   - ``mat_file_dir``: path of your remote server directory where you store your mat files (:ref:`see step 4 above <HPC_step4>`)

.. _HPC_step6:

6. Upload CSV file(s) to the MEA-NAP directory to your remote server
-------------------------------------------------------------------------

- For more detailed documentation about CSV formatting, :ref:`click here. <prepare-batch-analysis-csv-file>`

- There are **3 ways** to upload CSV files:

  - **For these methods, open another terminal window that is not logged into your remote server**

  1. Upload a single CSV file

     .. code-block:: bash

         scp [csv_file] remote_username@remote_host:[/remote/directory]

     - ``csv_file``: path of a local CSV file

  2. Upload multiple CSV files 

     .. code-block:: bash

         scp [csv_file1 csv_file2 csv_file3 ...] remote_username@remote_host:[/remote/directory]

     - ``csv_file1 csv_file2 csv_file3 ...``: paths of local CSV files (**should be separated by spaces**)
     - ``/remote/directory``: path of the MEA-NAP directory on your remote server (:ref:`see step 2 above <HPC_step2>`)


  3. Upload all CSV files located in a local directory

     .. code-block:: bash

         scp -r [myDir] remote_username@remote_host:[/remote/directory]

     - ``myDir``: path of a local directory containing CSV files
     - ``/remote/directory``: path of the MEA-NAP directory on your remote server (:ref:`see step 2 above <HPC_step2>`)

.. _HPC_step7:

7. Create a bash script to submit jobs for MEApipeline.m
---------------------------------------------------------

- Check available MATLAB versions on your remote server

  .. code-block:: bash

     module avail matlab

- If not available, check available R modules on your remote server

  .. code-block:: bash

     module avail R

- Get the full path of the MEA-NAP directory on your remote server

  .. code-block:: bash

     cd /remote/directory
     pwd

  ``/remote/directory``: path of the MEA-NAP directory on your remote server

- Create a new bash script

  .. code-block:: bash

     nano bash_script_name.sh

  ``bash_script_name``: name of the bash script (**must end with .sh**)

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

  - ``/remote/directory``: path of the MEA-NAP directory on your remote server (:ref:`see step 2 above <HPC_step2>`)
  - ``module_name``: name of the MATLAB or R module that you chose

- Line Overview
    - ``cd /remote/directory`` allows your remote server to easily access files necessary for running MEApipeline.m **(required)**
    - ``#SBATCH -o MEApipeline.sh.log-%j``: include this line in your bash script to save log files that can be distinguished by their job ID **(recommended)**
        - Log files are useful for viewing progress and error messages related to the MEApipeline.m

.. _HPC_step8:

8. Change the working directory to the MEA-NAP directory on your remote server
------------------------------------------------------------------------------------

**Make sure the terminal window is logged into your remote server**

- Change the working directory

  .. code-block:: bash

      cd [/remote/directory]

``/remote/directory``: path of the MEA-NAP directory on your remote server

.. _HPC_step9:

9. Modify MEApipeline.m
--------------------------

There are 3 **ways** to edit MEApipeline.m

For all methods, edit MEApipeline.m according to this documentation: `https://analysis-pipeline.readthedocs.io/en/latest/pipeline-steps.html`

1. Modify MEApipeline.m with the edit command

   .. code-block:: bash

       edit [/path/to/remote_MEApipeline.m]

   - ``/path/to/remote_MEApipeline.m``: path of MEApipeline.m on your remote server

2. Modify MEApipeline.m with the nano command

   .. code-block:: bash

       nano [/path/to/remote_MEApipeline.m]

   - ``/path/to/remote_MEApipeline.m``: path of MEApipeline.m on your remote server

3. Modify MEApipeline.m locally before transferring the file to the MEA-NAP directory on your remote server

   .. code-block:: bash

       scp [/path/to/local_MEApipeline.m] remote_username@remote_host:[/remote/directory]

   - ``/path/to/local_MEApipeline.m``: path of MEApipeline.m on your local device
   - ``/remote/directory``: path of the MEA-NAP directory on your remote server (:ref:`see step 2 above <HPC_step2>`)

.. _HPC_step10:

10. Create a bash script to submit jobs for MEApipeline.m
----------------------------------------------------------

- Check available MATLAB versions on your remote server

  .. code-block:: bash

    module avail matlab

  - Note the MATLAB module that you want to use

- If not available, check available R modules on your remote server

  .. code-block:: bash

    module avail R

  - Note the R module that you want to use

- Get the full path of the MEA-NAP directory on your remote server

  .. code-block:: bash

    cd [/remote/directory]
    pwd

  - ``/remote/directory``: path of the MEA-NAP directory on your remote server

- Create a new bash script

  .. code-block:: bash

      nano [bash_script_name]

  - ``bash_script_name``: name of the bash script (**must end with .sh**)

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

  - ``/remote/directory``: path of the MEA-NAP directory on your remote server (:ref:`see step 2 above <HPC_step2>`)
  - ``module_name``: name of the MATLAB or R module that you chose

- Line Overview
   - ``cd [/remote/directory]`` allows your remote server to easily access files necessary for running MEApipeline.m **(required)**
   - ``#SBATCH -o MEApipeline.sh.log-%j``: include this line in your bash script to save log files that can be distinguished by their job ID **(recommended)**
      - Log files are useful for viewing progress and error messages related to the MEApipeline.m
   - ``matlab -nodisplay -nosplash -r "run('MEApipeline.m'); exit;":`` automatically runs MEApipeline.m once the job is submitted **(required)**

.. _HPC_step11:

11. Submit a job with your bash script
----------------------------------------

- Submit the job

  .. code-block:: bash

      sbatch [bash_script]

  - ``bash_script``: path of the bash script needed for job submission

  - A Job ID (number) should appear on your screen

.. _HPC_step12:

12. Check log files to view progress and error messages
--------------------------------------------------------

- Open the log file

  .. code-block:: bash

      nano [log_file]

  - ``log_file``: path of the log file

  - If you included ``#SBATCH -o MEApipeline.sh.log-%j`` in your bash script, the Job ID can be used to locate the relevant log file

.. _HPC_step13:

13. Download MEA-NAP outputs from your remote server
-------------------------------------------------------------

**Open another terminal window that is not logged into your remote server**

- Download MEA-NAP outputs

  .. code-block:: bash

      scp -r remote_username@remote_host:[/remote/directory] [myDir]

  - ``/remote/directory``: remote output directory to download to the local device

