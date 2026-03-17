function spikeTimesGrounded = groundSpikeTimes(spikeTimes, channels, electrodesToGround, useName)

%GROUNDSPIKETIMES Summary of this function goes here
%   Detailed explanation goes here

if isstr(electrodesToGround)
    groundElectrodeCell = strsplit(electrodesToGround,',');
    groundElectrodeVec = str2double(groundElectrodeCell);
else
    groundElectrodeVec = groundElectrodeStr;
end 

if useName 
    groundElectrodeIndex = find(ismember(channels, groundElectrodeVec));
else
    groundElectrodeIndex = groundElectrodeVec;
end

spikeTimesGrounded = spikeTimes;

if ~isempty(groundElectrodeIndex)
    for groundIdx = groundElectrodeIndex'
        available_methods = fieldnames(spikeTimes{groundIdx});
    
        for fieldIdx = 1:length(available_methods)
            spikeMethodName = available_methods{fieldIdx};
            spikeTimesGrounded{groundIdx}.(spikeMethodName) = [];
        end
    end
end

end