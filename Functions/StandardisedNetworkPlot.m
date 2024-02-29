function figureHandle = StandardisedNetworkPlot(adjM, coords, edge_thresh, z, plotType, FN, pNum, ...
    Params, lagval, e, figFolder, figureHandle, saveFigure)
% Plot the graph network 
% Parameters
% ----------
% adjM : N x N matrix
%     adjacency matrix 
% coords : N x 2 matrix 
%     the x and y coordinates of each node or electrode 
%     currently assumes that the value ranges from 1 - 8 on both x and y axis
% edge_thresh : float 
%     a value between 0 and 1 for the minimum correlation to plot
% z : N X 1 vector 
%     the network metric used to determine the size of the plotted nodes
%     eg: node degree or node strength
% plotType : str
%     'MEA' to plot nodes with their respective electrode
%     coordinates and 'circular' to plot nodes in a circle
% FN : str
%     name of file/recording
% pNum - number to precede name of figure when it is saved
% Params : struct 
%   structure with parameters for plotting / file saving 
%   Params.minNodeSize : float
%       minimum node size for the network plot 
%   Params.useMinMaxBoundsForPlots : bool
%       whether to use the same node size scaling across plots of different
%       recordings, 1: yes, 0; no. This parameter determines how nodeScaleF
%       is determined
%   
% Returns 
% -------
%    F1 - 
%
% Variable definitions 
% --------
% nodeScaleF : float 
%       determines the maximum node size, based on the maximum node degree
%       either for an individual recording (Params.useMinMaxBoundsForPlots = 0) 
%       or across all recordings (Params.useMinMaxBoundsForPlots = 1)
% author RCFeord August 2021
% edited by Tim Sit 

if ~exist('saveFigure', 'var')
    saveFigure = 1;
end 

num_nodes = size(adjM, 2);

%% plot
p =  [50   100   660  550];
if exist('figureHandle', 'var')
    set(figureHandle, 'Position', p)
elseif ~isfield(Params, 'oneFigure')
    F1 = figure;
    F1.OuterPosition = p;
else 
    set(0, 'DefaultFigurePosition', p)
    % Params.oneFigure.OuterPosition = [50   100   660  550];
    set(Params.oneFigure, 'Position', p);
end 

aesthetics; axis off; hold on

title(strcat(regexprep(FN,'_','','emptymatch'), ... 
    {' '},num2str(lagval(e)),{' '},'ms',{' '},'lag'))


%% coordinates

xc = coords(:,1);
yc = coords(:,2);

%% add edges

if isfield(Params, 'useMinMaxBoundsForPlots')
    if Params.useMinMaxBoundsForPlots
        minNonZeroEdge = Params.metricsMinMax.EW(1);
        threshMax = Params.metricsMinMax.EW(2);
    else
        threshMax = max(adjM(:));
        minNonZeroEdge = min(min(adjM(adjM>0))); 
    end
else 
    threshMax = max(adjM(:));
    minNonZeroEdge = min(min(adjM(adjM>0))); 
