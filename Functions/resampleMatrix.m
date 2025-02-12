function newMatrix = resampleMatrix(ogMatrix, ogFs, newFs)
%RESAMPLEMATRIX Resample matrix given original and new sampling rate
% INPUT
% -----------
% ogMatrix : (numTimePoints, numVariables)
% Reference: 
% https://uk.mathworks.com/help/signal/ug/resampling-uniformly-sampled-signals.html

[p, q] = rat(newFs / ogFs); % get matlab resmapling parameters

ogNumSamples = size(ogMatrix, 1);
numVar = size(ogMatrix, 2); 

newNumSamples = ogNumSamples / ogFs * newFs;
newMatrix = zeros(newNumSamples, numVar) + nan;

for varIdx = 1:numVar
   newMatrix(:, varIdx) = resample(ogMatrix(:, varIdx), p, q); 
end


end

