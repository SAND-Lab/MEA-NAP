function twopActivityMatrix = get2pActivityMatrix(F, denoisedF, spks, spikeTimes, resamplingRate, Info, Params)
%GET2PACTIVITYMATRIX Summary of this function goes here
%   Detailed explanation goes here
% twopActivityMatrix (numTimeSmaples, numUnits)
if strcmp(Params.twopActivity, 'F')
    twopActivityMatrix = double(F);
elseif strcmp(Params.twopActivity, 'denoised F')
    twopActivityMatrix = double(denoisedF);
elseif strcmp(Params.twopActivity, 'spks')
    twopActivityMatrix = double(spks);
elseif strcmp(Params.twopActivity, 'peaks')
    twopActivityMatrix = SpikeTimesToMatrix(spikeTimes, resamplingRate, 'peak', Info);
end

end

