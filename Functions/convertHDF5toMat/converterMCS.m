%% Convert hdf5 files to mat files

function converterMCS(start_folder,out_folder,fs,varargin)

cd(start_folder);

d = dir;
phase = 0;

if ~isempty(varargin{1})
    custom_filename = varargin{1};
    cycle = custom_filename;
else
    cycle = 1 : 1 : length(d)-2;
end



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


import McsHDF5.*

for k = 1:length(cycle)
    
    if ~isempty(strfind(d(cycle(k)+2).name,'h5'))
        waitMessage = ['Converting file: ' d(cycle(k)+2).name];
        waitMessage = strrep(waitMessage, '_', '-');
        waitbarHandle = waitbar((k)/(length(cycle)),([blanks(5) waitMessage blanks(5)]));
        
        cd(start_folder);
    
        cfg = [];
        cfg.dataType = 'double';

        exp = McsHDF5.McsData(d(cycle(k)+2).name);
       
        
        exponent = exp.Recording{1}.AnalogStream{1}.Info.Exponent(:);
        exponent = double(exponent);
        
        label = exp.Recording{1}.AnalogStream{1}.Info.Label(:);
       
        dat = exp.Recording{1}.AnalogStream{1}.getConvertedData(cfg);
        %% Save data in the proper format
        cd(out_folder)
        dat = (dat.*10.^(exponent-(exponent+6)))';
        for ii = 1 : length(label)
            label{ii} = strrep(label{ii},'E-00156 ', '');
        end
        channels = str2double(label)';
        fs = 10000 ;
        savename = split(d(cycle(k)+2).name,'.');
        savename = savename{1};
        save(savename, "dat",'-v7.3', "channels", "fs")
        clear dat channels
        delete (waitbarHandle);
    end
end


%%
warndlg('MCS Convertion Completed','Warning');
        
        
        
    