% Plot relationship between mean node degree, PC, BC, Nodal Efficiency 

% load data
load("/Users/timothysit/AnalysisPipeline/OutputData07Apr2022/ExperimentMatFiles/HP_tc043_DIV28_07Apr2022.mat")

close all 

metrics_to_plot = {'ND', 'PC', 'BC', 'NE'}; 
num_metric_to_plot = length(metrics_to_plot);

p = [20 100 800 800];
set(0, 'DefaultFigurePosition', p)
figure;

plot_counter = 1;
for n_y = 1:num_metric_to_plot
    for n_x = 1:num_metric_to_plot 
        subplot(num_metric_to_plot, num_metric_to_plot, plot_counter);
        x_metric = NetMet.adjM15mslag.(metrics_to_plot{n_x});
        y_metric = NetMet.adjM15mslag.(metrics_to_plot{n_y});
        scatter(x_metric, y_metric)

        % Get top x metric 
        num_node = length(x_metric);
        x_metric_decending = sort(x_metric, 'descend');
        x_top_10 = x_metric_decending(1:round(num_node/10));
        xline(x_top_10(end))

        % Get top y metric
        y_metric_decending = sort(y_metric, 'descend');
        y_top_10 = y_metric_decending(1:round(num_node/10));
        yline(y_top_10(end))

        if n_x == 1
            ylabel(metrics_to_plot{n_y})
        end 

        if n_y == num_metric_to_plot
            xlabel(metrics_to_plot{n_x})
        end 

        plot_counter = plot_counter + 1;
    end 
end 
title_str = convertCharsToStrings(Info.FN{1});
sgtitle(title_str, 'Interpreter','none')
set(gcf, 'color', 'white')

fig_folder = '/Users/timothysit/AnalysisPipeline/OutputData07Apr2022/tempHubMetricPlots';
fig_name = strcat([Info.FN{1}, 'hub_metric_relationships']); 
fig_fullpath = fullfile(fig_folder, fig_name);
if Params.figMat == 1
    saveas(gcf,strcat([fig_fullpath, '.fig']));
end
if Params.figPng == 1
    saveas(gcf,strcat([fig_fullpath, '.png']));
end
if Params.figEps == 1
    saveas(gcf,strcat([fig_fullpath, '.eps']))
end

close(gcf)


%% Plot the ranks 
p = [20 100 1200 300];
set(0, 'DefaultFigurePosition', p)
figure;

for n_metric = 1:num_metric_to_plot
    subplot(1, num_metric_to_plot, n_metric)
    sorted_node_metric = sort(NetMet.adjM15mslag.(metrics_to_plot{n_metric}));
    plot(sorted_node_metric);
    xlabel('Rank (ascending)')
    ylabel(metrics_to_plot{n_metric})
    

    % Plot the top 10% 
    num_node = length(sorted_node_metric);
    sorted_node_metric_decending = flip(sorted_node_metric);
    top_10 = sorted_node_metric_decending(1:round(num_node/10));

    yline(top_10(end))


end 
sgtitle(Info.FN{1}, 'Interpreter','none')
set(gcf, 'color', 'white')

fig_folder = '/Users/timothysit/AnalysisPipeline/OutputData07Apr2022/tempHubMetricPlots';
fig_name = strcat([Info.FN{1}, 'hub_metric_ranks']); 
fig_fullpath = fullfile(fig_folder, fig_name);
if Params.figMat == 1
    saveas(gcf,strcat([fig_fullpath, '.fig']));
end
if Params.figPng == 1
    saveas(gcf,strcat([fig_fullpath, '.png']));
end
if Params.figEps == 1
    saveas(gcf,strcat([fig_fullpath, '.eps']))
end

close(gcf)