function MEA_batchConvert(ext)
%form: MEA_batchConvert
%
%This function converts MEA bin (binary, RAW) files into mat files in a batch. It will
%attempt to convert all "raw" files in the directory, so make sure they are
%all MEA files or enter an extension to select a few.
%
%To create the RAW file, 
%1. open MC_DataTool
%2. File-Open Multiple
%3. Select files of interest
%4. Click "bin"
%5. Click "All"
%6. Make sure "Write header" and "Signed 16bit" are checked in lower right
%7. Click Save
%8. when done, click Close

% TODO: Improve the command line output of this

% Last update: 20180626 
% TS: Added the conversion options

%% Select conversion mode 

convertOption = 'electrode'; % save electrode by electrode in a MEA-specific folder
% convertOption = 'whole'; % save the entire grid as one variable

%% initialize

if ~exist('ext','var')
    ext='.raw';
end;

ext2='.raw';

%% get files

d=dir;
files=[];

for i=1:length(d)
    if ~isempty(findstr(d(i).name,ext)) && ~isempty(findstr(d(i).name,ext2)) && length(d(i).name)>2 
        files=[files; i];
    end;
end;

files=d(files);

%% convert the files

for i=1:length(files)
    files(i).name
    skip=0;
    %find if file already converted
    for j=1:length(d)
        if ~isempty(strmatch(files(i).name(1:length(files(i).name)-4),d(j).name)) && d(j).isdir
            d(j).name
            skip=1;
        end;
    end;
    if skip==0
        MEA_load_bin(files(i).name, convertOption);
    end;
end;



end

