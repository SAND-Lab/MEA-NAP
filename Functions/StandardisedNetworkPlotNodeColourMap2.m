function [] = StandardisedNetworkPlotNodeColourMap2(adjM, coords, edge_thresh, z2, z2name, plotType, FN, Params)
%{
% script to plot the graph network 
% 
Parameters
----------
%   adjM - adjacency matrix 
%   coords - electrode/node coordinates (x and y, num nodes * 2)
%   edge_thresh - a value between 0 and 1 for the minimum correlation to
%       plot
%   z - the network metric used to determine the size of the plotted nodes
%       eg: node degree or node strength
%   zname - name of the z network metric
%   z2 - the network metric used to determine the colour of the plotted
%       nodes, eg: betweeness centrality or participation coefficient
%   z2name - name of the z2 network metric
%   plotType - 'grid' to plot nodes with their respective electrode
%       coordinates and 'circular' to plot nodes in a circle
Returns 
-------
%   None 
%
%}
%% plot

figure('units','centimeters','position',[0 0 20 20]);

aesthetics; hold on

%% coordinates

xc = coords(:,1);
yc = coords(:,2);

%% add edges

threshMax = max(adjM(:));
minNonZeroEdge = min(min(adjM(adjM>0))); 

if strcmp(plotType,'grid')
    
    max_ew = 4; % maximum edge width for plotting
    min_ew = 0.001; % min edge width
    light_c = [0.8 0.8 0.8]; % lightest edge colour
    
    count = 0;
    for elecA = 1:length(coords)
        for elecB = 1:length(coords)
            if adjM(elecA,elecB) >= edge_thresh && elecA ~= elecB && ~isnan(adjM(elecA,elecB))
                count = count +1;
                xco(count,:) = [xc(elecA),xc(elecB)];
                yco(count,:) = [yc(elecA),yc(elecB)];
                lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
                colour (count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
            end
        end
    end
    
    % threshold the edge width (in case edge values are lower than the
    % lower display bound) and colours
    lineWidth(lineWidth < 0) = min_ew;
    colour(colour > light_c(1)) = light_c(1);
    
    [~,order] = sort(colour(:,1),'descend');
    lineWidthT = lineWidth(:,order);
    colourT = colour(order,:);
    xcot = xco(order,:);
    ycot = yco(order,:);
    
    % Fix for any invalid color values
    for u = 1:length(xcot)
        % Check for invalid RGB values
        if any(isnan(colourT(u,:))) || all(colourT(u,:) == 0) || any(colourT(u,:) < 0) || any(colourT(u,:) > 1)
            colourT(u,:) = [0.5, 0.5, 0.5]; % Use default gray for invalid colors
        end
    end
    
    % More robust approach for plotting edges
    try
        for u = 1:length(xcot)
            try
                plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
            catch colorErr
                % Fallback if color still causes issues
                plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',[0.5, 0.5, 0.5]);
            end
        end
    catch plotErr
        disp('Warning: Error in plotting network edges in grid layout');
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
            colour (count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
        end
    end
    
    % threshold the edge width (in case edge values are lower than the
    % lower display bound) and colours
    lineWidth(lineWidth < 0) = min_ew;
    colour(colour > light_c(1)) = light_c(1);
    
    [~,order] = sort(colour(:,1),'descend');
    lineWidthT = lineWidth(:,order);
    colourT = colour(order,:);
    xcot = xco(order,:);
    ycot = yco(order,:);
    
    % Fix for any invalid color values
    for u = 1:size(xcot,1)
        % Check for invalid RGB values
        if any(isnan(colourT(u,:))) || all(colourT(u,:) == 0) || any(colourT(u,:) < 0) || any(colourT(u,:) > 1)
            colourT(u,:) = [0.5, 0.5, 0.5]; % Use default gray for invalid colors
        end
    end
    
    % More robust approach for plotting edges
    try
        for u = 1:size(xcot,1)
            try
                plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
            catch colorErr
                % Fallback if color still causes issues
                plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',[0.5, 0.5, 0.5]);
            end
        end
    catch plotErr
        disp('Warning: Error in plotting network edges in circular layout');
    end
end

%% add nodes (and colour them)

if strcmp(z2name, 'Module')
    mycolours = plasma;
else
    mycolours = colormap;
end

if strcmp(plotType,'grid')
    
    nodeScaleF = 0.3;
    
    for i = 1:length(adjM)
        pos = [xc(i)-(0.5*nodeScaleF) yc(i)-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        if z2(i)>0
            try
                % Calculate color with error handling
                colorIndex = ceil(length(mycolours)*((z2(i)-min(z2))/(max(z2)-min(z2))));
                % Ensure the color index is valid
                if colorIndex < 1
                    colorIndex = 1;
                elseif colorIndex > size(mycolours, 1)
                    colorIndex = size(mycolours, 1);
                end
                nodeColor = mycolours(colorIndex, 1:3);
                
                % Check for invalid RGB values
                if any(isnan(nodeColor)) || all(nodeColor == 0) || any(nodeColor < 0) || any(nodeColor > 1)
                    nodeColor = [0.5, 0.5, 0.5]; % Use default gray
                end
                
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',nodeColor,'EdgeColor','w','LineWidth',0.1);
            catch
                % Fallback to a safe color if calculation fails
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.5, 0.5, 0.5],'EdgeColor','w','LineWidth',0.1);
            end
        else
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(1,1:3),'EdgeColor','w','LineWidth',0.1)
        end
    end
    ylim([min(yc)-1 max(yc)+1])
    xlim([min(xc)-1 max(xc)+4.25])
