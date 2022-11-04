function [hub_peripheral_xy, hub_metrics, hub_score_index] = ... 
    fcn_find_hubs_wu(channels, raster, adjM, fs)

percentile_threshold    = 80; % percent
fr_thresh               = 0.1; % Hz
makePlots = 0;  % whether to make plots from this function (off for now)
% calculate nodal metrics based on Schroeter 2015
% these metrics are: nodal strength, betweenness centrality, local efficiency, and participation coefficient
%{
INPUT 
----------
channels : (N x 1 vector)
    N x 1 vector where N is the number of channels, each entry is the
    unique integer index denoting the identity (and position) of the
    channel
raster : (T x N matrix)
    number of samples (T) x number of units (N) binary spike matrix
adjM : (N x N matrix)
    N x N matrix where N is the number of channels / units / nodes in the
    network. Entry adjM(i, j) is the weight between node i and node j.
fs : (int)
    sampling frequency of the recording 
percentile_threshold : (float)
fr_thresh : (float)

OUTPUT 
----------

% TODO: rename things to something like zHub as the calculation 
% is based on z-scores

hub_peripheral_xy : (2 x 1 vector)
    
hub_metrics :  (structure)
    structure with fields:
        metrics : 
        metrics_norm : (N x 7 matrix)
            where N is the number of nodes in the network 
            each columnn is a particular network features 
            this is similar to metrics, except that values are z-scored 
            across all nodes
        metric_names : 
hub_score_index : (structure)
    
%}

% Calculate path length is element-wise inverse of adjacency matrix
smallFactor = 0.01; % prevent division by zero
pathLengthNetwork = 1 ./ (adjM + smallFactor); 

% get module affiliations
M     = community_louvain(adjM);
% list metric name strings
metric_names = {'Node strength','Betweenness centrality','Local efficiency', ... 
                 'Participation coefficient','Communicability'};
metrics.strengths   = strengths_und(adjM);
BC = betweenness_wei(pathLengthNetwork); 
BC = BC/((length(adjM)-1)*(length(adjM)-2)); % scale BC by size of network so range is 0 - 1
metrics.BC          = BC;
metrics.Eloc        = efficiency_wei(adjM,2);
metrics.PC          = participation_coef(adjM,M);
metrics.Comm        = sum(getCommunicability(adjM,1,1)); % input 1 means normalise to [0 1] and input ; sum to total communicability for each node

% normalised coefficient takes too long
% plot distribution of normalised and original part_coef and corr between
% these
% PC_norm = participation_coef_norm(adjM,M)
% [r p] = corr(PC(PC>0), PC_norm(PC>0));
% figure; scatter(PC(PC>0), PC_norm(PC>0)); aesthetics; xlabel('Participation coefficient (PC)');ylabel('PC normalised to module size');title(sprintf('r=%g, p=%g',round(r,3),round(p,4)))
% figure; h=histogram(PC(PC>0),'BinWidth',0.01);hold on; h2=histogram(PC_norm(PC>0),'BinWidth',0.01); aesthetics; l=legend('Participation coefficient','Normalised to module size','Box','off','Location','north');

metric_matrix = [metrics.strengths' metrics.BC metrics.Eloc metrics.PC metrics.Comm'];

