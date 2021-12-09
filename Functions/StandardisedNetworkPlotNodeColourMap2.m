function [] = StandardisedNetworkPlotNodeColourMap2(adjM, coords, edge_thresh, z2, z2name, plotType, FN, Params)

% script to plot the graph network 
% 
% INPUTS:
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

% author RCFeord August 2021

%% plot

F1 = figure;
F1.OuterPosition = [50 100 760 550];
aesthetics; axis off; hold on

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
%% add nodes

mycolours = colormap;

if strcmp(plotType,'grid')
    uniqueXc = sort(unique(xc));
    nodeScaleF = (uniqueXc(2)-uniqueXc(1))/2;
    for i = 1:length(adjM)
        pos = [xc(i)-(0.5*nodeScaleF) yc(i)-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        if z2(i)>0
            try
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((z2(i)-min(z2))/(max(z2)-min(z2)))),1:3),'EdgeColor','w','LineWidth',0.1)
                
            catch
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((z2(i)-min(z2))/(max(z2)-min(z2)))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
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
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((z2(i)-min(z2))/(max(z2)-min(z2)))),1:3),'EdgeColor','w','LineWidth',0.1)
                
            catch
                rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(ceil(length(mycolours)*((z2(i)-min(z2))/(max(z2)-min(z2)))+0.00001),1:3),'EdgeColor','w','LineWidth',0.1)
            end
        else
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',mycolours(1,1:3),'EdgeColor','w','LineWidth',0.1)
        end
    end
    ylim([-1.1 1.1])
    xlim([-1.1 2])
end

set(gca,'color','none')


%% format plot

if strcmp(plotType,'grid')
      
    text(max(xc)+1.5,max(yc),'edge weight:')
    
    range = max(adjM(:))-minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-nodeScaleF*2 max(yc)-nodeScaleF*2];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(nodeScaleF*2),num2str(round(max(adjM(:))-2/3*range,2)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-nodeScaleF*3.5 max(yc)-nodeScaleF*3.5];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(3.5*nodeScaleF),num2str(round(max(adjM(:))-1/3*range,2)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-nodeScaleF*5 max(yc)-nodeScaleF*5];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-(5*nodeScaleF),num2str(round(max(adjM(:)),2)))
    
    cb = colorbar;
    cb.Ticks = [0 0.2 0.4 0.6 0.8 1];
    cb.TickLabels = {num2str(min(z2)), num2str(round(1/5*max(z2),2)), num2str(round(2/5*max(z2),2)), num2str(round(3/5*max(z2),2)), num2str(round(4/5*max(z2),2)), num2str(round(max(z2),2))};
    cb.Label.String = z2name;

end

if strcmp(plotType,'circular')
          
    text(1.4,0.9,'edge weight:')
    
    range = max(adjM(:))-minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [0.7 0.7];
    l4 =  plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,0.7,num2str(round(max(adjM(:))*1/3,2)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [0.55 0.55];
    l5 =  plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,0.55,num2str(round(max(adjM(:))*2/3,2)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.4 1.6];
    posy = [0.4 0.4];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.7,0.4,num2str(round(max(adjM(:)),2)))
    
    cb = colorbar;
    cb.Ticks = [0 0.2 0.4 0.6 0.8 1];
    cb.TickLabels = {num2str(min(z2)), num2str(round(1/5*max(z2),2)), num2str(round(2/5*max(z2),2)), num2str(round(3/5*max(z2),2)), num2str(round(4/5*max(z2),2)), num2str(round(max(z2),2))};
    cb.Label.String = z2name;
    
end

%% save figure

if Params.figMat == 1
    saveas(gcf,strcat(FN,'_',plotType,'_NetworkPlot',z2name,'.fig'));
end
if Params.figPng == 1
    saveas(gcf,strcat(FN,'_',plotType,'_NetworkPlot',z2name,'.png'));
end
if Params.figEps == 1
    saveas(gcf,strcat(FN,'_',plotType,'_NetworkPlot',z2name,'.eps'));
end

close all

end