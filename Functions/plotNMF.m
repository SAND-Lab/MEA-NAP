function plotNMF(experimentMatFolder, plotSaveFolder, Params)
% Plots components and variance explained using non-negative matrix
% factorisation (NMF)
% Parameters
% ----------
% experimentMatFolder : str 
%     path to where experiment mat files are located
% plotSaveFolder : str
%     path to save plot
% Params : struct 
%     pipeline parameter structure
    
    % Plot NMF components
    nCompToPlotIfAvail = 3;  % (maximum) number of NMF components to plot
    
    fileList = dir(fullfile(experimentMatFolder, '*.mat'));

    for nFile = 1:length(fileList)
        filePath = fullfile(fileList(nFile).folder, fileList(nFile).name);
        matFileData = load(filePath);
        close all  % close the loaded figures

        NetMetData = matFileData.NetMet;
        lagFields = fieldnames(NetMetData);
        firstLagFieldData = NetMetData.(lagFields{1});
        
        nCompsAvailable = size(firstLagFieldData.nmfFactors, 2);

        if nCompsAvailable < nCompToPlotIfAvail
            nCompToPlot = nCompsAvailable;
        else 
            nCompToPlot = nCompToPlotIfAvail;
        end 
        
        max_spike_count = max(max(firstLagFieldData.downSampleSpikeMatrix'));
        num_time_samples = size(firstLagFieldData.downSampleSpikeMatrix, 1);
        time_in_sec = 0:num_time_samples / Params.NMFdownsampleFreq; 
        channel_idx = 1:size(firstLagFieldData.downSampleSpikeMatrix, 2);
        nmfFig = figure;
        
        subplot(3, 2, 1)
        minNonZeroSpikeRate = min(firstLagFieldData.downSampleSpikeMatrix(firstLagFieldData.downSampleSpikeMatrix > 0));
        % imagesc(time_in_sec, channel_idx, firstLagFieldData.downSampleSpikeMatrix', [0, max_spike_count]);
        % imagesc(time_in_sec, channel_idx, log10(firstLagFieldData.downSampleSpikeMatrix'), ...
        % [log10(minNonZeroSpikeRate) - 0.1, log10(max_spike_count)]);
        imagesc(time_in_sec, channel_idx, firstLagFieldData.downSampleSpikeMatrix', [0, 1]);
        
        colormap(flipud(gray)) 
        title('Original activity')
        ylabel('Electrode')
        xlabel('Time (s)')
        set(gca,'TickDir','out');
        set(gca,'box','off')
        hold on 
        numPossibleComponents = length(firstLagFieldData.nnmf_residuals);
        subplot(3, 2, 3)
        plot(firstLagFieldData.nnmf_var_explained, 'linewidth', 2);
        hold on
        numCompVarThreshold = size(firstLagFieldData.nmfWeightsVarThreshold, 1);
        plot([numCompVarThreshold, numCompVarThreshold], [0, 1], '--', ... 
            'linewidth', 1, 'Color',[0.5 0.5 0.5]);
        text(numCompVarThreshold + 0.5, 0.1, '95% Variance explained', 'Color', [0.5, 0.5, 0.5])
        xlabel('Number of NMF components')
        ylabel('Variance explained')
        
        if numPossibleComponents > 10
            if mod(numPossibleComponents, 10) == 0
                xticks([1, 10:10:floor(numPossibleComponents/10)*10])
            else
                xticks([1, 10:10:floor(numPossibleComponents/10)*10, numPossibleComponents])
            end
        elseif numPossibleComponents > 1
            xticks([1, numPossibleComponents])
        else
            xticks([1])
        end
        xlim([1, numPossibleComponents])
        ylim([0, 1.1])
        set(gca,'TickDir','out');
        set(gca,'box','off')
        
        subplot(3, 2, 5)
        plot(firstLagFieldData.nnmf_residuals, 'linewidth', 2);
        hold on
        plot(firstLagFieldData.randResidualPerComponent, 'linewidth', 2, 'color', [0.5, 0.5, 0.5]);
        hold on
        y_loc = max([firstLagFieldData.nnmf_residuals; firstLagFieldData.randResidualPerComponent]);
        plot([firstLagFieldData.num_nnmf_components, firstLagFieldData.num_nnmf_components],  ... 
            [0, y_loc], '--', ... 
            'linewidth', 1, 'Color',[0.5 0.5 0.5]);
        
        text(firstLagFieldData.num_nnmf_components + 0.5, 0.9 * y_loc, 'Observed', 'Color', [0 0.4470 0.7410])
        text(firstLagFieldData.num_nnmf_components + 9, 0.9 * y_loc, '>', 'Color', [0, 0, 0])
        text(firstLagFieldData.num_nnmf_components + 10.5, 0.9 * y_loc, 'Random', 'Color', [0.5, 0.5, 0.5])
        xlabel('Number of NMF components')
        ylabel('Mean sq. root residual')
        
        if numPossibleComponents > 10
            if mod(numPossibleComponents, 10) == 0
                xticks([1, 10:10:floor(numPossibleComponents/10)*10])
            else
                xticks([1, 10:10:floor(numPossibleComponents/10)*10, numPossibleComponents])
            end
        elseif numPossibleComponents > 1
            xticks([1, numPossibleComponents])
        else
            xticks([1])
        end
        xlim([1, numPossibleComponents])
        set(gca,'TickDir','out');
        set(gca,'box','off')
        
       

        for nComp = 1:nCompToPlot
    
            subplot(3, 2, nComp*2)

            % nmfProjection = firstLagFieldData.nmfFactors(:, nComp) * ...
            %                 firstLagFieldData.nmfWeights(nComp, :);
            nmfProjection = firstLagFieldData.nmfFactors(:, nComp) * ...
                             firstLagFieldData.nmfWeights(nComp, :);

            % imagesc(time_in_sec, channel_idx, nmfProjection')
            % imagesc(time_in_sec, channel_idx, log10(nmfProjection'), ...
            %      [log10(minNonZeroSpikeRate) - 0.1, log10(max_spike_count)])
             
            imagesc(time_in_sec, channel_idx, nmfProjection', ...
                 [0, 1])
             
            ylabel('Electrode')
            xlabel('Time (s)')
            set(gca,'TickDir','out');
            set(gca,'box','off')
            hold on 
            
            title(sprintf('NMF component %.f', nComp))

        end 
        
        % cbar = colorbar;
        
        set(gcf, 'color', 'w');

        % save figure 
        figFolder = fullfile(plotSaveFolder, ...
                     matFileData.Info.Grp{1}, ...
                     matFileData.Info.FN{1});
        if ~isfolder(figFolder)
            mkdir(figFolder)
        end 
                 
        figFullPath = fullfile(figFolder, 'nNMF');
        pipelineSaveFig(figFullPath, Params.figExt, Params.fullSVG, nmfFig)

        clf(nmfFig)
    end 

end 