function spikeTimes = findSpikeTimes(spikeTrain, method, samplingRate)
%findSpikeTimes calculate spike times given binary matrix
%   assumes input matrix in the form numSampl x numChannel
%   returns spikeTimes as an array of vectors 

% if method is 'seconds', then spike times are returned in seconds 
% otherwise, it will be returned in terms of sample number 

% according to this, a for loop works about as well as a vectorised
% solution
%https://www.mathworks.com/matlabcentral/answers/229711-using-find-on-each-column-of-a-matrix-independently

spikeTimes = cell(1, size(spikeTrain, 2)); % pre-allocate
for n = 1:size(spikeTrain, 2) 
    spikeTimes{n} = find(spikeTrain(:, n) == 1); 
end 

if strcmp(method, 'seconds')
    % not sure how to do operations on cell array 
    % but feel like there should be more effiecient way of doing this 
    for n = 1:size(spikeTrain, 2) 
        spikeTimes{n} = spikeTimes{n} ./ samplingRate;
    end 
end 


end

