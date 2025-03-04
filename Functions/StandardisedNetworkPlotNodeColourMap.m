function [figureHandle, colorbar_handle] = StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, z, ...
    zname, z2, z2name, plotType, FN, pNum, Params, lagval, e, figFolder, ...
    oneFigureHandle, normalizeLineWidthByCellType, cellTypeMatrixActive, cellTypeNames)
%
% script to plot the graph network 
% 
% Parameters
% ----------
%   adjM : double array 
%          adjacency matrix 
%   coords : double array 
%          electrode/node coordinates (x and y, num nodes * 2)
%   edge_thresh : float 
%      a value between 0 and 1 for the minimum correlation to plot
%   z : char 
%       the network metric used to determine the size of the plotted nodes
%       eg: node degree or node strength
%   zname : char
%      name of the z network metric
%   z2 : char
%       the network metric used to determine the colour of the plotted
%       nodes, eg: betweeness centrality or participation coefficient
%   z2name - name of the z2 network metric
%   plotType : char 
%        'MEA' to plot nodes with their respective electrode
%       coordinates 
%       'circular' to plot nodes in a circle
%   FN : char 
%        name of file/recording
%   pNum : char
%        number (in character or string format) to precede name of figure
%        when it is saved
%   Params : struct
%   normalizeLineWidthByCellType : bool (optional)
%        whether to normalize line width by cell type
%   cellTypeMatrixActive : matrix (optional)
%        matrix of cell types
%   cellTypeNames : cell array (optional)
%        names of cell types
%        
% Returns 
% -------
% figureHandle : handle to the figure
% colorbar_handle : handle to the colorbar
% 
% author RCFeord August 2020
% 

% Default values for optional parameters
if nargin < 18
    cellTypeNames = {};
end
if nargin < 17
    cellTypeMatrixActive = [];
end
if nargin < 16
    normalizeLineWidthByCellType = 0;
end

%% plot
p =  [50 100 700 600];

if Params.showOneFig
    if isgraphics(oneFigureHandle)
        set(oneFigureHandle, 'OuterPosition', p);
        figureHandle = oneFigureHandle;
    else 
        figureHandle = figure;
        set(figureHandle, 'OuterPosition', p);
    end 
else
   figureHandle = figure;
   figureHandle.OuterPosition = p;
end 

aesthetics; axis off; hold on

