function [stimInfo, stimPatterns] = getStimPatterns(stimInfo, Params)
%GETSTIMPATTERNS Identify unique patterns of stimulation
%   Detailed explanation goes here

% 1 | Get unique stimulation numbers
numElectrode = length(stimInfo);
numStimPerElectrode = zeros(numElectrode, 1);

for elecIndex = 1:length(stimInfo)
    
    numStimPerElectrode(elecIndex) = length(stimInfo{elecIndex}.elecStimTimes);
    
end

numPotentialUniquePatterns = length(unique(numStimPerElectrode));

if strcmp(Params.verboseLevel, 'High')
    fprintf(sprintf('Number of potential patterns detected: %.f \n', numPotentialUniquePatterns));
end

% 2 | start from electrode with least stimulation number to look for
% patterns
stimPatterns = {};
[~, elecIndexSorted] = sort(numStimPerElectrode);

for eIndex = 1:length(stimInfo)
    
    elecIndex  = elecIndexSorted(eIndex);
    
    % check if there is no stimulation, if so, assign to pattern 0 
    if length(stimInfo{elecIndex}.elecStimTimes) == 0
        stimInfo{elecIndex}.pattern = 0;
    else
        [patternId, stimPatterns] = checkStimPattern(stimInfo{elecIndex}.elecStimTimes, stimPatterns);
        stimInfo{elecIndex}.pattern = patternId;
    end 


end





end

