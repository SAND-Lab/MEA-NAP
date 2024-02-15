%% Convert hdf5 files to mat files

function converterMSC

start_folder = uigetdir(pwd,'Select the folder with hdf5 files');
cd(start_folder);

d = dir;
phase = 0;

% Control the number of phases and if there are h5 files in the selected folder    
for k = 3:length(d)
    if ~isempty(strfind(d(k).name,'h5'))
        phase = phase+1;
        nn = d(k).name;
    end
end

if phase == 0
    f = errordlg('Selection failed - There are not hdf5 file', 'Folder Error');
    return 
end


name = split(nn,'_');
mkdir(char(name(1)));
d = dir;
cd(char(name(1)));
exp_folder = pwd;
mkdir(char(strcat(name(1),'_Mat_files')));
cd(char(strcat(name(1),'_Mat_files')));
phase_folder = pwd;

import McsHDF5.*

for k = 3:length(d)
    
    if ~isempty(strfind(d(k).name,'h5'))
        waitMessage = ['Converting file: ' d(k).name];
        waitMessage = strrep(waitMessage, '_', '-');
        waitbarHandle = waitbar((k-3)/(length(d)-2),([blanks(5) waitMessage blanks(5)]));
        
        cd(start_folder);
    
        cfg = [];
        cfg.dataType = 'double';
        exp = McsHDF5.McsData(d(k).name);
        exponent = exp.Recording{1}.AnalogStream{1}.Info.Exponent(:);
        exponent = double(exponent);
        
        label = exp.Recording{1}.AnalogStream{1}.Info.Label(:);
       
        converted_data = exp.Recording{1}.AnalogStream{1}.getConvertedData(cfg);
        %% Save data in the proper format

        converted_data = (converted_data.*10.^(exponent-(exponent+6)))';
        channels = str2double(label)';
        fs = 25000; 
        savename = split(d(k).name,'.');
        savename = savename{1};
        save(savename, "converted_data", "channels", "fs")

       
        delete (waitbarHandle);
    end
end


%%
EndOfProcessing (start_folder, 'Successfully accomplished');
        
        
        
    