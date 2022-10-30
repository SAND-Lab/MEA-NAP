function [] = StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, z, zname, z2, z2name, plotType, ...
                                                   FN, pNum, Params, lagval, e)

% 
% Plots graph network with node size proportional to some node-level variable of
% choice and color-mapped based on some other node-level variable of choice
% 
% Parameters
% ----------
% adjM : matrix 
%    adjacency matrix 
% coords : matrix 
%    electrode/node coordinates (x and y, num nodes * 2)
% edge_thresh : float 
%    a value between 0 and 1 for the minimum correlation to plot
% z : str
%    the network metric used to determine the size of the plotted nodes
%     eg: node degree or node strength
%  zname : str
%     name of the z network metric
%   z2 : str
%     the network metric used to determine the colour of the plotted
%      nodes, eg: betweeness centrality or participation coefficient
%   z2name : str
%     name of the z2 network metric
%   plotType : str
%       'MEA' to plot nodes with their respective electrode
%       coordinates and 'circular' to plot nodes in a circle
%   FN : str
%       name of file/recording
%   pNum : int
%       number to precede name of figure when it is saved
% Returns 
% -------
% None 
%
% author RCFeord August 2021
% Updated by Tim Sit

%% plot
if ~isfield(Params, 'oneFigure')
    F1 = figure;
    F1.OuterPosition = [50   100   720  550];
else 
    p =  [50   100   720  550];
    set(0, 'DefaultFigurePosition', p)
    % Params.oneFigure.OuterPosition = [50   100   660  550];
    set(Params.oneFigure, 'Position', p);
end 

aesthetics; axis off; hold on

title(strcat(regexprep(FN,'_','','emptymatch'),{' '},num2str(lagval(e)),{' '},'ms',{' '},'lag'))

%% coordinates

xc = coords(:,1);
yc = coords(:,2);

%% Mapping to get theoretical bounds 
% Used when theoretical bounds is set to True, this maps the z2name to
% metric names
% TODO: find a more streamlined way to do this
z2nameToShortHand = containers.Map;
z2nameToShortHand('Betweeness centrality') = 'BC';
z2nameToShortHand('Participation coefficient') = 'PC';
z2nameToShortHand('Local efficiency') = 'Eloc';
z2nameToShortHand('Average controllability') = 'aveControl';
z2nameToShortHand('Modal controllability') = 'modalControl';


%% add edges
num_nodes = size(adjM, 2);
threshMax = max(adjM(:));
minNonZeroEdge = min(min(adjM(adjM>0))); 

if strcmp(plotType,'MEA')
    
    max_ew = 4; % maximum edge width for plotting
    min_ew = 0.001; % min edge width
    light_c = [0.8 0.8 0.8]; % lightest edge colour
    
    count = 0;
    for elecA = 1:num_nodes
        for elecB = 1:num_nodes
            if adjM(elecA,elecB) >= edge_thresh && elecA ~= elecB && ~isnan(adjM(elecA,elecB))
                count = count +1;
                xco(count,:) = [xc(elecA),xc(elecB)];
                yco(count,:) = [yc(elecA),yc(elecB)];
                lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
                colour (count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
            end
        end
    end
    
    [~,order] = sort(colour(:,1),'descend');
    lineWidthT = lineWidth(:,order);
    colourT = colour(order,:);
    xcot = xco(order,:);
    ycot = yco(order,:);
    for u = 1:length(xcot)
        plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
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
    
    [~,order] = sort(colour(:,1),'descend');
    lineWidthT = lineWidth(:,order);
    colourT = colour(order,:);
    xcot = xco(order,:);
    ycot = yco(order,:);
    for u = 1:size(xcot,1)
        plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
        hold on
    end
end
%% add nodes (and color them)

mycolours = colormap;

% TODO: What is this rectangle, I guess this is the individual nodes but
% made into circles?

if Params.use_theoretical_bounds
    cmap_bounds = Params.network_plot_cmap_bounds.(z2nameToShortHand(z2name));
    z2_min = cmap_bounds(1);
    z2_max = cmap_bounds(end);
else 
    z2_max = max(z2);
    z2_min = min(z2);
end 

if strcmp(plotType,'MEA')
    uniqueXc = sort(unique(xc));
    nodeScaleF = max(z)/(uniqueXc(2)-uniqueXc(1));
    for i = 1:length(adjM)
        if z(i)>0
            pos = [xc(i)-(0.5*z(i)/nodeScaleF) yc(i)-(0.5*z(i)/nodeScaleF) z(i)/nodeScaleF z(i)/nodeScaleF];
            if z2(i)>0
                try
                    rectangle('Position',pos,'Curvature',[1 1],'FaceColor', ... 
                        mycolours(ceil(length(mycolours)*((z2(i)-z2_min)/(z2_max-z2_min))),1:3), ...
                        'EdgeColor','w','LineWidth',0.1)
                    
                catch
                    rectangle('Position',pos,'Curvature',[1 1],'FaceColor', ...
                        mycolours(ceil(length(mycolours)*((z2(i)-z2_min)/(z2_max-z2_min))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
                end
            else
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(1,1:3),'EdgeColor','w','LineWidth',0.1)
            end
        end
        
        % Add channel numbers on top of the nodes
        if Params.includeChannelNumberInPlots 
            pos = [xc(i)  yc(i)];
            text(pos(1), pos(2), sprintf('%.f', Params.netSubsetChannels(i)), ...
                'HorizontalAlignment','center')
        end 

    end
    ylim([min(yc)-1 max(yc)+1])
    xlim([min(xc)-1 max(xc)+4.25])
end

if strcmp(plotType,'circular')
    
    nodeScaleF = max(z)/sqrt((abs(cos(t(1))-cos(t(2))))^2 + (abs(sin(t(1))-sin(t(2))))^2);
    
    for i = 1:length(adjM)
        if z(i)>0
            pos = [cos(t(i))-(0.5*z(i)/nodeScaleF) sin(t(i))-(0.5*z(i)/nodeScaleF) z(i)/nodeScaleF z(i)/nodeScaleF];
            if z2(i)>0
                try
                    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((z2(i)-z2_min)/(z2_max-z2_min))),1:3),'EdgeColor','w','LineWidth',0.1)
                    
                catch
                    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((z2(i)-z2_min)/(z2_max-z2_min))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
                end
            else
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(1,1:3),'EdgeColor','w','LineWidth',0.1)
            end
        end
    end
    ylim([-1.1 1.1])
    xlim([-1.1 2])
