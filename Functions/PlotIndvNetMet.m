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



for e = 1:length(lagval)
    
    % create subfolder
    lagFolderName = fullfile(Params.networkActivityFolder, strcat(num2str(lagval(e)),'mslag'));
    if ~isfolder(lagFolderName)
        mkdir(lagFolderName)
    end 
 
    lagValStr = sprintf('adjM%.fmslag', lagval(e));
    lagNetMet = expData.NetMet.(lagValStr);
    
    requiredMetrics = {'ND', 'NS', 'MEW', 'Eloc', 'BC', 'PC', 'Z'}; 
    if length(intersect(Params.netMetToCal, requiredMetrics)) == length(requiredMetrics)
       electrodeSpecificMetrics(lagNetMet.ND, lagNetMet.NS, lagNetMet.MEW, ...
        lagNetMet.Eloc, lagNetMet.BC, lagNetMet.PC, lagNetMet.Z, lagval, ... 
            e, char(Info.FN), Params, lagFolderName, oneFigureHandle)
    else
        fprintf('Warning: Not enough metrics to make plot 4A.7 \n') 
    end 
    
    
    %% Network plots 
    
    
    adjM = expData.adjMs.(lagValStr);
    
    aNtemp = sum(adjM,1);
    iN = find(aNtemp==0);
    
    % nodeStrength = nansum(adjM, 1);  % where are there sometimes NaN in the adjM?
    % inclusionIndex = find(nodeStrength ~= 0);
    % inclusionIndex = find(abs(nodeStrength) > 1e-6);
    inclusionIndex = lagNetMet.activeNodeIndices;
    
    if isfield(Info, 'CellTypes')
       [cellTypeMatrix, cellTypeNames] = getCellTypeMatrix(Info.CellTypes, expData.channels); 
       cellTypeMatrixActive = cellTypeMatrix(inclusionIndex, :);
    else 
        cellTypeMatrixActive = nan;
        cellTypeNames = nan;
    end
    
    adjM = adjM(inclusionIndex, inclusionIndex);
    coords = originalCoords(inclusionIndex, :);
    Params.netSubsetChannels = originalChannels(inclusionIndex);
    
    % edge threshold for adjM
    edge_thresh = getEdgeThreshold(adjM, Params);
    
    Ci = expData.NetMet.(lagValStr).Ci;
    if length(adjM) > 1
        [On,adjMord] = reorder_mod(adjM,Ci);
    end 
    
    channels = Info.channels;
    channels(iN) = [];
    
    plotPrefixes = {...
        '2', ...
        };
    
    colorMapMetricName = {...
         nan, ...  % nan results in network plot without colormap
        };
    
    colorMapMetricsToPlot = {...
                            nan, ... 
                             };
    
    nodeSizeMetricName = {...
                           'Node degree', ...
                           };
    
    nodeSizeMetricShortForm = {'ND'};
    
    nodeSizeMetricsToPlot = {lagNetMet.ND, ... 
                             };
                         
    
    
    if any(strcmp(Params.unitLevelNetMetToPlot, 'BC'))
        plotPrefixes{end+1} = '3'; 
        nodeSizeMetricsToPlot{end+1} = lagNetMet.ND;
        nodeSizeMetricName{end+1} = 'Node degree';
        nodeSizeMetricShortForm{end+1} = 'ND';
        colorMapMetricsToPlot{end+1} = lagNetMet.BC;
        colorMapMetricName{end+1} = 'Betweenness centrality';
    end 
    
    if any(strcmp(Params.unitLevelNetMetToPlot, 'PC'))
        plotPrefixes{end+1} = '4'; 
        nodeSizeMetricsToPlot{end+1} = lagNetMet.ND;
        nodeSizeMetricName{end+1} = 'Node degree';
        nodeSizeMetricShortForm{end+1} = 'ND';
        colorMapMetricsToPlot{end+1} = lagNetMet.PC;
        colorMapMetricName{end+1} = 'Participation coefficient';
    end 
                         
    if any(strcmp(Params.unitLevelNetMetToPlot, 'Eloc'))
        plotPrefixes{end+1} = '5'; 
        nodeSizeMetricsToPlot{end+1} = lagNetMet.NS;
        nodeSizeMetricName{end+1} = 'Node strength';
        nodeSizeMetricShortForm{end+1} = 'NS';
        colorMapMetricsToPlot{end+1} = lagNetMet.Eloc;
        colorMapMetricName{end+1} = 'Local efficiency';
    end 
    
    % OPTIONAL: also include controllability metrics in plot 
    if any(strcmp(Params.unitLevelNetMetToPlot , 'aveControl'))
        plotPrefixes{end+1} = '10';
        nodeSizeMetricsToPlot{end+1} = lagNetMet.ND;
        nodeSizeMetricName{end+1} = 'Node degree';
        nodeSizeMetricShortForm{end+1} = 'ND';
        colorMapMetricsToPlot{end+1} = lagNetMet.aveControl;
        colorMapMetricName{end+1} = 'Average controllability';
        
    end 

    if any(strcmp(Params.unitLevelNetMetToPlot , 'modalControl'))
        
        plotPrefixes{end+1} = '11';
        nodeSizeMetricsToPlot{end+1} = lagNetMet.ND;
        nodeSizeMetricName{end+1} = 'Node degree';
        nodeSizeMetricShortForm{end+1} = 'ND';
        colorMapMetricsToPlot{end+1} = lagNetMet.modalControl;
        colorMapMetricName{end+1} = 'Modal controllability';
        
    end
                           
    % temp settings for teseting 
    Params.includeChannelNumberInPlots = 0;
    
    if length(adjM) > 1
        
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
            
            if (sum(isnan(colorMapMetricsToPlot{networkPlotIdx}))) && (length(colorMapMetricsToPlot{networkPlotIdx}) == 1)
                
                plotType = 'MEA';
                pNum = sprintf('%s', plotPrefixes{networkPlotIdx});
                figureHandleOriginal = StandardisedNetworkPlot(adjM, coords, edge_thresh, ...
                nodeSizeMetricsToPlot{networkPlotIdx}, nodeSizeMetricShortForm{networkPlotIdx}, plotType, ...
                char(Info.FN),pNum,Params,lagval, e, lagFolderName, figureHandleOriginal, 1, cellTypeMatrixActive, cellTypeNames);
                
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
                plotType, char(Info.FN), pNum, Params, lagval, e, lagFolderName, figureHandleOriginal, 1, ...
                cellTypeMatrixActive, cellTypeNames);
            
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
            if sum(isnan(colorMapMetricsToPlot{networkPlotIdx})) && (length(colorMapMetricsToPlot{networkPlotIdx}) == 1)
                %
                % figureHandleScaled = StandardisedNetworkPlot(adjM, coords, edge_thresh, ...
                % nodeSizeMetricsToPlot{networkPlotIdx}, 'MEA', ...
                % char(Info.FN), sprintf('%s_scaled', plotPrefixes{networkPlotIdx}), Params, lagval, e, lagFolderName);
                plotType = 'MEA';
                pNum = sprintf('%s_scaled', plotPrefixes{networkPlotIdx});
                
                figureHandleScaled = StandardisedNetworkPlot(adjM, coords, edge_thresh, ...
                nodeSizeMetricsToPlot{networkPlotIdx}, nodeSizeMetricShortForm{networkPlotIdx}, plotType, ...
                char(Info.FN), pNum, Params, lagval, e, lagFolderName, figureHandleScaled, ...
                1, cellTypeMatrixActive, cellTypeNames);
                
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
                plotType, char(Info.FN), pNum, Params, lagval, e, lagFolderName, figureHandleScaled, ...
                1, cellTypeMatrixActive, cellTypeNames);
            
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
            if ~sum(isnan(colorMapMetricsToPlot{networkPlotIdx})) && ~isempty(cbOriginal) && isgraphics(cbOriginal)
                h1cbar = colorbar(h(1));
                if isfield(cbOriginal, 'Location')
                    h1cbar.Location = cbOriginal.Location;
                end
                if isfield(cbOriginal, 'Limits')
                    h1cbar.Limits = cbOriginal.Limits;
                end
                if isfield(cbOriginal, 'Label') && isfield(cbOriginal.Label, 'String')
                    h1cbar.Label.String = cbOriginal.Label.String; 
                end
                if isfield(cbOriginal, 'Units')
                    h1cbar.Units = cbOriginal.Units;
                end
                if isfield(cbOriginal, 'Ticks')
                    h1cbar.Ticks = cbOriginal.Ticks;
                end
                if isfield(cbOriginal, 'TickLabels')
                    h1cbar.TickLabels = cbOriginal.TickLabels;
                end
                
                if ~isempty(cbScaled) && isgraphics(cbScaled)
                    h2cbar = colorbar(h(2));
                    
                    if isfield(cbScaled, 'Location')
                        h2cbar.Location = cbScaled.Location;
                    end
                    if isfield(cbScaled, 'Limits')
                        h2cbar.Limits = cbScaled.Limits;
                    end
                    if isfield(cbScaled, 'Label') && isfield(cbScaled.Label, 'String')
                        h2cbar.Label.String = cbScaled.Label.String;
                    end
                    if isfield(cbScaled, 'Units')
                        h2cbar.Units = cbScaled.Units;
                    end
                    if isfield(cbScaled, 'Ticks')
                        h2cbar.Ticks = cbScaled.Ticks;
                    end
                    if isfield(cbScaled, 'TickLabels')
                        h2cbar.TickLabels = cbScaled.TickLabels;
                    end
                end
            end 
            axis off
            
            if isgraphics(figureHandleOriginal) && ~isempty(get(figureHandleOriginal, 'Currentaxes'))
                copyobj(allchild(get(figureHandleOriginal, 'Currentaxes')), h(1));
            end
            
            if isgraphics(figureHandleScaled) && ~isempty(get(figureHandleScaled, 'Currentaxes'))
                copyobj(allchild(get(figureHandleScaled, 'Currentaxes')), h(2));
            end
            
            if ~sum(isnan(colorMapMetricsToPlot{networkPlotIdx}))
               % The default doesn't work sometimes, so hard-coding it now
               if exist('h1cbar', 'var')
                   h1cbar.Position = [0.51, 0.1109, 0.0123, 0.8145];
               end
               if exist('h2cbar', 'var')
                   h2cbar.Position = [0.95, 0.1109, 0.0123, 0.8145];
               end
            end
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
        
        
        % Plot 4A.6: simple circular network plot
        % Updated to be coloured by which module each node belongs to
        if Params.timeProcesses
            fprintf('Plotting circular network \n')
            tic
        end 
        
        
        NDord = lagNetMet.ND(On);
        % StandardisedNetworkPlot(adjMord, coords, edge_thresh, NDord, ...
        %     'circular', char(Info.FN),'6',Params,lagval,e, lagFolderName, oneFigureHandle);
        
        moduleID = lagNetMet.Ci(On); 
        Params.metricsMinMax.Ci = moduleID;
        % close all
        oneFigureHandle = checkOneFigureHandle(Params, oneFigureHandle);
        
        plotInactiveNodesInCircPlot = 1;

        if plotInactiveNodesInCircPlot == 1
            originaladjM = expData.adjMs.(lagValStr);
            adjMordWithEmpty = zeros(length(originaladjM), length(originaladjM)); 
            numActiveNodes = length(adjMord);
            adjMordWithEmpty(1:numActiveNodes, 1:numActiveNodes) = adjMord; 
            moduleIDwithEmpty = zeros(length(originaladjM), 1); 
            moduleIDwithEmpty(1:numActiveNodes) = moduleID;
            
            NDordwithEmpty = zeros(length(originaladjM), 1);
            NDordwithEmpty(1:numActiveNodes) = NDord;
            
            StandardisedNetworkPlotNodeColourMap(adjMordWithEmpty, coords, edge_thresh, ...
                 NDordwithEmpty, 'Node degree', ...
                 moduleIDwithEmpty, 'Module', ...
                'circular', char(Info.FN), '6', Params, lagval, e, lagFolderName, oneFigureHandle);
        else 
        
            StandardisedNetworkPlotNodeColourMap(adjMord, coords, edge_thresh, ...
                 NDord, 'Node degree', ...
                 moduleID, 'Module', ...
                'circular', char(Info.FN), '6', Params, lagval, e, lagFolderName, oneFigureHandle);
        end 
        
            
        
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