end 



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

                if threshMax > minNonZeroEdge
                    lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
                    colour(count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
                else  % deal with case where threshMax == minNonZeroEdge because there is only one edge
                    lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-min_ew));
                    colour(count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-min_ew)));
                end 
            end
        end
    end
    
    % threshold the edge width (in case edge values are lower than the
    % lower display bound) and colours
    lineWidth(lineWidth <= 0) = min_ew;
    colour(colour > light_c(1)) = light_c(1);
    
    [~,order] = sort(colour(:,1),'descend');
    lineWidthT = lineWidth(:,order);
    colourT = colour(order,:);
    xcot = xco(order,:);
    ycot = yco(order,:);
    
    % for u = 1:length(xcot)
    %     plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
    % end
    % Thought: changing earlier code to avoid having to transpose
    % will speed things up (but not sure if significant)
    linePlot = plot(xcot',ycot'); % 'LineWidth',lineWidthT,'Color',colourT);
    set(linePlot, {'LineWidth'}, num2cell(lineWidthT'));
    set(linePlot, {'Color'}, num2cell(colourT', [1, 3])');
    hold on
    
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
            if threshMax > minNonZeroEdge
                lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
                colour(count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
            else % deal with case where threshMax == minNonZeroEdge because there is only one edge
                lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax));
                colour(count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax)));
            end 
       end
    end
    
    % threshold the edge width (in case edge values are lower than the
    % lower display bound) and colours
    lineWidth(lineWidth <= 0) = min_ew;
    colour(colour > light_c(1)) = light_c(1);
    
    [~,order] = sort(colour(:,1),'descend');
    lineWidthT = lineWidth(:,order);
    colourT = colour(order,:);
    xcot = xco(order,:);
    ycot = yco(order,:);

    linePlot = plot(xcot',ycot'); % 'LineWidth',lineWidthT,'Color',colourT);
    set(linePlot, {'LineWidth'}, num2cell(lineWidthT'));
    set(linePlot, {'Color'}, num2cell(colourT', [1, 3])');
    hold on


end
%% add nodes

if strcmp(plotType,'MEA')

    if isfield(Params, 'useMinMaxBoundsForPlots')
        if Params.useMinMaxBoundsForPlots
            nodeScaleF = max(Params.metricsMinMax.ND); % hard-coding to ND for now because there is no quick fix
            max_z = max(Params.metricsMinMax.ND);   % to be used in the legend 
        else
            nodeScaleF = max(z);
            max_z = max(z);
        end 
    else 
        nodeScaleF = max(z);
        max_z = max(z);
    end 
    
    for i = 1:length(adjM)
        if z(i)>0
            nodeSize = max(Params.minNodeSize, z(i)/nodeScaleF);
            
            pos = [xc(i)-(0.5*nodeSize) yc(i)-(0.5*nodeSize) nodeSize nodeSize];
            
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.020 0.729 0.859],'EdgeColor','w','LineWidth',0.1)
        end

        % Add channel numbers on top of the nodes
        if Params.includeChannelNumberInPlots 
            pos = [xc(i)  yc(i)];
            text(pos(1), pos(2), sprintf('%.f', Params.netSubsetChannels(i)), ...
                'HorizontalAlignment','center')
        end 

    end

    ylim([min(yc)-1 max(yc)+1])
    xlim([min(xc)-1 max(xc)+3.75])
end

if strcmp(plotType,'circular')
    
    
    if isfield(Params, 'useMinMaxBoundsForPlots')
        if Params.useMinMaxBoundsForPlots
            max_z = max(Params.metricsMinMax.ND); % to be used in the legend 
        else
            max_z = max(z);
        end 
    else 
        max_z = max(z);
    end 
    
    nodeScaleF = max_z/sqrt((abs(cos(t(1))-cos(t(2))))^2 + (abs(sin(t(1))-sin(t(2))))^2);
    
    for i = 1:length(adjM)
        if z(i)>0
            nodeSize = max(Params.minNodeSize, z(i)/nodeScaleF);
            pos = [cos(t(i))-(0.5*nodeSize) sin(t(i))-(0.5*nodeSize) nodeSize nodeSize];
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.020 0.729 0.859],'EdgeColor','w','LineWidth',0.1)
            % add channel number 
            if Params.includeChannelNumberInPlots 
                text(pos(1), pos(2), sprintf('%.f', Params.netSubsetChannels(i)), ...
                'HorizontalAlignment','center')
            end
        end
    end
    ylim([-1.1 1.1])
    xlim([-1.1 1.9])
end

set(gca,'color','none')


%% format plot
legdata = {};
legendNumDivisor = 3;
for divisor = 1:legendNumDivisor
    legdata{divisor} = num2str(round(max_z * divisor / legendNumDivisor), '%02d');
end
legdata = char(legdata);

