function combinePlots(plotPathsToCombine, outputFilePath, Params)
%COMBINEPLOTS Summary of this function goes here
%   Detailed explanation goes here

if isfield(Params, 'oneFigure') 
    if ~isgraphics(Params.oneFigure) 
        Params.oneFigure = figure();
    end 
else 
    F1 = figure;
end 



numDivs = length(plotPathsToCombine);




if Params.includeIdvScaledPlotsInCombinedPlots == 1
    
    figHeight = 300 * 2;
    figWidth = figHeight/2 * numDivs;
    set(gcf, 'position', [100, 100, figWidth, figHeight])


    gap = 0.00;
    marg_h = 0.01; 
    marg_w = 0.01;
    
    % make unscaledPlotPathsToCombine 
    unscaledPlotPathsToCombine = {};
    
    for plotNameIdx = 1:length(plotPathsToCombine)
        unscaledPlotPathsToCombine{plotNameIdx} = strrep(plotPathsToCombine{plotNameIdx}, '_scaled', '');
    end 
    
    [ha, pos] = tight_subplot(2, numDivs, gap, marg_h, marg_w);

    for divIdx = 1:numDivs 
        % plot the unscaled version 
        axes(ha(divIdx))
        if isfile(unscaledPlotPathsToCombine{divIdx})
            imshow(unscaledPlotPathsToCombine{divIdx})
        end 
        
        % plot the scaled version
        axes(ha(divIdx + numDivs));
        if isfile(plotPathsToCombine{divIdx})
            imshow(plotPathsToCombine{divIdx});
        end   
    end 
    
else
    figHeight = 300;
    figWidth = figHeight * numDivs;
    set(gcf, 'position', [100, 100, figWidth, figHeight])


    gap = 0.01;
    marg_h = 0.01; 
    marg_w = 0.01;
    
    [ha, pos] = tight_subplot(1, numDivs, gap, marg_h, marg_w);

    for divIdx = 1:numDivs 
        axes(ha(divIdx));
        if isfile(plotPathsToCombine{divIdx})
            imshow(plotPathsToCombine{divIdx});
        end   
    end 
end 

set(gcf, 'color', 'white')

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(outputFilePath, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(outputFilePath, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

close all


end

