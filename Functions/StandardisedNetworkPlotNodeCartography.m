function [] = StandardisedNetworkPlotNodeCartography(adjM, coords, edge_thresh, NdCartDiv, plotType, FN, pNum, Params, lagval, e)

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
%   plotType - 'MEA' to plot nodes with their respective electrode
%       coordinates and 'circular' to plot nodes in a circle
%   FN - name of file/recording
%   pNum - number to precede name of figure when it is saved

% author RCFeord August 2021

%% plot

F1 = figure;
F1.OuterPosition = [50   100   700  550];
aesthetics; axis off; hold on

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

c1 = [0.8 0.902 0.310]; % light green
c2 = [0.580 0.706 0.278]; % medium green
c3 = [0.369 0.435 0.122]; % dark green
c4 = [0.2 0.729 0.949]; % light blue
c5 = [0.078 0.424 0.835]; % medium blue
c6 = [0.016 0.235 0.498]; % dark blue

if strcmp(plotType,'MEA')
    uniqueXc = sort(unique(xc));
    nodeScaleF = (uniqueXc(2)-uniqueXc(1))/2;
    for i = 1:length(adjM)
            eval(['Colour = c' num2str(NdCartDiv(i)) ';']);
            pos = [xc(i)-(0.5*nodeScaleF) yc(i)-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
            rectangle('Position',pos,'Curvature',[1 1],'FaceColor',Colour,'EdgeColor','w','LineWidth',0.1)
    end
    ylim([min(yc)-1 max(yc)+1])
    xlim([min(xc)-1 max(xc)+3.75])
end

if strcmp(plotType,'circular')
    
    nodeScaleF = 2/3*sqrt((abs(cos(t(1))-cos(t(2)))^2) + (abs(sin(t(1))-sin(t(2)))^2));
    
    for i = 1:length(adjM)
        eval(['Colour = c' num2str(NdCartDiv(i)) ';']);
         pos = [cos(t(i))-(0.5*nodeScaleF) sin(t(i))-(0.5*nodeScaleF) nodeScaleF nodeScaleF];
        rectangle('Position',pos,'Curvature',[1 1],'FaceColor',Colour,'EdgeColor','w','LineWidth',0.1)
    end
    ylim([-1.1 1.1])
    xlim([-1.1 1.9])
end

set(gca,'color','none')


%% format plot

if strcmp(plotType,'MEA')
       
    pos = [(max(xc)+1.5) max(yc)-(nodeScaleF*2/3) nodeScaleF*2/3 nodeScaleF*2/3];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c1,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+2,max(yc)-(nodeScaleF*2/3-nodeScaleF*2/6),'peripheral node')
    
    pos = [(max(xc)+1.5) max(yc)-((nodeScaleF*2/3)*3) nodeScaleF*2/3 nodeScaleF*2/3];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c2,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+2,max(yc)-((nodeScaleF*2/3)*3-nodeScaleF*2/6),'non-hub connector')
   
    pos = [(max(xc)+1.5) max(yc)-((nodeScaleF*2/3)*5) nodeScaleF*2/3 nodeScaleF*2/3];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c3,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+2,max(yc)-((nodeScaleF*2/3)*5-nodeScaleF*2/6),'non-hub kinless node')
    
    pos = [(max(xc)+1.5) max(yc)-((nodeScaleF*2/3)*7) nodeScaleF*2/3 nodeScaleF*2/3];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c4,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+2,max(yc)-((nodeScaleF*2/3)*7-nodeScaleF*2/6),'provincial hub')
   
    pos = [(max(xc)+1.5) max(yc)-((nodeScaleF*2/3)*9) nodeScaleF*2/3 nodeScaleF*2/3];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c5,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+2,max(yc)-((nodeScaleF*2/3)*9-nodeScaleF*2/6),'connector hub')
   
    pos = [(max(xc)+1.5) max(yc)-((nodeScaleF*2/3)*11) nodeScaleF*2/3 nodeScaleF*2/3];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c6,'EdgeColor','w','LineWidth',0.1);
    text(max(xc)+2,max(yc)-((nodeScaleF*2/3)*11-nodeScaleF*2/6),'kinless hub')
    
    
    text(max(xc)+1.5, max(yc)-((nodeScaleF*2/3)*14),'edge weight:')
    
    range = max(adjM(:))-minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-((nodeScaleF*2/3)*16)  max(yc)-((nodeScaleF*2/3)*16)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3, max(yc)-((nodeScaleF*2/3)*16),num2str(round(max(adjM(:))-2/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-((nodeScaleF*2/3)*18)  max(yc)-((nodeScaleF*2/3)*18)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-((nodeScaleF*2/3)*18),num2str(round(max(adjM(:))-1/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [max(xc)+1.5 max(xc)+2.5];
    posy = [max(yc)-((nodeScaleF*2/3)*20)  max(yc)-((nodeScaleF*2/3)*20)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(max(xc)+3,max(yc)-((nodeScaleF*2/3)*20),num2str(round(max(adjM(:)),4)))

end

if strcmp(plotType,'circular')
    
    pos = [1.3 1-(nodeScaleF) nodeScaleF nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c1,'EdgeColor','w','LineWidth',0.1);
    text(1.4,1-(nodeScaleF-nodeScaleF*1/2),'peripheral node')
    
    pos = [1.3 1-((nodeScaleF)*3) nodeScaleF nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c2,'EdgeColor','w','LineWidth',0.1);
    text(1.4,1-((nodeScaleF)*3-nodeScaleF*1/2),'non-hub connector')
   
    pos = [1.3 1-((nodeScaleF)*5) nodeScaleF nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c3,'EdgeColor','w','LineWidth',0.1);
    text(1.4,1-((nodeScaleF)*5-nodeScaleF*1/2),'non-hub kinless node')
    
    pos = [1.3 1-((nodeScaleF)*7) nodeScaleF nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c4,'EdgeColor','w','LineWidth',0.1);
    text(1.4,1-((nodeScaleF)*7-nodeScaleF*1/2),'provincial hub')
   
    pos = [1.3 1-((nodeScaleF)*9) nodeScaleF nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c5,'EdgeColor','w','LineWidth',0.1);
    text(1.4,1-((nodeScaleF)*9-nodeScaleF*1/2),'connector hub')
   
    pos = [1.3 1-((nodeScaleF)*11) nodeScaleF nodeScaleF];
    rectangle('Position',pos,'Curvature',[1 1],'FaceColor',c6,'EdgeColor','w','LineWidth',0.1);
    text(1.4,1-((nodeScaleF)*11-nodeScaleF*1/2),'kinless hub')
    
    
    text(1.3, 1-((nodeScaleF)*14),'edge weight:')
    
    range = max(adjM(:))-minNonZeroEdge;
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-2/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.3 1.4];
    posy = [1-((nodeScaleF)*16)  1-((nodeScaleF)*16)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.43, 1-((nodeScaleF)*16),num2str(round(max(adjM(:))-2/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:))-1/3*range)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.3 1.4];
    posy = [1-((nodeScaleF)*18)  1-((nodeScaleF)*18)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.43,1-((nodeScaleF)*18),num2str(round(max(adjM(:))-1/3*range,4)))
    
    lineWidthL = min_ew + (max_ew-min_ew)*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge));
    colourL = [1 1 1]-(light_c*(((max(adjM(:)))-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    posx = [1.3 1.4];
    posy = [1-((nodeScaleF)*20)  1-((nodeScaleF)*20)];
    plot(posx,posy,'LineWidth',lineWidthL,'Color',colourL);
    text(1.43,1-((nodeScaleF)*20),num2str(round(max(adjM(:)),4)))
    
    
end

%% save figure

if Params.figMat == 1
    saveas(gcf,strcat(pNum,'_',plotType,'_NetworkPlotNodeCartography.fig'));
end
if Params.figPng == 1
    saveas(gcf,strcat(pNum,'_',plotType,'_NetworkPlotNodeCartography.png'));
end
if Params.figEps == 1
    saveas(gcf,strcat(pNum,'_',plotType,'_NetworkPlotNodeCartography.eps'));
end

close all

end