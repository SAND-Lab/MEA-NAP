function burstData = singleChannelBurstDetection(raster, N, samplingRate, isiThreshold)
% singleChannelBurstDetection Get bursts within channels using Bakkum method
% INPUTS
% -----------
% raster : T x N matrix
%     number of time samples (T) x number of units (N) binary spike matrix
% N : int
%    minimum number of spikes in spike train to attempt burst detection 
%    if the number of spikes is lower than this number, then default to
%    finding 0 bursts
% samplingRate : int
%     sampling rate of your recording in samples per second (Hz)
% isiThreshold : 'automatic' or float 
%     threshold for ISI_N, if 'automatic' (default), then will find ths value
%     by looking at the distribution of ISI_N times
% OUTPUTS 
% --------
% burstData (structure)
% with the following fields
%     bursting_units : N x 1 vector
%           binary vector where 1 = channel has burst and 0 = no bursts
%     array_burstRate : float
%         median burst rate across all electrodes 
%     all_burstRates : (vector)
%         burst rate for each bursting electrode
%     array_inBurstFR : (float)
%         median (across electrode) of the mean (across burst) firing rate within bursts
%     array_burstDur : (float)
%         median (across electrode) of the mean (across burst) duration
%         of bursts (in milliseconds)
%     all_burstDurs : (vector)
%         the duration of each burst 
%     array_ISI_within : (float)
%         median (across electrode) of the mean (across burst) inter-spike
%         interval within bursts
%     all_ISIs_within : (vector)
%         the inter-spike interval within each burst 
%     burst_times: (vector)
% Returns 
% -------
% burstData
% TODO:
% plot ISI distribution within bursts
% plot ISI between every N spikes 
% plot example electrode bursts
% plot raster for median co-activity and max / some std above median
% CV of ISI 
%
% progressbar('Units done')
warning('off','MATLAB:nearlySingularMatrix');

method = 'Bakkum'; 
ISInThreshold = isiThreshold; % 'automatic';
minChan = 1;
if ~exist('N')
    N = 3;
end

for elec = 1 : size(raster,2)
    
    spikeTrain = raster(:,elec);
    
    if sum(spikeTrain) >= N
         [burstMatrix, burstTimes, burstChannels] = burstDetect(spikeTrain, method, samplingRate,N, minChan, ISInThreshold);
    else
        burstMatrix     = 0;
        burstTimes      = 0;
        burstChannels   = 0;
    end
    burstMatrices{elec} = burstMatrix;
    burstTimes_all{elec} = burstTimes;
    burstChannels_all{elec} = burstChannels;
    clear burstMatrix burstTimes burstChannels
    % progressbar(elec/size(raster,2))
end
% progressbar(elec/size(raster,2))


% analyse bursts
% progressbar('Units done')
for elec = 1:length(burstMatrices)
    %     numBursts(i,1) = length(burstMatrices{i});
    burstMatrix = burstMatrices{elec};
    burstTimes  = burstTimes_all{elec};
    if length(burstMatrix) > 0 & iscell(burstMatrix)
        % get metrics for each burst
        for Bst=1:length(burstMatrix)
            sp_in_bst_all_bursts(Bst)=sum(sum(burstMatrix{Bst,1}));
            sp_times = find(burstMatrix{Bst,1}==1);
            sp_times2= sp_times(2:end);
            ISI_within = sp_times2 - sp_times(1:end-1);
            ISI_w_all_bursts(Bst) = round(nanmean(ISI_within)/samplingRate*1000,3); %in ms with 3 d.p.
            BLength_all_bursts(Bst) = size(burstMatrix{Bst,1},1)/samplingRate*1000; %in ms
            within_bst_FR_all_bursts(Bst) = sp_in_bst_all_bursts(Bst) / BLength_all_bursts(Bst) *1000;
            clear ISI_within sp_times sp_times2 train
        end
        % get mean values across bursts for this electrode/unit
        mean_num_sp_in_bst(elec)        = sum(sp_in_bst_all_bursts) / length(burstMatrix);
        total_num_sp_in_bst(elec)       = sum(sp_in_bst_all_bursts);
        burst_rate_elecs(elec)          = length(burstMatrix) / ((length(raster)/samplingRate)/60); %bursts/min
        mean_inBurst_FR(elec)           = nanmean(within_bst_FR_all_bursts);
        mean_ISI_w(elec)                = nanmean(ISI_w_all_bursts);
        mean_BLength(elec)              = nanmean(BLength_all_bursts);
        
        clear sp_in_bst_all_bursts sp_in_bst_all_bursts BLength_all_bursts within_bst_FR_all_bursts ISI_w_all_bursts
    else
        % disp('no bursts detected')
        mean_num_sp_in_bst(elec)    = NaN;
        total_num_sp_in_bst(elec)   = NaN;
        burst_rate_elecs(elec)      = NaN;
        mean_inBurst_FR(elec)       = NaN;
        mean_ISI_w(elec)            = NaN;
        mean_BLength(elec)          = NaN;
    end
    
    sp_times = find(raster(:,elec)==1);
    sp_times2= sp_times(2:end);
    ISI_outside = sp_times2 - sp_times(1:end-1);
    
    mean_ISI_o(elec)        = round(nanmean(ISI_outside)/samplingRate*1000,3); % in ms
    % frac_spikes_inB(elec)   = total_num_sp_in_bst(elec) / sum(raster(:,elec));
    % progressbar(elec/length(burstMatrices))
    clear burstMatrix sp_in_bst
end

for elec = 1:length(burstMatrices)
    check_elec(1,elec) = ~isempty(burstMatrices{elec});
    check_elec(2,elec) = iscell(burstMatrices{elec});
end
% get ID of all elecs with bursts
bursting_electrodes = find(sum(check_elec) == 2);

% get mean value for each elec/unit and value for each elec/unit
burstData.bursting_units = find(sum(check_elec) == 2); % which neurons or electrodes had bursts

burstData.array_burstRate         = nanmedian(burst_rate_elecs(bursting_electrodes)); %bursts/min
burstData.all_burstRates          = burst_rate_elecs(bursting_electrodes); 

burstData.array_inBurstFR         = full(nanmedian(mean_inBurst_FR(bursting_electrodes))); %in Hz
burstData.all_inBurstFRs          = full(mean_inBurst_FR(bursting_electrodes)); 

burstData.array_burstDur          = nanmedian(mean_BLength(bursting_electrodes)); %in ms
burstData.all_burstDurs           = mean_BLength(bursting_electrodes);

%     burstData.array_fracInBursts      = nanmedian(frac_spikes_inB(bursting_electrodes));
burstData.array_ISI_within        = nanmedian(mean_ISI_w(bursting_electrodes)); %in ms
burstData.all_ISIs_within         = mean_ISI_w(bursting_electrodes);

burstData.array_ISI_outside       = nanmedian(mean_ISI_o(bursting_electrodes)); %in ms
burstData.all_ISIs_outside        = mean_ISI_o(bursting_electrodes); 

burstData.array_fracInBursts      = full((sum(total_num_sp_in_bst(bursting_electrodes))  )  /  sum(sum(raster)));
burstData.all_fracsInBursts       = full((total_num_sp_in_bst(bursting_electrodes)  )  ./  sum(raster(:,bursting_electrodes)));

% get details of each burst for each rec. and elecrtode within that
% rec.
burstData.spike_matrices     = burstMatrices;
burstData.burst_times        = burstTimes_all;

end