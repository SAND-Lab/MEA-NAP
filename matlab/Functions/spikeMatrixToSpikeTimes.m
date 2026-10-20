function spikeTimes = spikeMatrixToSpikeTimes(spikeMatrix, fs)
%{
spikeMatrixToSpikeTimes converts spike matrix to spike times 
Parameters
----------
spikeMatrix : matrix 
    matrix with size (numSamples, numElectrodes)
fs : int 
    sampling frequency
Returns
-------
spikeTimes : cell 
    numElectrodes x 1 cell where each cell contains a vector 
    of the spike times in seconds 
%}
    
    numSamples = size(spikeMatrix, 1);
    numUnits = size(spikeMatrix, 2);
    
    spikeTimes = cell(numUnits, 1);

    for unitIdx = 1:numUnits
        spikeTimes{unitIdx} = find(spikeMatrix(:, unitIdx) == 1) / fs;
    end 

end 