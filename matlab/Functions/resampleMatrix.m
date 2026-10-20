function newMatrix = resampleMatrix(ogMatrix, ogFs, newFs)
%RESAMPLEMATRIX Resample matrix given original and new sampling rate
% INPUT
% -----------
% ogMatrix : (numTimePoints, numVariables)
% Reference: 
% https://uk.mathworks.com/help/signal/ug/resampling-uniformly-sampled-signals.html

[p, q] = rat(newFs / ogFs); % get matlab resmapling parameters

numVar = size(ogMatrix, 2); 

testResample = resample(ogMatrix(:,1), p, q);
newNumSamples = length(testResample);
newMatrix = zeros(newNumSamples, numVar) + nan;

for varIdx = 1:numVar
   newMatrix(:, varIdx) = resample(ogMatrix(:, varIdx), p, q); 
end


end

