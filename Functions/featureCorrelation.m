function featureCorrelation(nodeLevelData, recordingLevelData, Params)

    %% Look at feature correlation : node level
    subset_lag = 15;
    unique_eGrp = unique(nodeLevelData.('eGrp'));
    num_eGrp = length(unique_eGrp); 
    unique_AgeDiv = unique(nodeLevelData.('AgeDiv'));
    num_AgeDiv = length(unique_AgeDiv);
    
    columnsToExclude = {'eGrp', 'AgeDiv', 'Lag'};
    
    
    f = figure();
    f.Position = [100 100 300*num_AgeDiv 300*num_eGrp];
    for eGrpIdx = 1:num_eGrp
        for AgeDivIdx = 1:num_AgeDiv
    
            subplot(num_eGrp, num_AgeDiv, eGrpIdx+AgeDivIdx-1)
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

    saveFolder = fullfile(Params.priorAnalysisPath, '5_Stats');
    saveName = 'nodeLevelFeatureCorrelation';

    if Params.figMat == 1
        saveas(gcf,fullfile(saveFolder, [saveName '.fig']));
    end
    if Params.figPng == 1
        saveas(gcf,fullfile(saveFolder, [saveName '.png']));
    end
    if Params.figEps == 1
        saveas(gcf,fullfile(saveFolder, [saveName '.eps']));
    end
    
    % if ~isfield(Params, 'oneFigure')
    %     close all
    % else 
    %     set(0, 'CurrentFigure', Params.oneFigure);
    %    clf reset
    % end 
        
    %% Look at feature correlation : recording level
    subset_lag = 15;
    unique_eGrp = unique(recordingLevelData.('eGrp'));
    num_eGrp = length(unique_eGrp); 
    unique_AgeDiv = unique(recordingLevelData.('AgeDiv'));
    num_AgeDiv = length(unique_AgeDiv);
    
    columnsToExclude = {'eGrp', 'AgeDiv', 'Lag'};
    

    f = figure();
    f.Position = [100 100 300*num_AgeDiv 300*num_eGrp];
    for eGrpIdx = 1:num_eGrp
        for AgeDivIdx = 1:num_AgeDiv
    
            subplot(num_eGrp, num_AgeDiv, eGrpIdx+AgeDivIdx-1)
            subset_idx = find(strcmpi(recordingLevelData.eGrp, unique_eGrp(eGrpIdx)) & ...
                              recordingLevelData.('AgeDiv') == unique_AgeDiv(AgeDivIdx) & ...
                              recordingLevelData.('Lag') == subset_lag);
            ageDivRecordingLevel = recordingLevelData(subset_idx, :);
               
            subsetColumnIdx = find(~ismember(ageDivRecordingLevel.Properties.VariableNames, columnsToExclude));
            subsetRecordingLevelData = ageDivRecordingLevel(:,subsetColumnIdx);
            featureCorr = corr(table2array(subsetRecordingLevelData), 'rows','complete');
            columnNames = subsetRecordingLevelData.Properties.VariableNames;
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

    saveFolder = fullfile(Params.priorAnalysisPath, '5_Stats');
    saveName = 'recordingLevelFeatureCorrelation';
    
    if Params.figMat == 1
        saveas(gcf,fullfile(saveFolder, [saveName '.fig']));
    end
    if Params.figPng == 1
        saveas(gcf,fullfile(saveFolder, [saveName '.png']));
    end
    if Params.figEps == 1
        saveas(gcf,fullfile(saveFolder, [saveName '.eps']));
    end
    
    % if ~isfield(Params, 'oneFigure')
    %     close all
    % else 
    %     set(0, 'CurrentFigure', Params.oneFigure);
    %     clf reset
    % end 

end 