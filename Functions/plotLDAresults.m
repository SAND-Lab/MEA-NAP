function plotLDAresults(LDAresults, Params, classificationMode, figFolder)

%% To move : make plots

    if ~isfield(Params, 'oneFigure')
        F1 = figure;
    end 

if strcmp(classificationMode, 'genotypePerDIV')

    genotypePerDIVcell = LDAresults.genotypePerDIV;
    numDiv = size(genotypePerDIVcell, 1);
    set(gcf, 'Position', [0, 0, 400 * numDiv, 400]);

    sz = 100;
    
    %% LDA Projection Plot
    for divIdx = 1:numDiv
        subplot(1, numDiv, divIdx)
    
        % plot LDA first and second component
        % coloring the genotypes of individuals
        uniqueY = unique(genotypePerDIVcell{divIdx, 3});
        numUniqueY = length(uniqueY);
        divLDAprojection = genotypePerDIVcell{divIdx, 2};

        % colors = brewermap(numUniqueY, 'YlGnBu');
        colors = [205,76,42; 
                  64, 57, 112; 
                  17, 184, 225] ./ 255; 

        for uniqueYidx = 1:numUniqueY
            
            sampleIdx = find(ismember(genotypePerDIVcell{divIdx, 3}, uniqueY(uniqueYidx)));
            scatter(divLDAprojection(sampleIdx, 1), divLDAprojection(sampleIdx, 2), ...
                sz, colors(uniqueYidx, :), 'filled');
            hold on
            
            if divIdx == 1
                legend(uniqueY, 'FontSize',14)
            end 

        end 
        
        xlabel('LDA 1');
        ylabel('LDA 2');
        title(sprintf('DIV: %.f', genotypePerDIVcell{divIdx, 1}))

    end
    
    set(gcf, 'color', 'white')
    figName = 'LDAperDIV';
    figPath = fullfile(figFolder, figName);
    % pipelineSaveFig(figPath, Params.figExt, Params.fullSVG)
    figExt = {'.png'};
    fullSVG = 1;
    pipelineSaveFig(figPath, figExt, fullSVG)
    
    %% LDA weights plot 
    figure
    
    for divIdx = 1:numDiv
        
        W = genotypePerDIVcell{divIdx, 4};

        subplot(2, numDiv, divIdx)

        dim_1_weight = W(:, 1);
        if  Params.plotSortedWeights 
            [dim_1_weight_sorted, sort_idx] = sort(dim_1_weight, 'descend');
        else 
            dim_1_weight_sorted = dim_1_weight;
        end 

        bar(dim_1_weight_sorted)
        
        ylabel('LDA 1 weight')
        feature_names = LDAresults.features;
        xticks(1:length(feature_names))

        if Params.plotSortedWeights
            feature_names_sorted = feature_names(sort_idx);
        else 
            feature_names_sorted = feature_names;
        end 

        xticklabels(feature_names_sorted);

        title(sprintf('DIV: %.f', genotypePerDIVcell{divIdx, 1}))
        set(gca, 'TickLabelInterpreter', 'none')
        

        subplot(2, numDiv, numDiv + divIdx);

        dim_2_weight = W(:, 2);
        if  Params.plotSortedWeights 
            [dim_2_weight_sorted, dim_2_sort_idx] = sort(dim_2_weight, 'descend');
        else 
            dim_2_weight_sorted = dim_2_weight;
        end 

        bar(dim_2_weight_sorted)

        ylabel('LDA 2 weight')
        xticks(1:length(feature_names))

        if Params.plotSortedWeights
            dim_2_feature_names_sorted = feature_names(dim_2_sort_idx);
        else 
            dim_2_feature_names_sorted = feature_names;
        end 

        xticklabels(dim_2_feature_names_sorted)

        set(gca, 'TickLabelInterpreter', 'none')


    end

    % text box to indicate what the various metric means 
    % use Params.netMetToCal / Params.networkLevelNetMetToPlot
    % and Params.networkLevelNetMetLabels
    textBoxDim = [0.91, 0.45, 0.3, 0.3];  % xywh 
    textBoxStr = '';
    for featIdx = 1:length(feature_names)
        matchingLabelIdx = find(strcmp(Params.networkLevelNetMetToPlot, feature_names(featIdx)));
        matchingLabel = Params.networkLevelNetMetLabels(matchingLabelIdx);
        featureName = feature_names(featIdx);

        if featIdx < length(feature_names)
            strToAdd = sprintf('%s: %s \\n', featureName{1}, matchingLabel{1});
        else 
            strToAdd = sprintf('%s: %s', featureName{1}, matchingLabel{1});
        end 
        
        textBoxStr = strcat(textBoxStr, strToAdd);

    end 
    annotation('textbox', textBoxDim, 'String', sprintf(textBoxStr), 'FitBoxToText', 'on');
    
    set(gcf, 'Position', [0, 0, 400 * numDiv, 400]);
    set(gcf, 'color', 'white')
    figName = 'LDAweightsPerDIV';
    figPath = fullfile(figFolder, figName);
    % pipelineSaveFig(figPath, Params.figExt, Params.fullSVG)
    figExt = {'.png'};
    fullSVG = 1;
    pipelineSaveFig(figPath, figExt, fullSVG)


else 
    % LDA plot
    subplot(2, 2, 1)
    unique_y = unique(y);
    num_unique_y = length(unique_y);
    
    sz = 100;
    
    legend_labels = {};
    
    colors = brewermap(num_unique_y, 'GnBu');
    
    for n_y = 1:num_unique_y
        
        sample_matching_y = find(y == unique_y(n_y));
        scatter(Y(sample_matching_y, 1), Y(sample_matching_y, 2), sz, colors(n_y, :), 'filled')
        hold on
    
        legend_labels{n_y} = num2str(unique_y(n_y));
    
    end 
    xlabel('LDA 1');
    ylabel('LDA 2')
    leg = legend(legend_labels);
    title(leg, 'DIV')
    
    % Weights onto LDA1 
    subplot(2, 2, 3)
    bar(W(:, 1))
    xticks(1:length(subset_feature_names))
    xticklabels(subset_feature_names)
    xlabel('Features')
    ylabel('Weight')
    title('Weights on LDA 1')
    
    % Weights onto LDA2
    subplot(2, 2, 2)
    bar(W(:, 2))
    xticks(1:length(subset_feature_names))
    xticklabels(subset_feature_names)
    xlabel('Features')
    ylabel('Weight')
    title('Weights on LDA 1')
    
    
    set(gcf, 'color', 'w')
    
    saveName = 'ldaAcrossDIV';
    savePath = fullfile(figSaveFolder, saveName);
    
    if ~isfield(Params, 'oneFigure')
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
    else 
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, Params.oneFigure);
    end 
        
    if ~isfield(Params, 'oneFigure')
        close all
    else 
        set(0, 'CurrentFigure', Params.oneFigure);
        clf reset
    end 
end 

end 