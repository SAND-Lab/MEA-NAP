function HalfViolinPlot(data, pos, colour, width, kdeWidthForOnePoint)
% Parameters
% -----------
% data : 
% pos : float
%    center position on the x axis
% color : 
% width : has nothing to do with kde computation, just the plotting (ie.
% not to be confused with bandwidth)
% kdeWidthForOnePoint : 

% created May 2020, author RCFeord
% Edited by Tim Sit to change kernel density estimation method

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
if (length(data) > 1) && (std(data) > 10^-8)  % using value slightly above zero to prevent numerical precision issues
    % zero_replacement =  (max(data) - min(data)) * 0.01;
    % zero_replacement = 0.02;
    % zero_idx = find(data == 0);
    % zero_replacement_vector = repmat(zero_replacement, length(zero_idx), 1);
    % zero_replacement_vector(1:2:end) = -zero_replacement;
    % data(zero_idx) = zero_replacement_vector;
    num_mesh_points = 2 ^ 12; % this is the default from the authors of improvedSJkde
    [bandwidth, density, xmesh, cdf] = improvedSJkde(data, num_mesh_points);
    % data(zero_idx) = 0; 
    
    % min_bandwidth = 0.03;
    min_bandwidth = (max(data) - min(data)) * 0.1;
    bandwidth = max([min_bandwidth, bandwidth]); 
    
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