if strcmp(plotType,'MEA')
    
    % node degree legend
    text(max(xc)+1.5,max(yc),'node degree:')
    
    nodeLegendColor = [0.020 0.729 0.859];
    
    pos = [(max(xc)+2)-(str2num(legdata(1,:))/nodeScaleF)/2, ...
            max(yc)-1, ...
          str2num(legdata(1,:))/nodeScaleF, ...
          str2num(legdata(1,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',nodeLegendColor,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+3,(max(yc)-1)+(0.5*str2num(legdata(1,:))/nodeScaleF),legdata(1,:))
    
    pos = [(max(xc)+2)-(str2num(legdata(2,:))/nodeScaleF)/2, ...
           (max(yc)-1)-(0.5*str2num(legdata(2,:))/nodeScaleF + 1.5*str2num(legdata(1,:))/nodeScaleF), ...
           str2num(legdata(2,:))/nodeScaleF, ...
           str2num(legdata(2,:))/nodeScaleF];
       
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',nodeLegendColor,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+3,(max(yc)-1)-(1.5*str2num(legdata(1,:))/nodeScaleF),legdata(2,:))
    
    pos = [(max(xc)+2)-(str2num(legdata(3,:))/nodeScaleF)/2 (max(yc)-1)-(0.5*str2num(legdata(3,:))/nodeScaleF+str2num(legdata(2,:))/nodeScaleF+2.5*str2num(legdata(1,:))/nodeScaleF) str2num(legdata(3,:))/nodeScaleF str2num(legdata(3,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',nodeLegendColor,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+3,(max(yc)-1)-(str2num(legdata(2,:))/nodeScaleF+2.5*str2num(legdata(1,:))/nodeScaleF),legdata(3,:))
    
    text(max(xc)+1.5,max(yc)-(4*str2num(legdata(3,:))/nodeScaleF),'edge weight:')
    
    range = threshMax - minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((threshMax - 2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((threshMax-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-(5*str2num(legdata(3,:))/nodeScaleF) max(yc)-(5*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(5*str2num(legdata(3,:))/nodeScaleF),num2str(round(threshMax-2/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((threshMax-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((threshMax - 1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-(6*str2num(legdata(3,:))/nodeScaleF) max(yc)-(6*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(6*str2num(legdata(3,:))/nodeScaleF),num2str(round(threshMax-1/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*((threshMax-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((threshMax)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-(7*str2num(legdata(3,:))/nodeScaleF) max(yc)-(7*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(7*str2num(legdata(3,:))/nodeScaleF),num2str(round(threshMax,4)))
    
end

if strcmp(plotType,'circular')
    
    text(1.4,0.9,'node degree:')
    
    pos = [1.45-(str2num(legdata(1,:))/nodeScaleF)/2, ...
           0.9-0.25, ...
           str2num(legdata(1,:))/nodeScaleF, ...
           str2num(legdata(1,:))/nodeScaleF];
       
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.020 0.729 0.859],'EdgeColor','w','LineWidth',0.1);
    text(1.6,(0.9-0.25)+(0.5*str2num(legdata(1,:))/nodeScaleF),legdata(1,:))
    
    pos = [1.45-(str2num(legdata(2,:))/nodeScaleF)/2, ...
           (0.9-0.25)-(0.5*str2num(legdata(2,:))/nodeScaleF+3*str2num(legdata(1,:))/nodeScaleF), ...
           str2num(legdata(2,:))/nodeScaleF, ...
           str2num(legdata(2,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.020 0.729 0.859],'EdgeColor','w','LineWidth',0.1);
    text(1.6,(0.9-0.25)-(3*str2num(legdata(1,:))/nodeScaleF),legdata(2,:))
    
    pos = [1.45-(str2num(legdata(3,:))/nodeScaleF)/2 (0.9-0.25)-(0.5*str2num(legdata(3,:))/nodeScaleF+str2num(legdata(2,:))/nodeScaleF+5.5*str2num(legdata(1,:))/nodeScaleF) str2num(legdata(3,:))/nodeScaleF str2num(legdata(3,:))/nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.020 0.729 0.859],'EdgeColor','w','LineWidth',0.1);
    text(1.6,(0.9-0.25)-(str2num(legdata(2,:))/nodeScaleF+5.5*str2num(legdata(1,:))/nodeScaleF),legdata(3,:))
    
    text(1.4,(0.9-0.25)-(7*str2num(legdata(3,:))/nodeScaleF),'edge weight:')
    
    range = threshMax - minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((threshMax-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((threshMax-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [(0.9-0.25)-(9*str2num(legdata(3,:))/nodeScaleF) (0.9-0.25)-(9*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,(0.9-0.25)-(9*str2num(legdata(3,:))/nodeScaleF),num2str(round(threshMax-2/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((threshMax-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((threshMax-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [(0.9-0.25)-(10.5*str2num(legdata(3,:))/nodeScaleF) (0.9-0.25)-(10.5*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,(0.9-0.25)-(10.5*str2num(legdata(3,:))/nodeScaleF),num2str(round(threshMax-1/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((threshMax)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((threshMax)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [(0.9-0.25)-(12*str2num(legdata(3,:))/nodeScaleF) (0.9-0.25)-(12*str2num(legdata(3,:))/nodeScaleF)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,(0.9-0.25)-(12*str2num(legdata(3,:))/nodeScaleF),num2str(round(threshMax, 4)))
    
end

%% save figure

figName = strcat([pNum, '_', plotType, '_NetworkPlot']);
figPath = fullfile(figFolder, figName);

if saveFigure
    if exist('figureHandle', 'var')
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, figureHandle);
    elseif ~isfield(Params, 'oneFigure')
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
    else 
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, Params.oneFigure);
    end 
end 


%  output figure handle 
if exist('figureHandle', 'var')
    % do nothing
elseif ~isfield(Params, 'oneFigure')
    figureHandle = F1;
else 
    figureHandle = Params.oneFigure;
end 




end