function plotClassificationResults(classificationResults, Params, figFolder)
    
    figure 
    

    numClassifiers = length(classificationResults.classification_models);
    subGroupLevels = classificationResults.subGroupLevels;
    lineHandles = [];
    modelColors = brewermap(numClassifiers, 'Set1');


    if Params.doPairwiseClassification == 1 
        
        numPairs = size(classificationResults.targetPairs, 1);
        subplot_obj = [];
            
        for pairIdx = 1:numPairs
            subplot_obj(pairIdx) = subplot(1, numPairs, pairIdx);

            % calculate baseline 
            numSampleGrp1 = classificationResults.numSampleOfEachPair(pairIdx, :, 1);
            numSampleGrp2 = classificationResults.numSampleOfEachPair(pairIdx, :, 2);
            baseline = max([numSampleGrp1; numSampleGrp2], [], 1) ./ (numSampleGrp1 + numSampleGrp2);
           
            for classifierIdx = 1:numClassifiers
                model_loss = classificationResults.model_loss_per_subgroup(pairIdx, :, classifierIdx);
                model_accuracy = 1 - model_loss;

                if Params.scaleClfPerformanceWbaseline == 1
                    model_accuracy = (model_accuracy - baseline) ./ (1 - baseline);
                end 

                scatter(subGroupLevels, model_accuracy, 40, modelColors(classifierIdx, :),  'filled')
                hold on 

                h = plot(subGroupLevels, model_accuracy, 'LineWidth', 1, 'Color', modelColors(classifierIdx, :));
                    
                lineHandles(classifierIdx) = h;
            end 


            % plot baseline 

            if (Params.scaleClfPerformanceWbaseline == 0) && (Params.downsampleMajorityClass == 0)
                plot(subGroupLevels, baseline, 'LineWidth', 1, 'Color', [0.2, 0.2, 0.2], 'Linestyle', '--');
            end 

            if Params.downsampleMajorityClass == 1
               yline(0.5, 'LineWidth', 1, 'Color', [0.2, 0.2, 0.2], 'Linestyle', '--'); 
            end 

            title(sprintf('%s vs %s', ... 
                classificationResults.targetPairs{pairIdx, 1}, classificationResults.targetPairs{pairIdx, 2}));

            if pairIdx == 1
                legend(lineHandles, classificationResults.classification_models)
            end 

            xlabel('DIV')
            if Params.scaleClfPerformanceWbaseline
                ylabel('Model performance (accuracy rel baseline)')
            else
                ylabel('Model performance (accuracy)')
            end 

        end 
        
        linkaxes(subplot_obj, 'y')
        set(gcf, 'color', 'w')
        set(gcf, 'Position', [0, 0, 1200, 400])

        % Also do a version controlling for baseline 


    else

        for classifierIdx = 1:numClassifiers
            
            model_loss = classificationResults.model_loss_per_subgroup(:, classifierIdx);
            model_accuracy = 1 - model_loss;
            
            scatter(subGroupLevels, model_accuracy, 40, modelColors(classifierIdx, :),  'filled')
            hold on 
    
            h = plot(subGroupLevels, model_accuracy, 'LineWidth', 1, 'Color', modelColors(classifierIdx, :));
            lineHandles(classifierIdx) = h;
    
            hold on 
            
    
        end 
    
        legend(lineHandles, classificationResults.classification_models)
        set(gcf, 'color', 'w')
        xlabel('DIV')
        ylabel('Model performance (accuracy)')
        set(gcf, 'Position', [0, 0, 600, 400])

    end 
    
    fig_name = 'classification_performance';
    savePath = fullfile(figFolder, fig_name);

    if ~isfield(Params, 'oneFigure')
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG);
    else 
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, Params.oneFigure);
    end 

end 