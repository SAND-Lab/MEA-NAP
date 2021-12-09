function HalfViolinPlot(data,pos,colour,width)

% created May 2020, author RCFeord

data(isnan(data)) = [];
data(isinf(data)) = [];
bandwidth = 0.3*mean(data);
% bandwidth = 0.8;

% plot the violin
% [f,xi] = ksdensity(data,'Bandwidth',bandwidth);
[f,xi] = ksdensity(data);
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