% method 1: normalise to max. of this recording
% norm_metric_matrix = [metrics.strengths' metrics.BC metrics.Eloc metrics.PC] ...
%     ./ [max(metrics.strengths) max(metrics.BC) max(metrics.Eloc) max(metrics.PC)];

% method 2: get z scores for each metric
norm_metric_matrix = zscore(metric_matrix);

% get percentile across all metrics, one value for each node
% do this on normalised metrics
% Y = prctile(norm_metric_matrix ,percentile_threshold,1);
% sort by mean normalised metric value
Y = mean(norm_metric_matrix,2);
% get top 5 nodes
% B is the mean normalised metric, I is the index of the node
[B,I] = sort(Y,'descend');
channels_sorted = channels(I); % descending order
top5_channel_xy = channels_sorted(1:5);
disp('Stimulate:'); disp(num2str(top5_channel_xy))


%% plot nodes normalised value for each metric in overall percentile order

% add firing rate
rec_duration = size(raster, 1) / fs;
fr = sum(raster)./rec_duration;
% method one: normalise to max fr (but this biased by outliers)
% fr_norm = fr ./ max(fr);
% sqrt fr to deal with skewed distribution and get z scores
fr_norm = zscore(sqrt(fr));

 % get most peripheral node that is still active
% max find B>0 gives the lowest scoring channel in terms of all metrics
% that is greater than 0. I of this gives where in the channels variable
% this metric came from. This index of channels gives the xy coord
bottom_active_channel = channels(I(max(find(fr(I)>fr_thresh))));

if makePlots

    p = [642 386 637 255];
    if ~isfield(Params, 'oneFigure')
        F1 = figure;
        F1.Position = p;
    else 
        set(0, 'DefaultFigurePosition', p)
        set(Params.oneFigure, 'Position', p);
    end 
       
    % plot metrics sorted in order of hubness
    for metric = 1:length(metric_names)
        hold on; plot(norm_metric_matrix(I,metric))
    end
    
    hold on; 
    p=plot(fr_norm(I),'LineWidth',2);
    % make firing rate transparent
    p.Color(4) = 0.3;
    % add mean
    plot(mean(norm_metric_matrix(I,:),2),':k','LineWidth',2)
    % aesthetics
    ylabel('Z-score')
    xlabel({'Electrodes', '\itsorted for hubness'})
    aesthetics
   
    % add markers for hub and peripheral node to stim
    hold on; 
    p=plot([find(channels_sorted==top5_channel_xy(1)),find(channels_sorted==bottom_active_channel)],...
        [max(norm_metric_matrix(:)) max(norm_metric_matrix(:))],'vk','MarkerFaceColor','k','MarkerSize',3);
    % add legend etc
    l=legend([metric_names 'Firing rate' 'Metric mean','Stimulated nodes'],'box','off');
    l.Title.String = 'Normalised metrics';
    l.Location = 'eastoutside';
    
    title(sprintf('Stimulate nodes(xy): %g %g \n',top5_channel_xy(1),bottom_active_channel));
    
end 

% TODO: save these plots

% get temporal raster sorted in order of hubness
% figure;
% imagesc(downSampleSum(full(raster(:,I)), rec_duration)'); 
% caxis([0 50]);
% cb = colorbar; cb.Label.String = 'Spike rate (Hz)' ; aesthetics
% xlabel('Time (s)');ylabel({'Electrodes', '\itsorted for hubness'});
% % verify with heatmap
% figure;
% TODO: cannot find this function 
% seems to be called in getHeatMaps_AD.m as well 
% https://github.com/alexander-w-e-dunn/MEA/blob/71275f258326998d06ae3dcd70a84a1855c55719/getHeatMaps_AD.m
% can skip this
% makeHeatMap_AD(raster, 'logr',channels,fs) %choose 'rate' or 'count' or 'logc'
% save figure?
%{
output figure with panel temporal raster plot, ordered in percentile ranks
firing rate heatmap
correlation between firing rate and metrics
%}
% % or, for each node, get percentile for each metric
% for node = 1:length(channels)
%     for metric = 1:length(fieldnames(metrics))
%         percentiles(node,metric) = pct(
%     end
% end

% get xy coordinate of the hub and peripheral nodes
hub_peripheral_xy           = [top5_channel_xy(1),bottom_active_channel];
hub_metrics.metrics         = [metric_matrix(I,:) fr(I)'];
hub_metrics.metrics_norm    = [norm_metric_matrix(I,:) fr_norm(I)' mean(norm_metric_matrix(I,:),2)];
hub_metrics.metric_names    = [metric_names 'Firing rate' 'Normalised metric mean'];
hub_metrics.metrics_unsorted = metric_matrix;
hub_metrics.metrics_norm_unsorted = norm_metric_matrix;
hub_score_index.xy          = channels(I);
hub_score_index.label       = 'Channel xy coordinates in descending order of "hubness" i.e. mean hub metric; most hub like is first';

end

