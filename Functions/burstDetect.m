function [burstMatrix, burstTimes, burstChannels] = burstDetect(spikeMatrix, method, samplingRate, N, minChannel)
%script from: https://github.com/Timothysit/mecp2
    %last edited by Alex Dunn: August 2019
    
% INPUT 
    % spikeMatrix 
    
    % method 
    % string input specifying the method to do burst detection 
    % main ones are logISI o 
    % defaults to Bakkum
    
    % samplingRate 
    % sampling frequency, defaults to 25kHz (mecp2 project 2017-2018) 
    
    % N is the minimum  number of spike for detecting a burst
    
    % minChannel is the minimum number of channels required to participate
    % in a burst

% OUTPUT 
    % burstMatrix
    % nB x 1 cell. where nB is the number of burst 
    % each cell contain the spike matrix during the burst duration 
    
    % burstTimes
    % nB x 2 matrix, where nB is the number of burst
    % the first column represent the start times (in frames) of the burst 
    % the second column respresent the end times (in frames) of the burst
    
    % burstChannels 
    % nB x 1 cell, each containing a vector listing which channels were
    % active during that burst
    
    
% Original author: Tim Sit 
% Last update: 2020.04.03 bu Alex Dunn

switch nargin
    case 1 
        method = 'Bakkum'; 
        samplingRate = 25000;
    case 2
        samplingRate = 25000;
end 

if strcmp(method, 'Manuel')
    % implements Rich club topology paper method 
    % 1. spike times donwsampled to 1Khz resolution 
    % activity of all electrodes averaged over windows of 10ms
    % into one vector 
    
    duration = 360; 
    downMatrix = downsample(spikeMatrix, 25);
    
    % 10 ms at 1000Hz means 10 samples 
    % 1kHz = 1000 samples / second = 1 sample / millisecond 
    % therefore, if you want each bin to mean 10ms, you need 
    % 720 * 10 bins
    ddownMatrix = downSampleMean(downMatrix, duration * 10); 
    
    % average activity over all electrodes 
    downVec = mean(ddownMatrix, 2);
    
    % 2. vector searched for clusters of activity (< 60ms 
    % inter-event interval) 
    
    % one approach is to calculate the ISI, then search for sequence of > 2
    % where ISI < 60ms 
    % the term 'cluster' is quite vague, email Manuel about this. 
    samplingRate = 1000;
    spikeTimes = findSpikeTimes(downVec, 'seconds', samplingRate);
    spikeISI = findISI(spikeTimes);
    
    % 3. if activity within cluster occur on at least 6 
    % electrodes and contained at least 50 spikes, 
    % population burst defined 
    
    
    % merge bursts closer than 200ms 
    

end 

if strcmp(method, 'LogISI') 
    % based on https://github.com/ellesec/burstanalysis/blob/master/Burst_detection_methods/logisi_pasq_method.R
    % shown by Cotterill et al 2016 to be one of the best
    % Originally developed by Pasquale 2010 
    
    % need to loop this over all all electrodes
    
    
    % step 1, find ISI. In terms of seconds, or time bins???
    % I will go with seconds for now
    spikeTimes = findSpikeTimes(downVec, 'seconds', samplingRate);
    
    % the code for this is migrated to LOgISIbd.m (incomplete as of
    % 20180217)
    % the main principle is to find a good way to determine which ISI is
    % within a burst, and which is between bursts (ie. from the same burst
    % or different burst?)
    
    % xx = bins of current logISIH
    % yy = logISIH 
    
    % smooth yy by operating a local regression using weighted linear least
    % squares
    
    
end 

if strcmp(method, 'Tim')
    % implements my method 
end 

if strcmp(method, 'nno')
    % These are default values
    start_ISI = 0.08; % maximum ISI to start a burst
    continue_ISI = 0.16; % maximum ISI to continue a burstca
    min_nspikes = 3; % minimum number of spikes to count as burst
    burstMatrix =  cell(1, size(spikeMatrix, 2)); % pre-allocate
    for n = 1:length(spikeTimes) 
        burstMatrix{n} = buda_detect_bursts_canonical(spikeTimes{n}, start_ISI, continue_ISI,min_nspikes);
    end    
end 

