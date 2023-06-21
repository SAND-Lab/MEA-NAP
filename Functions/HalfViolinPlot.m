function HalfViolinPlot(data, pos, colour, width, kdeWidthForOnePoint)
% Parameters
% -----------
% data : 
% pos : 
% color : 
% width : has nothing to do with kde computation, just the plotting (ie.
% not to be confused with bandwidth)
% kdeWidthForOnePoint : 

% created May 2020, author RCFeord

data(isnan(data)) = [];
data(isinf(data)) = [];
% bandwidth = 0.3*mean(data);
% bandwidth = 0.8;

% Scott's Rule of bandwidth selection
% ndim = 1;  % number of dimensions of KDE
% ndatapoints = length(data);
% sigma = std(data);
% bandwidth = 1.06 * sigma * ndatapoints .^ (-1 / (ndim + 4));

% Silverman's Rule (default matlab behaviour)
% [~, ~, bandwidth] = ksdensity(data);

% Sheather and Jones rule (seem to work better for multimodal)
% See: https://aakinshin.net/posts/kde-bw/  
% This seem to take forever... 
% bandwidth = bandwidth_SJ(data, 'norm');

% Improved Sheather and Jones rule 
if length(data) > 1 && std(data) > 0
    [bandwidth, density, xmesh, cdf] = improvedSJkde(data);
else
    if strcmp(kdeWidthForOnePoint, 'auto')
        [~, ~, bandwidth] = ksdensity(data);
    else 
        bandwidth = kdeWidthForOnePoint;  % small value, or zero is recommended
    end 
end 

% plot the violin
[f,xi] = ksdensity(data, 'Bandwidth',bandwidth);
% [f,xi] = ksdensity(data);

% f = density;
% xi = xmesh;

widthFactor = width/max(f);
obj.ViolinPlot = fill(f*widthFactor+pos+0.1,xi,colour);
hold on
obj.ViolinPlot.EdgeColor = colour;
obj.ViolinPlot.LineWidth = 1;
            
% plot the data points next to the violin
jitter = (rand(size(data))) * width;
drops_pos = jitter +pos - (width+0.1);
obj.ScatterPlot = scatter(drops_pos,data,20,colour,'filled');

% plot the data mean
meanValue = mean(data);
obj.MeanPlot = scatter(pos, meanValue, 100, [0 0 0], 'filled');

% % plot the standard deviation
% stdValue = std(data);
% obj.StdPlot = plot([pos pos],[meanValue-stdValue meanValue+stdValue],'Color',[0 0 0]);
% obj.StdPlot.LineWidth = 3;

% plot the standard error of the mean
semValue = std(data)/sqrt(length(data));
obj.StdPlot = plot([pos pos],[meanValue-semValue meanValue+semValue],'Color',[0 0 0]);
obj.StdPlot.LineWidth = 3;

end
