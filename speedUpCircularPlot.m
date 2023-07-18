%% Make adjacency matrix 

rng(777); % set a random seed so it's reproducible
numNodes = 60;
numTimePoints = 1000;
randomTimeCourse = rand(numTimePoints, numNodes);
adjM = corr(randomTimeCourse);

Params.minNodeSize = 0.1;

adjM(adjM < 0) = 0;
z = rand(numNodes, 1);

%% Settings for circular plot 
edge_thresh = 0;
threshMax = max(adjM(:));
minNonZeroEdge = min(min(adjM(adjM>0))); 

%% Old method 
fprintf('Running old version of circular plot \n')
tic
figure;
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
for u = 1:size(xcot,1)
    plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
    hold on
end


max_z = max(z);
eval(['legdata = [''' num2str(round(max_z*1/3),'%02d') '''; ''' num2str(round(max_z*2/3),'%02d') '''; ''' num2str(round(max_z),'%02d') '''];']); % data for the legend


nodeScaleF = max_z/sqrt((abs(cos(t(1))-cos(t(2))))^2 + (abs(sin(t(1))-sin(t(2))))^2);

for i = 1:length(adjM)
    if z(i)>0
        nodeSize = max(Params.minNodeSize, z(i)/nodeScaleF);
        pos = [cos(t(i))-(0.5*nodeSize) sin(t(i))-(0.5*nodeSize) nodeSize nodeSize];
        rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.020 0.729 0.859],'EdgeColor','w','LineWidth',0.1)
    end
end
ylim([-1.1 1.1])
xlim([-1.1 1.9])



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

fprintf(sprintf('Number of connections plotted: %.f \n', sum(adjM(:) > 0)));
toc

%% New method 
fprintf('Running new version of circular plot \n')
tic
figure;
max_ew = 2; % maximum edge width for plotting
min_ew = 0.001; % min edge width
light_c = [0.8 0.8 0.8]; % lightest edge colour

adjMtril = tril(adjM,-1);
[~,linpos] = sort(adjMtril(:));
[xord,yord] = ind2sub(size(adjMtril),linpos);

t = linspace(-pi,pi,length(adjM) + 1).';

% This somehow computers the trajectory of the lines, but I am not exactly
% sure how... I think it will be easier to compute all possible lines at
% once, then subset
% eg. see: https://uk.mathworks.com/matlabcentral/fileexchange/48576-circulargraph

subset_index = (adjM(:) >= edge_thresh) & (xord ~= yord) & ~isnan(adjM(:));
%
%{
thetaLim = zeros(2, sum(subset_index));

u = [cos(t(xord)) sin(t(xord))]';
v = [cos(t(yord)) sin(t(yord))]';
u = u(:, subset_index);
v = v(:, subset_index);

roundUindex = find(round(u(1, :), 3) == 0);

x0 = -(u(2, :)-v(2, :))./(u(1, :).*v(2, :)-u(2, :).*v(1, :));
y0 =  (u(1, :)-v(1, :))./(u(1, :).*v(2, :)-u(2, :).*v(1, :));
r  = sqrt(x0.^2 + y0.^2 - 1);
thetaLim(1, :) = atan2(u(2, :) - y0, u(1, :) - x0)';
thetaLim(2, :) = atan2(v(2, :) - y0, v(1, :) - x0)';

xco = zeros(length(subset_index), 100);
yco = zeros(length(subset_index), 100);

for i = 1:sum(subset_index)
    
    u_i = u(:, i);
    v_i = v(:, i);

    if u_i(1) >= 0 && v_i(1) >= 0
        % ensure the arc is within the unit disk
        theta = [linspace(max(thetaLim(:, i)),pi,50),...
            linspace(-pi,min(thetaLim(:, i)),50)].';
    else
        theta = linspace(thetaLim(1, i),thetaLim(2, i), 100).';
    end
    
    xco(i, :) = r(i) * cos(theta)+x0(i);
    yco(i, :) = r(i) * sin(theta)+y0(i);

end 
%}

%

%
xco = zeros(sum(subset_index), 100);
yco = zeros(sum(subset_index), 100);

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
        % lineWidth(count) = min_ew + (max_ew-min_ew)*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
        % colour (count,:) = [1 1 1]-(light_c*((adjM(elecA,elecB)-minNonZeroEdge)/(threshMax-minNonZeroEdge)));
    end
end
%}

% linewidth and colour 
lineWidth = min_ew + (max_ew-min_ew)*((adjM(linpos)-minNonZeroEdge)/(threshMax-minNonZeroEdge));
lineWidth = lineWidth(subset_index)';

colour = [1 1 1] - (light_c.* ((adjM(linpos) - minNonZeroEdge)/(threshMax-minNonZeroEdge)));
colour = colour(subset_index, :);

% threshold the edge width (in case edge values are lower than the
% lower display bound) and colours
lineWidth(lineWidth < 0) = min_ew;
colour(colour > light_c(1)) = light_c(1);

[~,order] = sort(colour(:,1),'descend');
lineWidthT = lineWidth(:,order);
colourT = colour(order,:);
xcot = xco(order,:);
ycot = yco(order,:);

% Tim 2023-07-13: replace for loop with one plot, which should be faster
% since you don't have to re-write to the same figure handle so many times
% for u = 1:size(xcot,1)
%     plot(xcot(u,:),ycot(u,:),'LineWidth',lineWidthT(u),'Color',colourT(u,:));
%     hold on
% end

% plot(xcot,ycot,'LineWidth',lineWidthT(u),'Color',colourT(u,:));
linePlot = plot(xcot',ycot'); % 'LineWidth',lineWidthT,'Color',colourT);
set(linePlot, {'LineWidth'}, num2cell(lineWidthT'));
set(linePlot, {'Color'}, num2cell(colourT', [1, 3])');
hold on

max_z = max(z);
eval(['legdata = [''' num2str(round(max_z*1/3),'%02d') '''; ''' num2str(round(max_z*2/3),'%02d') '''; ''' num2str(round(max_z),'%02d') '''];']); % data for the legend


nodeScaleF = max_z/sqrt((abs(cos(t(1))-cos(t(2))))^2 + (abs(sin(t(1))-sin(t(2))))^2);

%{
for i = 1:length(adjM)
    if z(i)>0
        nodeSize = max(Params.minNodeSize, z(i)/nodeScaleF);
        pos = [cos(t(i))-(0.5*nodeSize) sin(t(i))-(0.5*nodeSize) nodeSize nodeSize];
        rectangle('Position',pos,'Curvature',[1 1],'FaceColor',[0.020 0.729 0.859],'EdgeColor','w','LineWidth',0.1)
    end
end
%}

% Try vectorised version of rectangle 
subset_z_index = find(z > 0);
nodeSize = max(Params.minNodeSize, z(subset_z_index) ./ nodeScaleF);
t_subset = t(subset_z_index+1);
% pos = [cos(t_subset)-(0.5*nodeSize) sin(t_subset)-(0.5*nodeSize) nodeSize nodeSize];
% rectangle('Position',pos);
pos = [cos(t_subset) sin(t_subset)];
viscircles(pos, nodeSize/2, 'Color', [0.020 0.729 0.859]); 

ylim([-1.1 1.1])
xlim([-1.1 1.9])



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

fprintf(sprintf('Number of connections plotted: %.f \n', sum(adjM(:) > 0)));
toc