end

if strcmp(plotType,'circular')
    
    nodeScaleF = 2/3*sqrt((abs(cos(t(1))-cos(t(2)))^2) + (abs(sin(t(1))-sin(t(2)))^2));
    
    for i = 1:length(adjM)
        pos = [cos(t(i))-(0.5*nodeScaleF) sin(t(i))-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        if z2(i)>0
            try
                % Calculate color with error handling
                colorIndex = ceil(length(mycolours)*((z2(i)-min(z2))/(max(z2)-min(z2))));
                % Ensure the color index is valid
                if colorIndex < 1
                    colorIndex = 1;
                elseif colorIndex > size(mycolours, 1)
                    colorIndex = size(mycolours, 1);
                end
                nodeColor = mycolours(colorIndex, 1:3);
                
                % Check for invalid RGB values
                if any(isnan(nodeColor)) || all(nodeColor == 0) || any(nodeColor < 0) || any(nodeColor > 1)
                    nodeColor = [0.5, 0.5, 0.5]; % Use default gray
                end
                
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',nodeColor,'EdgeColor','w','LineWidth',0.1);
            catch
                % Fallback to a safe color if calculation fails
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.5, 0.5, 0.5],'EdgeColor','w','LineWidth',0.1);
            end
        else
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(1,1:3),'EdgeColor','w','LineWidth',0.1)
        end
    end
    ylim([-1.1 1.1])
    xlim([-1.1 2])
end

set(gca,'color','none')

%% add colorbar

if ~strcmp(z2name, 'Module')
    cb = colorbar;
    cb.Ticks = [0 0.2 0.4 0.6 0.8 1]; % Specify the tick location
    
    cbar_ticklabels = {};
    num_ticks = length(cb.Ticks);
    round_decimal_places = 3; % fix to 3 decimal places
    tickVals = linspace(min(z2), max(z2), num_ticks);
    
    % Safely handle case where all values are zeros
    if min(z2) == 0 && max(z2) == 0
        cbar_ticklabels = {'0', '0.2', '0.4', '0.6', '0.8', '1'};
    else
        for tickIndex = 1:num_ticks
            cbar_ticklabels{tickIndex} = num2str(round(tickVals(tickIndex), round_decimal_places));
        end 
    end
    
    cb.TickLabels = cbar_ticklabels;
    cb.Label.String = z2name;
else
    % No Colorbar for modules, plot some colored circles instead
    legendStart = min(xc) + 0.5;
    legendYpos = min(yc) - 0.5;
    text(legendStart, legendYpos, 'Module')
    legendXpositions = linspace(legendStart+1, legendStart+3, length(unique(z2)));
    
    uniqueModules = unique(z2);
    circleSize = 0.2;
    for moduleIdx = 1:length(uniqueModules)
        if uniqueModules(moduleIdx) > 0  % Skip module 0 (doesn't belong to any module)
            circlePos = [legendXpositions(moduleIdx)-circleSize/2, legendYpos-circleSize/2, circleSize, circleSize];
            try
                % Calculate color with error handling
                colorIndex = ceil(length(mycolours)*((uniqueModules(moduleIdx)-min(z2))/(max(z2)-min(z2))));
                % Ensure the color index is valid
                if colorIndex < 1
                    colorIndex = 1;
                elseif colorIndex > size(mycolours, 1)
                    colorIndex = size(mycolours, 1);
                end
                moduleColor = mycolours(colorIndex, 1:3);
                
                % Check for invalid RGB values
                if any(isnan(moduleColor)) || all(moduleColor == 0) || any(moduleColor < 0) || any(moduleColor > 1)
                    moduleColor = [0.5, 0.5, 0.5]; % Use default gray
                end
                
                rectangle('Position',circlePos,'Curvature',[1 1],'FaceColor',moduleColor,'EdgeColor','w','LineWidth',0.1);
                text(legendXpositions(moduleIdx), legendYpos, num2str(uniqueModules(moduleIdx)), ...
                    'HorizontalAlignment', 'center')
            catch
                % Fallback to a safe color if calculation fails
                rectangle('Position',circlePos,'Curvature',[1 1],'FaceColor',[0.5, 0.5, 0.5],'EdgeColor','w','LineWidth',0.1);
                text(legendXpositions(moduleIdx), legendYpos, num2str(uniqueModules(moduleIdx)), ...
                    'HorizontalAlignment', 'center')
            end
        end
    end
end

%% Add channel numbers based on user preference
if isfield(Params, 'includeChannelNumberInPlots') && Params.includeChannelNumberInPlots
    if strcmp(plotType, 'grid')
        for i = 1:length(adjM)
            text(xc(i), yc(i), sprintf('%.f', Params.netSubsetChannels(i)), ...
                'HorizontalAlignment', 'center');
        end
    else % circular
        for i = 1:length(adjM)
            text(cos(t(i)), sin(t(i)), sprintf('%.f', Params.netSubsetChannels(i)), ...
                'HorizontalAlignment', 'center');
        end
    end
end

%% save figure
figFolder = Params.outputDirectory;
figName = strcat('NetworkPlot_',z2name,'_',FN);
figName = strrep(figName, ' ', '');
figPath = fullfile(figFolder, figName);
pipelineSaveFig(figPath, Params.figExt, Params.fullSVG);