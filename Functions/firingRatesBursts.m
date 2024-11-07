function [Ephys] = firingRatesBursts(spikeMatrix,Params,Info)
%
% Detects firing rate bursts

%

verbose = 0;  % 1 : prints out status, 0 : keep quiet

% get spike counts
FiringRates = full(sum(spikeMatrix))/Info.duration_s;

% calculate firing rates  
active_chanIndex = (FiringRates >= Params.minActivityLevel);
ActiveFiringRates = FiringRates(active_chanIndex);  %spikes of only active channels ('active'= >7)

% Ephys.FR = ActiveFiringRates;
Ephys.FR = FiringRates;
% currently calculates only on active channels (>=FR_threshold)
% stats  
% currently rounds to a specified number of decimal digits
Ephys.FRmean = round(mean(ActiveFiringRates),3);
Ephys.FRstd = round(std(ActiveFiringRates),3);
Ephys.FRsem = round(std(ActiveFiringRates)/(sqrt(length(ActiveFiringRates))),3);
Ephys.FRmedian = round(median(ActiveFiringRates),3);
Ephys.FRiqr = round(iqr(ActiveFiringRates),3);
Ephys.numActiveElec = length(ActiveFiringRates);

%get rid of NaNs where there are no spikes; change to 0
if isnan(Ephys.FRmean)
    Ephys.FRmean=0;
end
if isnan(Ephys.FRmedian)
    Ephys.FRmedian=0;
end



% Network burst detection
[burstMatrix, burstTimes, burstChannels] = burstDetect(spikeMatrix, ...
    Params.networkBurstDetectionMethod, Params.fs, Params.minSpikeNetworkBurst, ...
    Params.minChannelNetworkBurst, Params.bakkumNetworkBurstISInThreshold);

nBursts = size(burstTimes,1);

% Single channel burst detection
burstData = singleChannelBurstDetection(spikeMatrix, Params.singleChannelBurstMinSpike, Params.fs); 

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
    Ephys.numNbursts = size(burstTimes,1);
    Ephys.meanNumChansInvolvedInNbursts = mean(chans_involved);
    Ephys.meanISIWithinNbursts_ms = mean(mean_ISI_w);
    Ephys.meanISIoutsideNbursts_ms = round(mean(ISI_outside)/Params.fs*1000,3);
    Ephys.CVofINBI = round((std(IBIs)/mean(IBIs)),3); %3 decimal places
    Ephys.NBurstRate = round(60*(nBursts/(length(spikeMatrix(:,1))/Params.fs)),3);
    Ephys.fracInNburst = round(sp_in_bst/sum(sum(spikeMatrix)),3);
    Ephys.channelBurstingUnits = burstData.bursting_units;
    Ephys.channelAveBurstRate = burstData.array_burstRate;
    Ephys.channelBurstRate = burstData.all_burstRates;
    Ephys.channelWithinBurstFr = burstData.all_inBurstFRs;
    Ephys.channelBurstDur = burstData.all_burstDurs;
    Ephys.channelAveBurstDur = burstData.array_burstDur;
    Ephys.channelISIwithinBurst = burstData.all_ISIs_within;
    Ephys.channelAveISIwithinBurst = burstData.array_ISI_within;
    Ephys.channeISIoutsideBurst = burstData.all_ISIs_outside;
    Ephys.channelAveISIoutsideBurst = burstData.array_ISI_outside;
    Ephys.channelFracSpikesInBursts = burstData.all_fracsInBursts;
    Ephys.channelAveFracSpikesInBursts = burstData.array_fracInBursts;

    %need to go intro burst detect and edit as it is not deleting the bursts
    %with <5 channels from burstChannels and burstTimes hence they are longer
    %need this for easier plotting of burst
    
else
    if verbose
        disp('no bursts detected')
    end 
    sp_in_bst=0;
    Ephys.meanNBstLengthS = nan; % mean length burst in s
    Ephys.numNbursts = 0;
    Ephys.meanNumChansInvolvedInNbursts = nan;
    Ephys.meanISIWithinNbursts_ms = nan;
    Ephys.meanISIoutsideNbursts_ms = nan;
    Ephys.CVofINBI = nan; %3 decimal places
    Ephys.NBurstRate = 0;
    Ephys.fracInNburst = nan;
    
end