% title(sprintf('Active electrode map %s, threshold = %.2f', FN, edge_thresh))
title(strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag'))
%% coordinates

xc = coords(:,1);
yc = coords(:,2);

%% add edges

threshMax = max(adjM(:));
minNonZeroEdge = min(min(adjM(adjM>0))); 

if strcmp(plotType,'MEA')
    
    max_ew = 4; % maximum edge width for plotting
    min_ew = 0.001; % min edge width
    light_c = [0.8 0.8 0.8]; % lightest edge colour
    
    count = 0;
    for elecA = 1:length(adjM)
        for elecB = 1:length(adjM)
            if adjM(elecA,elecB) >= edge_thresh && elecA ~= elecB && ~isnan(adjM(elecA,elecB))
                count = count + 1;
                xco(count,:) = [xc(elecA),xc(elecB)];
                yco(count,:) = [yc(elecA),yc(elecB)];
                lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
                colour(count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
                
            end
        end
    end
    
    if count > 0
        [~,order] = sort(colour(:,1),'descend');
        lineWidthT = lineWidth(:,order);
        % Fix invalid line widths
        lineWidthT(lineWidthT <= 0 | isnan(lineWidthT) | isinf(lineWidthT)) = min_ew;
        colourT = colour(order,:);
        % Fix invalid RGB colors
        colourT(colourT < 0) = 0;
        colourT(colourT > 1) = 1;
        colourT(isnan(colourT)) = 0.5;
        xcot = xco(order,:);
        ycot = yco(order,:);
    
        for u = 1:length(xcot)
            try
                plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
            catch
                % Fallback with safe values if plotting fails
                plot(xcot(u,:),ycot(u,:),'LineWidth',min_ew,'Color',[0.5 0.5 0.5]);
            end
        end
    end
end

if strcmp(plotType,'circular')
    
    max_ew = 2; % maximum edge width for plotting
    min_ew = 0.001; % min edge width
    light_c = [0.8 0.8 0.8]; % lightest edge colour
    
    adjMtril = tril(adjM,-1);
    [~,linpos] = sort(adjMtril(:));
    [xord,yord] = ind2sub(size(adjMtril),linpos);
    
    t = linspace(-pi,pi,length(adjM) + 1).';
    
    count = 0;
    for elec = 1:length(xord)
        elecA = xord(elec);
        elecB = yord(elec);
        if adjM(elecA,elecB) >= edge_thresh && elecA ~= elecB && ~isnan(adjM(elecA,elecB))
            count = count +1;
            u  = [cos(t(elecA));sin(t(elecA))];
            v  = [cos(t(elecB));sin(t(elecB))];
            if round(u(1),3) == 0
                try
                    if cos(t(elecA-1))>0
                        u(1) = 0.001;
                    elseif cos(t(elecA-1))<0
                        u(1) = -0.001;
                    end
                catch
                    u(1) = 0;
                end
            end
            if round(v(1),3) == 0
                try
                    if cos(t(elecB-1))>0
                        v(1) = 0.001;
                    elseif cos(t(elecB-1))<0
                        v(1) = -0.001;
                    end
                catch
                    v(1) = 0;
                end
            end
            
            if round(u(2),3) == 0
                try
                    if sin(t(elecA-1))>0
                        u(2) = 0.001;
                    elseif sin(t(elecA-1))<0
                        u(2) = -0.001;
                    end
                catch
                    u(2) = 0;
                end
            end
            if round(v(2),3) == 0
                try
                    if sin(t(elecB-1))>0
                        v(2) = 0.001;
                    elseif sin(t(elecB-1))<0
                        v(2) = -0.001;
                    end
                catch
                    v(2) = 0;
                end
            end
            
            if round(abs(u(1)),4)==round(abs(v(1)),4)
                u(1) = u(1)+0.0001;
            end
            if round(abs(u(2)),4)==round(abs(v(2)),4)
                u(2) = u(2)+0.0001;
            end
            
            x0 = -(u(2)-v(2))/(u(1)*v(2)-u(2)*v(1));
            y0 =  (u(1)-v(1))/(u(1)*v(2)-u(2)*v(1));
            r  = sqrt(x0^2 + y0^2 - 1);
            thetaLim(1) = atan2(u(2)-y0,u(1)-x0);
            thetaLim(2) = atan2(v(2)-y0,v(1)-x0);
            
            if u(1) >= 0 && v(1) >= 0
                % ensure the arc is within the unit disk
                theta = [linspace(max(thetaLim),pi,50),...
                    linspace(-pi,min(thetaLim),50)].';
            else
                theta = linspace(thetaLim(1),thetaLim(2)).';
            end
            xco(count,:) = r*cos(theta)+x0;
            yco(count,:) = r*sin(theta)+y0;
            lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
            colour(count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
        end
    end
    
    if count > 0
        [~,order] = sort(colour(:,1),'descend');
        lineWidthT = lineWidth(:,order);
        % Fix invalid line widths
        lineWidthT(lineWidthT <= 0 | isnan(lineWidthT) | isinf(lineWidthT)) = min_ew;
        colourT = colour(order,:);
        % Fix invalid RGB colors
        colourT(colourT < 0) = 0;
        colourT(colourT > 1) = 1;
        colourT(isnan(colourT)) = 0.5;
        xcot = xco(order,:);
        ycot = yco(order,:);
        for u = 1:size(xcot,1)
            try
                plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
            catch
                % Fallback with safe values if plotting fails
                plot(xcot(u,:),ycot(u,:),'LineWidth',min_ew,'Color',[0.5 0.5 0.5]);
            end
            hold on
        end
    end
end

%% add nodes

if strcmp(plotType,'MEA')
    
    count = 0;
    for i = 1:length(adjM)
        if sum(isnan(adjM(i,:)))<length(adjM) % ie if the electrodes is not NaN for all
            count = count + 1;
            nodeX(count) = xc(i);
            nodeY(count) = yc(i);
            val1 = z(i); % value for node size
            val2 = z2(i); % value for node color
            if i == 1
                val1min = val1;
                val1max = val1;
                val2min = val2;
                val2max = val2;
            else
                val1min = min(val1min,val1);
                val1max = max(val1max,val1);
                val2min = min(val2min,val2);
                val2max = max(val2max,val2);
            end
            nodeSize(count) = val1;
            nodeColour(count,:) = [val2];
        end
    end
    
    if ~isempty(nodeSize)
    
        % normalise size
        if val1max ~= val1min
            nodeScaleN = rescale(nodeSize,5,20,'InputMin',val1min,'InputMax',val1max);
        else
            nodeScaleN = 8*ones(1,length(nodeSize));
        end
        
        % normalise color
        if val2max ~= val2min
            nodeColourN = rescale(nodeColour,0,1,'InputMin',val2min,'InputMax',val2max);
        else
            % choose middle of colormap if all the same value
            nodeColourN = 0.5*ones(length(nodeColour),1);
        end
        
        CM = jet(1000);
        
        % nodeColourNew = CM(ceil(nodeColourN*999)+1,:);
        
        % index into the colormap - ceil(nodeColourN*999)+1 to handle case where we have 0
        % this could be a problem if nodeColourN is negative, which it
        % shouldn't be after rescaling from 0 to 1
        colorIndices = ceil(nodeColourN*999)+1;
        
        % Clamp indices to valid range (1 to 1000) in case there are issues
        colorIndices(colorIndices < 1) = 1;
        colorIndices(colorIndices > 1000) = 1000;
        colorIndices(isnan(colorIndices)) = 1; % Use first color for NaN
        
        nodeColourNew = CM(colorIndices,:);
        
        for i = 1:length(nodeSize)
            % rounding nodeScaleN to avoid MATLAB warnings
            pos = [nodeX(i)-(round(nodeScaleN(i),4)/2) nodeY(i)-(round(nodeScaleN(i),4)/2) round(nodeScaleN(i),4) round(nodeScaleN(i),4)];
            try
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',nodeColourNew(i,:),'EdgeColor','k','LineWidth',0.1)
            catch
                % Use default gray if there's a problem with the color
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.5 0.5 0.5],'EdgeColor','k','LineWidth',0.1)
            end
            
            if Params.includeChannelNumberInPlots
                text(pos(1), pos(2), sprintf('%.f', i), ...
                    'HorizontalAlignment','center')
            end 
            
        end
        
        ylim([min(yc)-1 max(yc)+1])
        xlim([min(xc)-1 max(xc)+3.75])
        
        % colourbar scaled for the node colour
        a = colorbar;
        colorbar_handle = a; % set return value
        colormap(jet);
        ylabel(a,z2name,'FontSize',12)
        
        % Check for valid min/max values before setting color axis
        if isfinite(val2min) && isfinite(val2max) && val2min < val2max
            caxis([val2min val2max])
        elseif isfinite(val2min) && isfinite(val2max) && val2min == val2max
            % Handle case where min == max (use small offset)
            caxis([val2min-0.1, val2max+0.1])
        else
            % Default fallback for invalid values
            caxis([0 1])
        end
        
        % also add a legend for the node sizes
        % add 3 circles to the 
        bufferX = 8; 
        largeESize = 20;
        medESize = 12.5;
        smallESize = 5;
        % the circles are positioned at the right edge of the graph, 
        % with the smaller circles slightly lowered, so it's more aesthetically pleasing
        largeNodePosX = max(xc) + bufferX - largeESize/2;
        largeNodePosY = (max(yc)+min(yc))/2 - largeESize/2;
        medNodePosX = largeNodePosX + 3;
        medNodePosY = largeNodePosY + 3;
        smallNodePosX = medNodePosX + 2;
        smallNodePosY = medNodePosY + 3;
        
        % convert the large node size to the original scale
        largeNodeOriginalScale = (largeESize - 5) * (val1max - val1min) / (20 - 5) + val1min;
        medNodeOriginalScale = (medESize - 5) * (val1max - val1min) / (20 - 5) + val1min;
        smallNodeOriginalScale = (smallESize - 5) * (val1max - val1min) / (20 - 5) + val1min;
        
        % some more aesthetically pleasing positioning for the text
        largeNodeTextX = max(xc) + bufferX + 1;
        largeNodeTextY = largeNodePosY + 6;
        medNodeTextX = medNodePosX + 1;
        medNodeTextY = medNodePosY + 3;
        smallNodeTextX = smallNodePosX + 1;
        smallNodeTextY = smallNodePosY + 0;
        
        titleText = [zname ' scale:'];
        titleTextPosX = largeNodeTextX - 5;
        titleTextPosY = largeNodeTextY + 3;
        
        % plot color and position of circles
        largeNodeColour = [0 0 0];
        text(titleTextPosX, titleTextPosY, titleText);
        rectangle('Position', [largeNodePosX, largeNodePosY, largeESize, largeESize], ...
            'Curvature', [1, 1], 'FaceColor', largeNodeColour);
        text(largeNodeTextX, largeNodeTextY, ['Max = ' num2str(largeNodeOriginalScale)]);
        
        medNodeColour = [0.3 0.3 0.3];
        rectangle('Position', [medNodePosX, medNodePosY, medESize, medESize], ... 
            'Curvature', [1, 1], 'FaceColor', medNodeColour);
        text(medNodeTextX, medNodeTextY, ['Med = ' num2str(medNodeOriginalScale)]);
        
        smallNodeColour = [0.5 0.5 0.5];
        rectangle('Position', [smallNodePosX, smallNodePosY, smallESize, smallESize], ... 
            'Curvature', [1, 1], 'FaceColor', smallNodeColour);
        text(smallNodeTextX, smallNodeTextY, ['Min = ' num2str(smallNodeOriginalScale)]);
    
    else
        colorbar_handle = []; % Empty handle if no nodes to plot
    end
else
    colorbar_handle = []; % Default empty handle
end

if strcmp(plotType,'circular')
    
    count = 0;
    for i = 1:length(adjM)
        if sum(isnan(adjM(i,:)))<length(adjM) % ie if the electrodes is not NaN for all
            count = count + 1;
            nodeX(count) = cos(t(i));
            nodeY(count) = sin(t(i));
            val1 = z(i); % value for node size
            val2 = z2(i); % value for node color
            if i == 1
                val1min = val1;
                val1max = val1;
                val2min = val2;
                val2max = val2;
            else
                val1min = min(val1min,val1);
                val1max = max(val1max,val1);
                val2min = min(val2min,val2);
                val2max = max(val2max,val2);
            end
            nodeSize(count) = val1;
            nodeColour(count,:) = [val2];
        end
    end
    
    if ~isempty(nodeSize)
    
        % normalise size
        if val1max ~= val1min
            nodeScaleN = rescale(nodeSize,0.1,0.3,'InputMin',val1min,'InputMax',val1max);
        else
            nodeScaleN = 0.15*ones(1,length(nodeSize));
        end
        
        % normalise color
        if val2max ~= val2min
            nodeColourN = rescale(nodeColour,0,1,'InputMin',val2min,'InputMax',val2max);
        else
            % choose middle of colormap if all the same value
            nodeColourN = 0.5*ones(length(nodeColour),1);
        end
        
        CM = jet(1000);
        
        % handle potential issues with indices
        colorIndices = ceil(nodeColourN*999)+1;
        colorIndices(colorIndices < 1) = 1;
        colorIndices(colorIndices > 1000) = 1000;
        colorIndices(isnan(colorIndices)) = 1; % Use first color for NaN
        
        nodeColourNew = CM(colorIndices,:);
        
        for i = 1:length(nodeSize)
            pos = [nodeX(i)-nodeScaleN(i) nodeY(i)-nodeScaleN(i) 2*nodeScaleN(i) 2*nodeScaleN(i)];
            try
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',nodeColourNew(i,:),'EdgeColor','k','LineWidth',0.1)
            catch
                % Use default gray if there's a problem with the color
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.5 0.5 0.5],'EdgeColor','k','LineWidth',0.1)
            end
            
            if Params.includeChannelNumberInPlots
                text(pos(1), pos(2), sprintf('%.f', i), ...
                    'HorizontalAlignment','center')
            end
        end
        
        ylim([-1.1 1.1])
        xlim([-1.1 1.9])
        
        % colourbar scaled for the node colour
        a = colorbar;
        colorbar_handle = a; % set return value 
        colormap(jet);
        if ~isempty(z2name)
            ylabel(a,z2name,'FontSize',12)
        end
        
        % Check for valid min/max values before setting color axis
        if isfinite(val2min) && isfinite(val2max) && val2min < val2max
            caxis([val2min val2max])
        elseif isfinite(val2min) && isfinite(val2max) && val2min == val2max
            % Handle case where min == max (use small offset)
            caxis([val2min-0.1, val2max+0.1])
        else
            % Default fallback for invalid values
            caxis([0 1])
        end
        
        % also add a legend for the node sizes
        % add 3 circles to the 
        bufferX = 1.5; 
        largeESize = 0.3;
        medESize = 0.2;
        smallESize = 0.1;
        % the circles are positioned at the right edge of the graph, 
        % with the smaller circles slightly lowered, so it's more aesthetically pleasing
        largeNodePosX = bufferX - largeESize;
        largeNodePosY = 0.8 - largeESize;
        medNodePosX = largeNodePosX;
        medNodePosY = 0.5 - medESize;
        smallNodePosX = largeNodePosX;
        smallNodePosY = 0.2 - smallESize;
        
        % convert the large node size to the original scale
        largeNodeOriginalScale = (largeESize - 0.1) * (val1max - val1min) / (0.3 - 0.1) + val1min;
        medNodeOriginalScale = (medESize - 0.1) * (val1max - val1min) / (0.3 - 0.1) + val1min;
        smallNodeOriginalScale = (smallESize - 0.1) * (val1max - val1min) / (0.3 - 0.1) + val1min;
        
        % some more aesthetically pleasing positioning for the text
        largeNodeTextX = largeNodePosX + (2 * largeESize) + 0.03;
        largeNodeTextY = largeNodePosY + largeESize;
        medNodeTextX = medNodePosX + (2 * medESize) + 0.03;
        medNodeTextY = medNodePosY + medESize;
        smallNodeTextX = smallNodePosX + (2 * smallESize) + 0.03;
        smallNodeTextY = smallNodePosY + smallESize;
        
        titleText = [zname ' scale:'];
        titleTextPosX = largeNodePosX;
        titleTextPosY = largeNodePosY + (2 * largeESize) + 0.02;
        
        % plot color and position of circles
        largeNodeColour = [0 0 0];
        text(titleTextPosX, titleTextPosY, titleText);
        rectangle('Position', [largeNodePosX, largeNodePosY, 2*largeESize, 2*largeESize], ...
            'Curvature', [1, 1], 'FaceColor', largeNodeColour);
        text(largeNodeTextX, largeNodeTextY, ['Max = ' num2str(largeNodeOriginalScale)]);
        
        medNodeColour = [0.3 0.3 0.3];
        rectangle('Position', [medNodePosX, medNodePosY, 2*medESize, 2*medESize], ... 
            'Curvature', [1, 1], 'FaceColor', medNodeColour);
        text(medNodeTextX, medNodeTextY, ['Med = ' num2str(medNodeOriginalScale)]);
        
        smallNodeColour = [0.5 0.5 0.5];
        rectangle('Position', [smallNodePosX, smallNodePosY, 2*smallESize, 2*smallESize], ... 
            'Curvature', [1, 1], 'FaceColor', smallNodeColour);
        text(smallNodeTextX, smallNodeTextY, ['Min = ' num2str(smallNodeOriginalScale)]);
    
    else
        colorbar_handle = []; % Empty handle if no nodes to plot
    end
else
    % This would be for a different plot type - not implemented
    colorbar_handle = []; % Default empty handle
end

set(gca,'color','none')

%% save figure

figName = strcat([pNum,'_',plotType,'_',zname,'_',z2name]);
figPath = fullfile(figFolder, figName);

if Params.showOneFig
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, figureHandle);
else 
    pipelineSaveFig(figPath, Params.figExt, Params.fullSVG);
end 

if ~Params.showOneFig
    close all
else 
    set(0, 'CurrentFigure', figureHandle);
    clf reset
end 

end