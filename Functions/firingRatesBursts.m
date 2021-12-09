function [Ephys] = firingRatesBursts(spikeMatrix,Params,Info)

spikeCounts = full(sum(spikeMatrix))/Info.duration_s;
%remove ref channel spikes:
spikeCounts(Info.channels == 15) = 0;     
active_chanIndex = spikeCounts>=0.1;
ActiveSpikeCounts = spikeCounts(active_chanIndex);  %spikes of only active channels ('active'= >7)

% calculate firing rates
FiringRates = ActiveSpikeCounts/(length(spikeMatrix)/Params.fs); % firing rate in seconds
Ephys.FR = FiringRates;

% stats
Ephys.FRmean = round(mean(FiringRates),3);
Ephys.FRstd = round(std(FiringRates),3);
Ephys.FRsem = round(std(FiringRates)/(sqrt(length(ActiveSpikeCounts))),3);
Ephys.FRmedian = round(median(FiringRates),3);
Ephys.FRiqr = round(iqr(FiringRates),3);
Ephys.numActiveElec = length(ActiveSpikeCounts);

%get rid of NaNs where there are no spikes; change to 0
if isnan(Ephys.FRmean)
    Ephys.FRmean=0;
end
if isnan(Ephys.FRmedian)
    Ephys.FRmedian=0;
end


method ='Bakkum';
%note, Set N = 30 (min number of bursts)
%ensure bursts are excluded if fewer than 3 channels (see inside burstDetect
%function)
%to change min channels change line 207 of burstDetect.m
%to change N (min n spikes) see line 170 of burstDetect.m
N = 30; minChan = 3;

[burstMatrix, burstTimes, burstChannels] = burstDetect(spikeMatrix, method, Params.fs, N, minChan);
nBursts = length(burstMatrix);

if ~isempty(burstMatrix)
    for Bst=1:length(burstMatrix)
        sp_in_bst(Bst)=sum(sum(burstMatrix{Bst,1}));
        train = sum(burstMatrix{Bst,1},2);%sum across channels
        train(train>1)=1; %re-binarise
        sp_times = find(train==1);
        sp_times2= sp_times(2:end);
        ISI_within = sp_times2 - sp_times(1:end-1);
        mean_ISI_w(Bst) = round(mean(ISI_within)/Params.fs*1000,3); %in ms with 3 d.p.
        chans_involved(Bst) = length(burstChannels{Bst,1});
        
        NBLength(Bst) = size(burstMatrix{Bst,1},1)/Params.fs;
        
        clear ISI_within sp_times sp_times2 train
        
    end
    sp_in_bst=sum(sp_in_bst);
    
    train = sum(spikeMatrix,2);%sum across channels
    train(train>1)=1; %re-binarise
    sp_times = find(train==1);
    sp_times2= sp_times(2:end);
    ISI_outside = sp_times2 - sp_times(1:end-1);
    
    %get IBIs
    end_times = burstTimes(1:end-1,2); %-1 because no IBI after end of last burst
    sta_times = burstTimes(2:end,1); %start from burst start time 2
    IBIs      = sta_times -end_times;
    % calculate CV of IBI and non need to convert from samples to seconds
    % (as relative measure it would be the same)
    
    % NOTE: these are based on the ISI across all channels!!!
    Ephys.meanNBstLengthS = mean(NBLength); % mean length burst in s
    Ephys.numNbursts = length(burstTimes);
    Ephys.meanNumChansInvolvedInNbursts = mean(chans_involved);
    Ephys.meanISIWithinNbursts_ms = mean(mean_ISI_w);
    Ephys.meanISIoutsideNbursts_ms = round(mean(ISI_outside)/Params.fs*1000,3);
    Ephys.CVofINBI = round((std(IBIs)/mean(IBIs)),3); %3 decimal places
    Ephys.NBurstRate = round(60*(nBursts/(length(spikeMatrix(:,1))/Params.fs)),3);
    Ephys.fracInNburst = round(sp_in_bst/sum(sum(spikeMatrix)),3);
    
    %need to go intro burst detect and edit as it is not deleting the bursts
    %with <5 channels from burstChannels and burstTimes hence they are longer
    %need this for easier plotting of burst
    
else
    disp('no bursts detected')
    sp_in_bst=0;
    
    Ephys.meanNBstLengthS = nan; % mean length burst in s
    Ephys.numNbursts = nan;
    Ephys.meanNumChansInvolvedInNbursts = nan;
    Ephys.meanISIWithinNbursts_ms = nan;
    Ephys.meanISIoutsideNbursts_ms = nan;
    Ephys.CVofINBI = nan; %3 decimal places
    Ephys.NBurstRate = nan;
    Ephys.fracInNburst = nan;
    
end