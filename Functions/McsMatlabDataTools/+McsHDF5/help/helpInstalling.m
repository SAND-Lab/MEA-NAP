%% Installing the Toolbox
% Following these instructions is only necessary, if you have downloaded
% the Toolbox as a .zip file. If you are using the .mltbx file or have
% installed the Toolbox via Matlab's "Add-Ons" menu, there is no need to
% perform the steps in this document

%% Adding the package base bath
% If you have download the package as a .zip file, you will need to add the
% base path of the +McsHDF5 folder to your matlab path after extracting the
% .zip file. The base path is the directory one level below the +McsHDF5
% folder. This step is not necessary if you have installed the Toolbox from
% the .mltbx file or via the Add-Ons menu in Matlab.

%% 
% *Example 1:* If you saved the package for example to the directory
% C:\Code\+McsHDF5, you should have the following directory structure:
%
% * |C:\Code\+McsHDF5\@McsAnalogStream|
% * |C:\Code\+McsHDF5\@McsData|
% * |C:\Code\+McsHDF5\@McsEventStream|
% * |...|
%
% In this case, the base path is the directory C:\Code, so you should call
% the following command:
%
%   addpath C:\Code

%% 
% *Example 2:* If you saved the package for example to the directory
% /home/username/Code/+McsHDF5, you should have the following directory
% structure: 
%
% * |/home/username/Code/+McsHDF5/@McsAnalogStream|
% * |/home/username/Code/+McsHDF5/@McsData| 
% * |/home/username/Code/+McsHDF5/@McsEventStream|
% * |...| 
%
% In this case, the base path is the directory /home/username/Code/, 
% so you should call the following command:
%
%   addpath /home/username/Code/


%% Importing the package
% If you have installed the package from a .zip file, after adding the
% path, import the package as follows:
%
%   import McsHDF5.*