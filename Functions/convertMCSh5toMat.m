function convertMCSh5toMat(dataFolder)
% Converts h5 files from multichannel systems (MCS) to mat files to be used
% in MEA-NAP 
% Adapted from code from Alessio 
% Written by Tim Sit during March 2024
% The code currently assumes that the reference electrode is number 15
    
    fileList = dir(fullfile(dataFolder, '*.h5'));
    
    for fileIndex = 1:length(fileList)
        
        fpath = fullfile(fileList(fileIndex).folder, fileList(fileIndex).name);
        
        h5data = McsHDF5.McsData(fpath);
        

        exponent = h5data.Recording{1}.AnalogStream{1}.Info.Exponent(:);
        exponent = double(exponent);

        label = h5data.Recording{1}.AnalogStream{1}.Info.Label(:);
        numChannels = length(label);
        
        channels = zeros(numChannels, 1) + nan;
        for channelIdx = 1:numChannels
            channelStr = split(label{channelIdx}, ' ');
            
            if strcmp(channelStr{end}, 'Ref')
               channelNumber = 15; 
            else
               channelNumber = str2num(channelStr{end});
            end
            
            channels(channelIdx) = channelNumber;
        end
        
        cfg = [];
        cfg.dataType = 'double';
        dat = h5data.Recording{1}.AnalogStream{1}.getConvertedData(cfg); 
        dat = (dat.*10.^(exponent-(exponent+6)))'; % (numSample, numChannels)
        
        % channels = str2double(label)';  % this is in Alessio's code, but
        % outputs NaN in my exerience
        
        fNameParts = split(fileList(fileIndex).name, '.');
        fileName = join(fNameParts{1:end-1}, '.');
        
        fs = h5data.Recording{1}.AnalogStream{1}.getSamplingRate;
        
        savename = fullfile(fileList(fileIndex).folder, [fileName '.mat']);
        
        % get size of dat 
        dt = whos('dat'); 
        datMB = dt.bytes*9.53674e-7;  
        
        if datMB > 2000 
            save(savename, "dat", "channels", "fs", '-v7.3');
        else
            save(savename, "dat", "channels", "fs");
        end 
          
        
        
    end

end