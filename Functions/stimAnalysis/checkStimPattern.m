function [patternId,stimPatterns] = checkStimPattern(candidatePattern,stimPatterns)
%UNTITLED Summary of this function goes here
%   Detailed explanation goes here

% consider these patterns the same if the mean difference in stim times 
% is less than this value
stimTimeDiffThreshold = 0.1; 

if isempty(stimPatterns)
    patternId = 1;
    stimPatterns{patternId} = candidatePattern;
else
    numExistingPatterns = length(stimPatterns);
    stimPatternLengths = zeros(numExistingPatterns, 1);
    for patternIdx = 1:length(stimPatterns)
        stimPatternLengths(patternIdx) = length(stimPatterns{patternIdx});
    end
    
    if ~ismember(length(candidatePattern), stimPatternLengths)
        % new pattern established due to unequal length from existing
        % patterns 
        patternId = numExistingPatterns + 1;
        stimPatterns{patternId} = candidatePattern;
    else
        
        % check each pattern sequence one by one to see if any match 
        matchPattern = nan; 
        for patternIdx = 1:length(stimPatterns)
            
            patternTimeDiffs = abs(candidatePattern - stimPatterns{patternIdx});
            if mean(patternTimeDiffs) < stimTimeDiffThreshold
                matchPattern = patternIdx;
            end

        end

        if isnan(matchPattern)
            % new pattern established because no existing ones match
             patternId = numExistingPatterns + 1;
             stimPatterns{patternId} = candidatePattern;
        else 
            patternId = matchPattern;
            % no motification if stimPatterns necessary
        end


    end

end 

end

