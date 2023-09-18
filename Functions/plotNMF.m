function plotNMF(experimentMatFolder, plotSaveFolder, Params)
    
    

    fileList = dir(fullfile(experimentMatFolder, '*.mat'));

    for nFile = 1:length(fileList)
        filePath = fullfile(fileList(nFile).folder, fileList(nFile).name);
        matFileData = load(filePath);
        close all  % close the loaded figures

        NetMetData = matFileData.NetMet;
        lagFields = fieldnames(NetMetData);
        firstLagFieldData = NetMetData.(lagFields{1});
        
        nCompsAvailable = size(firstLagFieldData.nmfFactors, 2);
        nCompToPlot = 3;

        if nCompsAvailable < nCompToPlot
            nCompToPlot = nCompsAvailable;
        end 


        nmfFig = figure;
        
        subplot(3, 2, 3)
        imagesc(firstLagFieldData.downSampleSpikeMatrix');
        hold on 
        

        for nComp = 1:nCompToPlot
    
            subplot(3, 2, nComp*2)

            nmfProjection = firstLagFieldData.nmfFactors(:, nComp) * ...
                            firstLagFieldData.nmfWeights(nComp, :);

            imagesc(nmfProjection')
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