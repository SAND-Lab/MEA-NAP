function activityStats = calTwopActivityStats(expData, Params)
% Calculates properties related to two-photon activity
% INPUTS 
% ------
% expData : struct 
% 
% RETURNS 
% --------
% activityStats : struct

activityStats = struct();

%% Metrics shared with ephys
% get spike counts
if strcmp(Params.twopActivity, 'peaks')
    numPeaksPerUnit = zeros(1, length(expData.spikeTimes));
    peakISIPerUnit = zeros(1, length(expData.spikeTimes));  % inter-spike-interval
    for unitIndex = 1:length(expData.spikeTimes)
        numPeaksPerUnit(unitIndex) = length(expData.spikeTimes{unitIndex}.peak);
        if length(expData.spikeTimes{unitIndex}.peak) >= 2
            peakISIPerUnit(unitIndex) = mean(diff(expData.spikeTimes{unitIndex}.peak));
        else 
            peakISIPerUnit(unitIndex) = nan;
        end
    end
    FiringRates = numPeaksPerUnit / expData.Info.duration_s;
else 
    FiringRates = sum(expData.(Params.twopActivity), 1) / expData.Info.duration_s;
end

% calculate firing rates  
active_chanIndex = (FiringRates >= Params.minActivityLevel);
ActiveFiringRates = FiringRates(active_chanIndex);  %spikes of only active channels ('active'= >7)

% Ephys.FR = ActiveFiringRates;
activityStats.FR = FiringRates;
% currently calculates only on active channels (>=FR_threshold)
% stats  
% currently rounds to a specified number of decimal digits
activityStats.FRmean = round(mean(ActiveFiringRates),3);
activityStats.FRstd = round(std(ActiveFiringRates),3);
activityStats.FRsem = round(std(ActiveFiringRates)/(sqrt(length(ActiveFiringRates))),3);
activityStats.FRmedian = round(median(ActiveFiringRates),3);
activityStats.FRiqr = round(iqr(ActiveFiringRates),3);
activityStats.numActiveElec = length(ActiveFiringRates);

activityStats.ISImean = nanmean(peakISIPerUnit);
activityStats.ISI = peakISIPerUnit;


%get rid of NaNs where there are no spikes; change to 0
if isnan(activityStats.FRmean)
    activityStats.FRmean=0;
end
if isnan(activityStats.FRmedian)
    activityStats.FRmedian=0;
end

%% Two-photon specific metrics 
% unit level
activityStats.unitHeightMean = nanmean(expData.activityProperties.peakHeights, 2)';  % cell by events
activityStats.unitPeakDurMean = nanmean(expData.activityProperties.peakDurationFrames, 2)' / expData.fs;
activityStats.unitEventAreaMean = nanmean(expData.activityProperties.eventAreas, 2)' / expData.fs;

% recording level 
activityStats.recHeightMean = nanmean(activityStats.unitHeightMean);
activityStats.recPeakDurMean = nanmean(activityStats.unitPeakDurMean);
activityStats.recEventAreaMean = nanmean(activityStats.unitEventAreaMean);




