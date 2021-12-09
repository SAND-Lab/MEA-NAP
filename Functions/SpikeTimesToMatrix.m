function [spikeMatrix] = SpikeTimesToMatrix(spikeTimes,spikeDetectionResult,method,Info)

    % Get spike times
    for i = 1:length(spikeTimes)
        if ~isempty(spikeTimes{1,i})
        eval(['spikeTimesStruct.channel' num2str(i) '= spikeTimes{1,i}.(method);']);
        end
    end
    
    % Convert spike times to matrix
    start_time = 0;
    end_time = Info.duration_s;
    sampling_rate = spikeDetectionResult.params.fs; % number of samples per second
    spikeMatrix = spikeTimeToMatrix(spikeTimesStruct, ...
        start_time, end_time, sampling_rate);
    
end