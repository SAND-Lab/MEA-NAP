function outTrain = downSampleSum(spikeTrain, newSampleNum) 
%downSampleSum performs downsampling via summation (basically binning) of
%2D matrices. 

% Author: Tim Sit 
% Last Update: 20180518

% INPUT
    % spikeTrain   | numSamp x numChannel matrix 
    % newSampleNum | new sampling rate to use, ie. the number of bins that
    % you want in the end result
    
    
% OUTPUT 
    % outTrain     | newSampleNum x numChannel matrix

    numElectrode = size(spikeTrain, 2); 
    downTrain = reshape(spikeTrain, [], newSampleNum, numElectrode);
    % downTrain = sum(downTrain); % this need resolving
    downTrain = sum(downTrain, 1); % maybe this
    outTrain = reshape(downTrain, newSampleNum, numElectrode);
end 