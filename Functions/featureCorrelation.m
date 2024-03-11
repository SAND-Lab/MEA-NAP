function featureCorrelation(nodeLevelData, recordingLevelData, Params, subset_lag, plotSaveFolder)
% Looks at the correlation of features at the node level and the recording
% level
% Parameters
% ----------
% nodeLevelData : 
% recordingLevelData : 
% Params : 
% subset_lag : int 
% Returns 
% -------


%% Look at feature correlation : node level
unique_eGrp = unique(nodeLevelData.('eGrp'));
num_eGrp = length(unique_eGrp); 
unique_AgeDiv = unique(nodeLevelData.('AgeDiv'));
num_AgeDiv = length(unique_AgeDiv);

columnsToExclude = {'eGrp', 'AgeDiv', 'Lag', 'recordingName'};

% TODO: figure creation needs to be tidied up here
f = figure();
f.Position = [100 100 300*num_AgeDiv 300*num_eGrp];
for eGrpIdx = 1:num_eGrp
    for AgeDivIdx = 1:num_AgeDiv

        subplot(num_eGrp, num_AgeDiv, (eGrpIdx-1)*num_AgeDiv + AgeDivIdx)
        subset_idx = find(strcmpi(nodeLevelData.eGrp, unique_eGrp(eGrpIdx)) & ...
                          nodeLevelData.('AgeDiv') == unique_AgeDiv(AgeDivIdx) & ...
                          nodeLevelData.('Lag') == subset_lag);
        ageDivNodeLevel = nodeLevelData(subset_idx, :);
           
        subsetColumnIdx = find(~ismember(ageDivNodeLevel.Properties.VariableNames, columnsToExclude));
        subsetNodeLevelData = ageDivNodeLevel(:,subsetColumnIdx);
        featureCorr = corr(table2array(subsetNodeLevelData), 'rows','complete');
        columnNames = subsetNodeLevelData.Properties.VariableNames;
        imagesc(featureCorr, [-1, 1]);
        set(gca, 'XTick', 1:length(columnNames), 'XTickLabel', columnNames) 
        set(gca, 'YTick', 1:length(columnNames), 'YTickLabel', columnNames) 
        title(sprintf('%s %.f', unique_eGrp{eGrpIdx}, unique_AgeDiv(AgeDivIdx)))
        hold on

    end 

end 
    
cbar = colorbar;
cbar.Position = [0.93, 0.15, 0.01, 0.7];
ylabel(cbar, 'Correlation', 'FontSize', 14);
% set(gcf, 'color', 'w')

saveName = 'nodeLevelFeatureCorrelation';

savePath = fullfile(plotSaveFolder, saveName);

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, f);
else 
    Params.oneFigure = f;
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 
        
%% Look at feature correlation : recording level
unique_eGrp = unique(recordingLevelData.('eGrp'));
num_eGrp = length(unique_eGrp); 
unique_AgeDiv = unique(recordingLevelData.('AgeDiv'));
num_AgeDiv = length(unique_AgeDiv);

columnsToExclude = {'eGrp', 'AgeDiv', 'Lag', 'recordingName'};


f = figure();
f.Position = [100 100 300*num_AgeDiv 300*num_eGrp];
for eGrpIdx = 1:num_eGrp
    for AgeDivIdx = 1:num_AgeDiv

        subplot(num_eGrp, num_AgeDiv, (eGrpIdx-1)*num_AgeDiv + AgeDivIdx)
        subset_idx = find(strcmpi(recordingLevelData.eGrp, unique_eGrp(eGrpIdx)) & ...
                          recordingLevelData.('AgeDiv') == unique_AgeDiv(AgeDivIdx) & ...
                          recordingLevelData.('Lag') == subset_lag);
        ageDivRecordingLevel = recordingLevelData(subset_idx, :);
           
        subsetColumnIdx = find(~ismember(ageDivRecordingLevel.Properties.VariableNames, columnsToExclude));
        subsetRecordingLevelData = ageDivRecordingLevel(:,subsetColumnIdx);
        featureCorr = corr(table2array(subsetRecordingLevelData), 'rows','complete');
        columnNames = subsetRecordingLevelData.Properties.VariableNames;
        imagesc(featureCorr, [-1, 1]);
        
        if length(columnNames) > 20 
            tickmark_fontsize = 4;
        else
            tickmark_fontsize = 9;
        end
        
        set(gca, 'XTick', 1:length(columnNames), 'XTickLabel', columnNames, 'fontsize', tickmark_fontsize, 'TickLabelInterpreter', 'none') 
        set(gca, 'YTick', 1:length(columnNames), 'YTickLabel', columnNames, 'fontsize', tickmark_fontsize, 'TickLabelInterpreter', 'none') 
        title(sprintf('%s %.f', unique_eGrp{eGrpIdx}, unique_AgeDiv(AgeDivIdx)))
        hold on

    end 

end 

cbar = colorbar;
cbar.Position = [0.93, 0.15, 0.01, 0.7];
ylabel(cbar, 'Correlation', 'FontSize', 14);
% set(gcf, 'color', 'w')

saveName = 'recordingLevelFeatureCorrelation';

savePath = fullfile(plotSaveFolder, saveName);

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, f);
else 
    Params.oneFigure = f;
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 

end 