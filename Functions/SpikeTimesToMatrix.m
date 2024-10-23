function [spikeMatrix] = SpikeTimesToMatrix(spikeTimes,fs,method,Info)
    % Convert spike times to spike matrix 
    % TODO: can replace spikeDetectionResult with just fs, since
    % spikeDetectionResult may not always be available
    % Get spike times
    for i = 1:length(spikeTimes)
        if ~isempty(spikeTimes{1,i})
        eval(['spikeTimesStruct.channel' num2str(i) '= spikeTimes{1,i}.(method);']);
        end
    end
    
    % Convert spike times to matrix
    start_time = 0;
    end_time = Info.duration_s;
    spikeMatrix = spikeTimeToMatrix(spikeTimesStruct, ...
        start_time, end_time, fs);
    
end