% if strcmp(method, 'surprise') 
%     minSpike = 3; % do not analyse trains with less than this many spikes
%     for n = 1:length(spikeTimes) 
%         if length(spikeTimes{n}) < minSpike
%             burstMatrix{n} = NaN;
%         else 
%             [burstMatrix{n}.archive_burst_RS, ... 
%                 burstMatrix{n}.archive_burst_length, ... 
%                 burstMatrix{n}.archive_burst_start] = ... 
%                 surpriseBurst(spikeTimes{n}); 
%         if isempty(burstMatrix{n}.archive_burst_RS) % no bursts
%             burstMatrix{n} = NaN; 
%         end 
%     end 
% end 

if strcmp(method, 'Bakkum')
    % https://www.frontiersin.org/articles/10.3389/fncom.2013.00193/full
    % get spike times
    % note that this does network burst. (but can also do channel burst
    % with some modifications)
    
    % combine spike times to a single train 
    
    trainCombine = sum(spikeMatrix, 2);
    
    % make sure it is all either 1 or 0, treat coincident spikes as one
    % spike. Expect this to be quite rate 
    trainCombine(find(trainCombine > 1)) = 1;
    
    
    allSpikeTimes = findSpikeTimes(trainCombine, 'seconds', samplingRate); 
    
    % combine them into a single vector
    
    
    Spike.T = cell2mat(findSpikeTimes(trainCombine, 'seconds', samplingRate));
    
    % convert it to a structure 
    
    
    % 'Spike' is a structure with members: 
    % Spike.T Vector of spike times [sec] 
    % Spike.C (optional) Vector of spike channels 
        % I assume this is the channel causing the spike for that bin 
        % I think it must be just one value, therefore won't accept
        % conincident spike (although they are quite rare I think).
    % 
    % 'N' spikes within 'ISI_N' [seconds] satisfies the burst criteria
    
    % N = 30; % N is the critical paramter here, 
    
    % ISI_N can be automatically selected (and this is dependent on N)
    Steps = 10.^[-5:0.05:1.5]; 
    % exact values of this doens't matter as long as its log scale, covers 
    % the possible spikeISI times,(but we don't care about values about
    % 0.1s anyway)
    plotFig = 0;
    ISInTh = getISInTh(Spike.T, N, Steps, plotFig);
    
    [Burst SpikeBurstNumber] = BurstDetectISIn(Spike, N, ISInTh); 
    
    % Burst.T_start Burst start time [sec] 
    % Burst.T_end Burst end time [sec] 
    % Burst.S Burst size (number of spikes) 
    % Burst.C Burst size (number of channels) 
    
    % burstMatrix = Burst;
    
    
    % now, covert it to a cell structure, where each cell contain a matrix 
    % with the spike trains during a burst period 
    burstCell = cell(length(Burst.S), 1);
    
    
    
    for bb = 1:length(Burst.S)
        T_start_frame = round(Burst.T_start(bb) * samplingRate); % convert from s back to frame 
        T_end_frame = round(Burst.T_end(bb) * samplingRate); 
        burstCell{bb} = spikeMatrix(T_start_frame:T_end_frame, :);
    end 
    
    % burstTimes = [Burst.T_start', Burst.T_end'] % in seconds
    burstTimes = [round(Burst.T_start * samplingRate)', round(Burst.T_end * samplingRate)']; % in frames 
    
     
    % burstMatrix = burstCell; 
    
%     minChannel = 3; 

    % minimum number of channel to be active for a burst to be considered network burst
    % this can be incorporated to the above can can be vectorised
    % active means at least one spike within the time window
    removeBurstIndex = [ ]; 
    burstChannels = cell(length(burstCell), 1); 
    for i = 1:length(burstCell)
        if length( find(sum(burstCell{i}) >= 1)) < minChannel % numChannel active
        removeBurstIndex = [removeBurstIndex, i]; 
        end 
        burstChannels{i} = find(sum(burstCell{i}) >= 1); % find which channels are active
    end 
    
    burstCell(removeBurstIndex, :) = [ ];
    
    %AD remove from channels and burst times as well...
    burstChannels(removeBurstIndex,:) = [ ];
    burstTimes(removeBurstIndex,:) = [ ];
    
    burstMatrix = burstCell; 
    
    % look at which channels are active 
    
    
end 


end