end

set(gca,'color','none')


%% format plot

if round(max(z)*1/3) >= 1
    eval(['legdata = [''' num2str(round(max(z)*1/3),'%02d') '''; ''' num2str(round(max(z)*2/3),'%02d') '''; ''' num2str(round(max(z)),'%02d') '''];']); % data for the legend
elseif round(max(z)*1/3) < 1
    eval(['legdata = [''' num2str(round(max(z)*1/3,4),'%.4f') '''; ''' num2str(round(max(z)*2/3,4),'%.4f') '''; ''' num2str(round(max(z),4),'%.4f') '''];']);
end


if strcmp(plotType,'MEA')
    
    text(max(xc)+1.5,max(yc),strcat(zname,':'))
    
    pos = [(max(xc)+2)-(str2num(legdata(1,:))/nodeScaleF)/2 max(yc)-1 str2num(legdata(1,:))/nodeScaleF str2num(legdata(1,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[1 1 1],'EdgeColor','k','LineWidth',0.5);
    text(max(xc)+3,(max(yc)-1)+(0.5*str2num(legdata(1,:))/nodeScaleF),legdata(1,:))
    
    pos = [(max(xc)+2)-(str2num(legdata(2,:))/nodeScaleF)/2 (max(yc)-1)-(0.5*str2num(legdata(2,:))/nodeScaleF+1.5*str2num(legdata(1,:))/nodeScaleF) str2num(legdata(2,:))/nodeScaleF str2num(legdata(2,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[1 1 1],'EdgeColor','k','LineWidth',0.5);
    text(max(xc)+3,(max(yc)-1)-(1.5*str2num(legdata(1,:))/nodeScaleF),legdata(2,:))
    
    pos = [(max(xc)+2)-(str2num(legdata(3,:))/nodeScaleF)/2 (max(yc)-1)-(0.5*str2num(legdata(3,:))/nodeScaleF+str2num(legdata(2,:))/nodeScaleF+2.5*str2num(legdata(1,:))/nodeScaleF) str2num(legdata(3,:))/nodeScaleF str2num(legdata(3,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[1 1 1],'EdgeColor','k','LineWidth',0.5);
    text(max(xc)+3,(max(yc)-1)-(str2num(legdata(2,:))/nodeScaleF+2.5*str2num(legdata(1,:))/nodeScaleF),legdata(3,:))
    
    text(max(xc)+1.5,max(yc)-(4*str2num(legdata(3,:))/nodeScaleF),'edge weight:')
    
    range = max(adjM(:))-minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-(5*str2num(legdata(3,:))/nodeScaleF) max(yc)-(5*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(5*str2num(legdata(3,:))/nodeScaleF),num2str(round(max(adjM(:))-2/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-(6*str2num(legdata(3,:))/nodeScaleF) max(yc)-(6*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(6*str2num(legdata(3,:))/nodeScaleF),num2str(round(max(adjM(:))-1/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-(7*str2num(legdata(3,:))/nodeScaleF) max(yc)-(7*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(7*str2num(legdata(3,:))/nodeScaleF),num2str(round(max(adjM(:)),4)))
    
    cb = colorbar;
    cb.Ticks = [0 0.2 0.4 0.6 0.8 1];
    
    % This is the line that specifies the cmap labels 

    cbar_ticklabels = {};
    num_ticks = length(cb.Ticks);
    
    
    if Params.use_theoretical_bounds == 1
        % Uses user-specified custom bounds (the min and max possible in
        % theory for each metric)
        cmap_bounds = Params.network_plot_cmap_bounds.(z2nameToShortHand(z2name));
        tickVals = linspace(cmap_bounds(1), cmap_bounds(2), num_ticks);
        round_decimal_places = ceil(-log10(cmap_bounds(2) - cmap_bounds(1))) + 1;
    else
        % Set cmap bounds from the min and max across nodes in this
        % specific network
        % roughly estimate the appropriate rounding decimal places from the max
        % - min difference, eg. max of 1 and min of 0 will result in -log(0) +
        % 1 = 1 decimal place rounding, a max of 0.1 and min of 0 will result
        % in 2 decimal place rounding, and a max of 0.1 and min of 0.01 will
        % result in 3 decimal place (because of the ceil function)
        round_decimal_places = ceil(-log10(max(z2) - min(z2))) + 1;
        tickVals = linspace(min(z2), max(z2), num_ticks);

    end 

   for tickIndex = 1:num_ticks
       cbar_ticklabels{tickIndex} = num2str(round(tickVals(tickIndex), round_decimal_places));
   end 
    
    cb.TickLabels = cbar_ticklabels;
    cb.Label.String = z2name;

end

if strcmp(plotType,'circular')
    
    text(1.4,0.9,strcat(zname,':'))
    
    pos = [1.45-(str2num(legdata(1,:))/nodeScaleF)/2 0.9-0.25 str2num(legdata(1,:))/nodeScaleF str2num(legdata(1,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[1 1 1],'EdgeColor','k','LineWidth',0.5);
    text(1.6,(0.9-0.25)+(0.5*str2num(legdata(1,:))/nodeScaleF),legdata(1,:))
    
    pos = [1.45-(str2num(legdata(2,:))/nodeScaleF)/2 (0.9-0.25)-(0.5*str2num(legdata(2,:))/nodeScaleF+3*str2num(legdata(1,:))/nodeScaleF) str2num(legdata(2,:))/nodeScaleF str2num(legdata(2,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[1 1 1],'EdgeColor','k','LineWidth',0.5);
    text(1.6,(0.9-0.25)-(3*str2num(legdata(1,:))/nodeScaleF),legdata(2,:))
    
    pos = [1.45-(str2num(legdata(3,:))/nodeScaleF)/2 (0.9-0.25)-(0.5*str2num(legdata(3,:))/nodeScaleF+str2num(legdata(2,:))/nodeScaleF+5.5*str2num(legdata(1,:))/nodeScaleF) str2num(legdata(3,:))/nodeScaleF str2num(legdata(3,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[1 1 1],'EdgeColor','k','LineWidth',0.5);
    text(1.6,(0.9-0.25)-(str2num(legdata(2,:))/nodeScaleF+5.5*str2num(legdata(1,:))/nodeScaleF),legdata(3,:))
    
    text(1.4,(0.9-0.25)-(7*str2num(legdata(3,:))/nodeScaleF),'edge weight:')
    
    range = max(adjM(:))-minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [(0.9-0.25)-(9*str2num(legdata(3,:))/nodeScaleF) (0.9-0.25)-(9*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,(0.9-0.25)-(9*str2num(legdata(3,:))/nodeScaleF),num2str(round(max(adjM(:))-2/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [(0.9-0.25)-(10.5*str2num(legdata(3,:))/nodeScaleF) (0.9-0.25)-(10.5*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,(0.9-0.25)-(10.5*str2num(legdata(3,:))/nodeScaleF),num2str(round(max(adjM(:))-1/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [(0.9-0.25)-(12*str2num(legdata(3,:))/nodeScaleF) (0.9-0.25)-(12*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,(0.9-0.25)-(12*str2num(legdata(3,:))/nodeScaleF),num2str(round(max(adjM(:)),4)))
    
    cb = colorbar;
    cb.Ticks = [0 0.2 0.4 0.6 0.8 1]; % Specify the tick location
    
    cbar_ticklabels = {};
    num_ticks = length(cb.Ticks);
    round_decimal_places = ceil(-log10(max(z2) - min(z2))) + 1;
    tickVals = linspace(min(z2), max(z2), num_ticks);
    for tickIndex = 1:num_ticks
        cbar_ticklabels{tickIndex} = num2str(round(tickVals(tickIndex), round_decimal_places));
    end 
    
    cb.TickLabels = cbar_ticklabels;
    cb.Label.String = z2name;
    
end

%% save figure
figName = strcat([pNum,'_',plotType,'_NetworkPlot',zname,z2name]);
figName = strrep(figName, ' ', '');

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 

end