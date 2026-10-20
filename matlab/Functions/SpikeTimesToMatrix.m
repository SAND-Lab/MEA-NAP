function [spikeMatrix] = SpikeTimesToMatrix(spikeTimes,fs,method,Info)
    % Convert spike times to spike matrix 
    % TODO: can replace spikeDetectionResult with just fs, since
    % spikeDetectionResult may not always be available
    % -------------------------------------------------------------------
    % Change log
    % 2025-01-21 : Returns empty double matrix if no cells in spikeTimes
    
    
    % Get spike times
    for i = 1:length(spikeTimes)
        if ~isempty(spikeTimes{1,i})
        eval(['spikeTimesStruct.channel' num2str(i) '= spikeTimes{1,i}.(method);']);
        end
    end
    
    % Convert spike times to matrix
    start_time = 0;
    end_time = Info.duration_s;
    
    if exist('spikeTimesStruct', 'var')
        spikeMatrix = spikeTimeToMatrix(spikeTimesStruct, ...
        start_time, end_time, fs);
    else 
        bin_edges = start_time:1/fs:end_time;
        num_bins = length(bin_edges) - 1; 
        spikeMatrix = zeros(num_bins, 0);
    end

    
end