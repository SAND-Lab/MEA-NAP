function plotNMF(experimentMatFolder, plotSaveFolder, Params)
    
    % Plot NMF components
    nCompToPlotIfAvail = 3;

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

        nmfFig = figure;
        
        subplot(3, 2, 1)
        imagesc(firstLagFieldData.downSampleSpikeMatrix', [0, max_spike_count]);
        colormap(flipud(gray)) 
        title('Original activity')
        ylabel('Channel')
        xlabel('Time bins')
        set(gca,'TickDir','out');
        set(gca,'box','off')
        hold on 
        
        subplot(3, 2, 3)
        plot(firstLagFieldData.nnmf_var_explained, 'linewidth', 2);
        hold on
        numCompVarThreshold = size(firstLagFieldData.nmfWeightsVarThreshold, 1);
        plot([numCompVarThreshold, numCompVarThreshold], [0, 1], '--', ... 
            'linewidth', 1, 'Color',[0.5 0.5 0.5]);
        text(numCompVarThreshold, 0.1, '95% VE', 'Color', [0.5, 0.5, 0.5])
        xlabel('nNMF components')
        ylabel('Variance explained')
        
        ylim([0, 1.1])
        set(gca,'TickDir','out');
        set(gca,'box','off')
        
        
        
        subplot(3, 2, 5)
        plot(firstLagFieldData.nnmf_residuals, 'linewidth', 2);
        xlabel('nNMF components')
        ylabel('Mean square root residual')
        set(gca,'TickDir','out');
        set(gca,'box','off')
        
       

        for nComp = 1:nCompToPlot
    
            subplot(3, 2, nComp*2)

            % nmfProjection = firstLagFieldData.nmfFactors(:, nComp) * ...
            %                 firstLagFieldData.nmfWeights(nComp, :);
            nmfProjection = firstLagFieldData.nmfFactors(:, nComp) * ...
                             firstLagFieldData.nmfWeights(nComp, :);

            imagesc(nmfProjection', [0, max_spike_count])
            ylabel('Channel')
            xlabel('Time bins')
            set(gca,'TickDir','out');
            set(gca,'box','off')
            hold on 
            
            title(sprintf('NMF component %.f', nComp))

        end 
        
        set(gcf, 'color', 'w');

        % save figure 
        figFullPath = fullfile(plotSaveFolder, ...
                     matFileData.Info.Grp{1}, ...
                     matFileData.Info.FN{1});
        pipelineSaveFig(figFullPath, Params.figExt, Params.fullSVG, nmfFig)

        clf(nmfFig)
    end 

end 