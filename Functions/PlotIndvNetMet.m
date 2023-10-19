function PlotIndvNetMet(expData, Params, Info, originalCoords, originalChannels, oneFigureHandle)
%PLOTINDVNETMET Creates network plot for individual recordings
% Parameters
% ----------
% expData : struct 
% Params : struct 
% Info : struct
% 
% Returns 
% ----------
    

%% electrode specific half violin plots
 
lagval = expData.Params.FuncConLagval;

% edge threshold for adjM
edge_thresh = 0.0001;

for e = 1:length(lagval)
    
    % create subfolder
    lagFolderName = fullfile(Params.networkActivityFolder, strcat(num2str(lagval(e)),'mslag'));
    if ~isfolder(lagFolderName)
        mkdir(lagFolderName)
    end 
 
    lagValStr = sprintf('adjM%.fmslag', lagval(e));
    lagNetMet = expData.NetMet.(lagValStr);
    
    electrodeSpecificMetrics(lagNetMet.ND, lagNetMet.NS, lagNetMet.MEW, ...
        lagNetMet.Eloc, lagNetMet.BC, lagNetMet.PC, lagNetMet.Z, lagval, ... 
            e, char(Info.FN), Params, lagFolderName, oneFigureHandle)
    
    %% Network plots 
    
    
    adjM = expData.adjMs.(lagValStr);
    
    aNtemp = sum(adjM,1);
    iN = find(aNtemp==0);
    
    nodeStrength = nansum(adjM, 1);  % where are there sometimes NaN in the adjM?
    % inclusionIndex = find(nodeStrength ~= 0);
    inclusionIndex = find(abs(nodeStrength) > 1e-6);
    adjM = adjM(inclusionIndex, inclusionIndex);
    coords = originalCoords(inclusionIndex, :);
    Params.netSubsetChannels = originalChannels(inclusionIndex);
    
    Ci = expData.NetMet.(lagValStr).Ci;
    if length(adjM) > 0
        [On,adjMord] = reorder_mod(adjM,Ci);
    end 
    
    channels = Info.channels;
    channels(iN) = [];
    
    plotPrefixes = {...
        '2', ...
        '3', ...
        '4', ...
        '5', ...
        };
    
    colorMapMetricName = {...
         nan, ...  % nan results in network plot without colormap
        'Betweeness centrality', ... 
        'Participation coefficient', ...
        'Local efficiency', ... 
        };
    
    colorMapMetricsToPlot = {...
                            nan, ... 
                            lagNetMet.BC, ...
                            lagNetMet.PC, ...
                            lagNetMet.Eloc, ...
                             };
    
    nodeSizeMetricName = {...
                           'Node degree', ...
                           'Node degree', ... 
                           'Node degree', ... 
                           'Node strength', ...
                           };
                       
    nodeSizeMetricsToPlot = {lagNetMet.ND, ... 
                             lagNetMet.ND, ...
                             lagNetMet.ND, ... 
                             lagNetMet.NS, ...
                             };
    
    % OPTIONAL: also include controllability metrics in plot 
    if any(strcmp(Params.unitLevelNetMetToPlot , 'aveControl'))
        plotPrefixes{end+1} = '10';
        nodeSizeMetricsToPlot{end+1} = lagNetMet.ND;
        nodeSizeMetricName{end+1} = 'Node degree';
        colorMapMetricsToPlot{end+1} = lagNetMet.aveControl;
        colorMapMetricName{end+1} = 'Average controllability';
        
    end 

    if any(strcmp(Params.unitLevelNetMetToPlot , 'modalControl'))
        
        plotPrefixes{end+1} = '11';
        nodeSizeMetricsToPlot{end+1} = lagNetMet.ND;
        nodeSizeMetricName{end+1} = 'Node degree';
        colorMapMetricsToPlot{end+1} = lagNetMet.modalControl;
        colorMapMetricName{end+1} = 'Modal controllability';
        
    end
                           
    % temp settings for teseting 
    Params.includeChannelNumberInPlots = 0;
    
    if length(adjM) > 0
        
        % Loop through the metrics of interest to plot
        for networkPlotIdx = 1:length(colorMapMetricsToPlot)
            
            if Params.timeProcesses
                fprintf('Plotting network scaled to individual recording \n')
                tic
            end 
            
            Params.useMinMaxBoundsForPlots = 0;
            
            figureHandleOriginal = figure('visible', 'off');
            
            % make unscaledPlotPathsToCombine 
            plotPathsToCombine = {};

            % for plotNameIdx = 1:length(plotPathsToCombine)
            %     unscaledPlotPathsToCombine{plotNameIdx} = strrep(plotPathsToCombine{plotNameIdx}, '_scaled', '');
            %  end 

            if sum(isnan(colorMapMetricsToPlot{networkPlotIdx}))
                
                plotType = 'MEA';
                pNum = sprintf('%s', plotPrefixes{networkPlotIdx});
                figureHandleOriginal = StandardisedNetworkPlot(adjM, coords, edge_thresh, ...
                nodeSizeMetricsToPlot{networkPlotIdx}, plotType, ...
                char(Info.FN),pNum,Params,lagval,e, lagFolderName, figureHandleOriginal);
                
                figName = strcat([pNum, '_', plotType, '_NetworkPlot.png']);
                figPath = fullfile(lagFolderName, figName);
                plotPathsToCombine{1} = figPath;
            
                % Temp test 
                % h(1) = StandardisedNetworkPlot(adjM, coords, edge_thresh, ...
                % nodeSizeMetricsToPlot{networkPlotIdx}, 'MEA', ...
                % char(Info.FN),sprintf('%s', plotPrefixes{networkPlotIdx}),Params,lagval,e, lagFolderName, h(1), 0);
            else 
                plotType = 'MEA';
                pNum = sprintf('%s', plotPrefixes{networkPlotIdx});
                zname = nodeSizeMetricName{networkPlotIdx};
                z2name = colorMapMetricName{networkPlotIdx};
                
                [figureHandleOriginal, cbOriginal] = StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ...
                nodeSizeMetricsToPlot{networkPlotIdx}, zname, ...
                colorMapMetricsToPlot{networkPlotIdx}, z2name, ...
                plotType, char(Info.FN), pNum, Params, lagval, e, lagFolderName, figureHandleOriginal);
            
                figName = strcat([pNum,'_',plotType,'_NetworkPlot',zname,z2name]);
                figName = strrep(figName, ' ', '');
                figPath = fullfile(lagFolderName, [figName '.png']);
                plotPathsToCombine{1} = figPath;
                % [figureHandleOriginal, cbOriginal] = StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ...
                % nodeSizeMetricsToPlot{networkPlotIdx}, nodeSizeMetricName{networkPlotIdx}, ...
                % colorMapMetricsToPlot{networkPlotIdx}, colorMapMetricName{networkPlotIdx}, ...
                % 'MEA', char(Info.FN), sprintf('%s', plotPrefixes{networkPlotIdx}), Params, lagval, e, lagFolderName);
            end 
            
            if Params.timeProcesses
                toc
            end 
            
            if Params.timeProcesses
                fprintf('Plotting network scaled to all recordings \n')
                tic
            end 

            figureHandleScaled = figure('visible', 'off');
            Params.useMinMaxBoundsForPlots = 1;
            if sum(isnan(colorMapMetricsToPlot{networkPlotIdx}))
                %
                % figureHandleScaled = StandardisedNetworkPlot(adjM, coords, edge_thresh, ...
                % nodeSizeMetricsToPlot{networkPlotIdx}, 'MEA', ...
                % char(Info.FN), sprintf('%s_scaled', plotPrefixes{networkPlotIdx}), Params, lagval, e, lagFolderName);
                plotType = 'MEA';
                pNum = sprintf('%s_scaled', plotPrefixes{networkPlotIdx});
                
                figureHandleScaled = StandardisedNetworkPlot(adjM, coords, edge_thresh, ...
                nodeSizeMetricsToPlot{networkPlotIdx}, plotType, ...
                char(Info.FN), pNum, Params, lagval, e, lagFolderName, figureHandleScaled);
                
                figName = strcat([pNum, '_', plotType, '_NetworkPlot.png']);
                figPath = fullfile(lagFolderName, figName);
                plotPathsToCombine{2} = figPath;
            else 
                plotType = 'MEA';
                pNum = sprintf('%s_scaled', plotPrefixes{networkPlotIdx});
                zname = nodeSizeMetricName{networkPlotIdx};
                z2name = colorMapMetricName{networkPlotIdx};
                [figureHandleScaled, cbScaled] = StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ...
                 nodeSizeMetricsToPlot{networkPlotIdx}, zname, ...
                 colorMapMetricsToPlot{networkPlotIdx}, z2name, ...
                plotType, char(Info.FN), pNum, Params, lagval, e, lagFolderName, figureHandleScaled);
            
                figName = strcat([pNum,'_',plotType,'_NetworkPlot',zname,z2name]);
                figName = strrep(figName, ' ', '');
                figPath = fullfile(lagFolderName, [figName '.png']);
                plotPathsToCombine{2} = figPath;
                
                % [figureHandleScaled, cbScaled] = StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ...
                %  nodeSizeMetricsToPlot{networkPlotIdx}, nodeSizeMetricName{networkPlotIdx}, ...
                %  colorMapMetricsToPlot{networkPlotIdx}, colorMapMetricName{networkPlotIdx}, ...
                % 'MEA', char(Info.FN), sprintf('%s_scaled', plotPrefixes{networkPlotIdx}), Params, lagval, e, lagFolderName);
            end 
            
            if Params.timeProcesses
                toc
            end 
            
            if Params.timeProcesses
                fprintf('Combining the two network plots \n')
                tic
            end 
            
            % Try just merging two PNGs
            % TEMP TEST
            %{
            combinedFigure = figure('visible','off'); % create a new figure for saving and printing
            p =  [50   100   660*2 + 400  550];
            set(combinedFigure, 'Position', p);
            
            % h(1) = subplot(1, 2, 1);
            % axis off
            % h(2) = subplot(1, 2, 2);
            % PNG MERGE strategy
            gap = 0.00;
            marg_h = 0.01; 
            marg_w = -0.01;
            [ha, pos] = tight_subplot(1, 2, gap, marg_h, marg_w);
            axes(ha(1));
            imshow(plotPathsToCombine{1});
            axes(ha(2));
            imshow(plotPathsToCombine{2});
            %}
            
            %
            combinedFigure = figure('visible','off'); % create a new figure for saving and printing
            p =  [50   100   660*2 + 400  550];
            set(combinedFigure, 'Position', p);
            h(1) = subplot(1, 2, 1);
            axis off
            h(2) = subplot(1, 2, 2);
            if ~sum(isnan(colorMapMetricsToPlot{networkPlotIdx}))
                h1cbar = colorbar(h(1));
                h1cbar.Location = cbOriginal.Location;
                h1cbar.Limits = cbOriginal.Limits;
                h1cbar.Label.String = cbOriginal.Label.String; 
                h1cbar.Units = cbOriginal.Units;
                h1cbar.Ticks = cbOriginal.Ticks;
                h1cbar.TickLabels = cbOriginal.TickLabels;
                
                h2cbar = colorbar(h(2));
                h2cbar.Location = cbScaled.Location;
                h2cbar.Limits = cbScaled.Limits;
                h2cbar.Label.String = cbScaled.Label.String;
                h2cbar.Units = cbScaled.Units;
                h2cbar.Ticks = cbScaled.Ticks;
                h2cbar.TickLabels = cbScaled.TickLabels;
            end 
            axis off
            
            copyobj(allchild(get(figureHandleOriginal, 'Currentaxes')), h(1)); 
            copyobj(allchild(get(figureHandleScaled, 'Currentaxes')), h(2)); 
            %}
            
            set(gcf, 'color', 'white');
            
            if isnan(colorMapMetricName{networkPlotIdx})
                figPath = fullfile(lagFolderName, ...
                sprintf('%s_combined_MEA_NetworkPlot', plotPrefixes{networkPlotIdx}));
            else
                figPath = fullfile(lagFolderName, ...
                sprintf('%s_combined_MEA_NetworkPlot_%s', plotPrefixes{networkPlotIdx}, ... 
                colorMapMetricName{networkPlotIdx}));
            end
            
            pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, combinedFigure);
            
            if Params.timeProcesses
                toc
            end 
            
            
            
            close(figureHandleOriginal) 
            close(figureHandleScaled) 
            close(combinedFigure)
            
            % delete(figureHandleOriginal) 
            % delete(figureHandleScaled) 
            % delete(combinedFigure)
            % fprintf(sprintf('Current figure number: %.f \n', get(gcf, 'Number')))
        end
        
        
        % simple circular network plot
        if Params.timeProcesses
            fprintf('Plotting circular network \n')
            tic
        end 
        
        NDord = lagNetMet.ND(On);
        StandardisedNetworkPlot(adjMord, coords, edge_thresh, NDord, ...
            'circular', char(Info.FN),'6',Params,lagval,e, lagFolderName, oneFigureHandle);
        
        if Params.timeProcesses
            toc
        end 
        
        if strcmp(Params.verboseLevel, 'High')
            figureHandleList = findall(groot,'Type','figure');
            fprintf(sprintf('Number of figure handles: %.f \n', numel(figureHandleList)));
        end 
        
    end 
    

    
    
end 


end

