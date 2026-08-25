%% Checking betweenness centrality measure 
% also checks calculation of participation coefficient

num_random_networks = 1;
num_nodes_per_newtwork = 60;
allow_negative_weights = 0;
edge_thresh = 0.8;

% calculate the metrics used for finding hubs

if allow_negative_weights
    weight_min = -1;
    weight_max = 1;
else
    weight_min = 0;
    weight_max = 1;
end 

num_metric = 6;
node_metrics = zeros(num_random_networks, num_nodes_per_newtwork, num_metric);

for n_rand_network = 1:num_random_networks
    
    adjM = (weight_max-weight_min).*rand(num_nodes_per_newtwork, num_nodes_per_newtwork) + weight_min;
    [ND,EW] = findNodeDegEdgeWeight(adjM,edge_thresh);
    
    % Participation coefficient (why is this so complicated - some many
    % parameter to set?)
    [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    [PC,~,~,~] = participation_coef_norm(adjM,Ci, 100, 1);

    % Nodal efficiency 
    WCon = weight_conversion(adjM, 'lengths');
    DistM = distance_wei(WCon);
    mDist = mean(DistM,1);
    NE = 1./mDist;
    NE = NE';

    % Calculate bewteness centrality from lattice model of the network 
    ITER = 10000;
    Z = pdist(adjM);
    D = squareform(Z);
    [L,Rrp,ind_rp,eff,met] = latmio_und_v2(adjM,ITER,D,'SW');

    BCfromL = betweenness_wei(L);
    BCfromL = BCfromL/((length(adjM)-1)*(length(adjM)-2));

    % Calculate betweeness centrality just from the weight matrix converted to path lengths)
    smallValue = 0.001; % to avoid dividing by zero
    pathLengthMatirx = 1 ./ (adjM + smallValue);  % smaller weight means further away
    BC = betweenness_wei(pathLengthMatirx);
    BC = BC / ((length(adjM)-1)*(length(adjM)-2));  % scale based on network size
    
    [Ci_classic,Q_classic] = modularity_und(adjM);
    PCfromToolBox = participation_coef(adjM, Ci_classic); 
    
    % save the results
    node_metrics(n_rand_network, :, 1) = ND;
    node_metrics(n_rand_network, :, 2) = NE;
    node_metrics(n_rand_network, :, 3) = PC;
    node_metrics(n_rand_network, :, 4) = BCfromL;
    node_metrics(n_rand_network, :, 5) = BC;
    node_metrics(n_rand_network, :, 6) = PCfromToolBox;

end 

%% Plot results 

figure
num_plot = 1;
metric_names = {'ND', 'NE', 'PC', 'BCfromL', 'BCfrom1/W', 'PCfromToolBox'}; 

for n_y = 1:num_metric
    for n_x = 1:num_metric 
        subplot(num_metric, num_metric, num_plot)
        x_metric = node_metrics(:, :, n_x);
        y_metric = node_metrics(:, :, n_y);
        scatter(x_metric, y_metric)

        [r, p_val] = corrcoef(x_metric, y_metric);
        title_str = sprintf('r = %.3f, p = %.4f', r(1, 2), p_val(1, 2));
        title(title_str)

        if n_x == 1
            ylabel(metric_names{n_y})
        end 

        if n_y == num_metric
            xlabel(metric_names{n_x})
        end 

        num_plot = num_plot + 1;
    end 
end

set(gcf, 'color', 'white')

%% Participation Coefficient
figure; scatter(PC_original, PC2_original)
[R,P] = corrcoef(PC_original, PC2_original);
title(sprintf('R = %.2f, p = %.4f', R(1, 2), P(1, 2)))
ylabel('PC using modularity_und CI', 'Interpreter', 'none')
xlabel('PC using mod_consensus_cluster_iterate CI', 'Interpreter', 'none') 
set(gcf, 'color', 'white')

%% Load HPC data PC calculations using normalization and without 
close all 
adjM_folder_path = '/Users/timothysit/AnalysisPipeline/OutputData19May2022v12/ExperimentMatFiles';
cd(adjM_folder_path)
adjM_fnames = {dir('*.mat').name};
nFiles = length(adjM_fnames);
mainFig = figure('Position', [10 10 1200 600]);
nExamplesToPlt = 10;

coefPerFile = zeros(nFiles, 2);
pValPerFile = zeros(nFiles, 1);
rValPerFile = zeros(nFiles, 1);

for nFile = 1:length(adjM_fnames)
    fileData = load(adjM_fnames{nFile});

    if isfield(fileData.Params, 'oneFigure')
        f = fileData.Params.oneFigure;
        close(f);
    end 

    pc_norm = fileData.NetMet.adjM15mslag.PC;
    pc_raw = fileData.NetMet.adjM15mslag.PC_raw;

    % Get coefficients of a line fit through the data.
    coefficients = polyfit(pc_norm, pc_raw, 1);
    coefPerFile(nFile, :) = coefficients;
    [corrRVal,corrPVal] = corr(pc_norm, pc_raw, 'Type', 'Spearman');
    pValPerFile(nFile) = corrPVal;
    rValPerFile(nFile) = corrRVal;
    
    if nFile <= nExamplesToPlt
        subplot(2, 5, nFile)
        scatter(pc_norm, pc_raw);
        xlabel('Participation coefficient normalised')
        ylabel('Participation coefficient')
        title(adjM_fnames{nFile}, 'Interpreter','none')
        hold on
    end 

end 

set(mainFig, 'color', 'white');
figSaveFolder = '/Users/timothysit/AnalysisPipeline/plots';
figName = 'examplePCnormVsRaw';
saveas(gcf,fullfile(figSaveFolder, [figName '.png']));

%% Plot correlations 

figure;
scatter(rValPerFile, pValPerFile)
xlabel('Spearman correlation r')
ylabel('Spearman correlation p')
sig_threshold = 0.05;
yline(sig_threshold, 'Linestyle', '--')
set(gcf, 'color', 'white');
figSaveFolder = '/Users/timothysit/AnalysisPipeline/plots';
figName = 'spearmanCorrelationPCnormAndRaw';
saveas(gcf,fullfile(figSaveFolder, [figName '.png']));

%% Plot the line of best fit for each recording 

figure;
for nFile = 1:length(adjM_fnames)
    x_vals_to_interpolate = linspace(0, 1, 1000);
    y_predictions = polyval(coefPerFile(nFile, :), x_vals_to_interpolate);
    plot(x_vals_to_interpolate, y_predictions);
    hold on
end 
xlabel('Participation coefficient (normalised)')
ylabel('Participation coefficient (prediction)')
set(gcf, 'color', 'white');
figSaveFolder = '/Users/timothysit/AnalysisPipeline/plots';
figName = 'linearLineSlopePCnormVsRaw';
saveas(gcf,fullfile(figSaveFolder, [figName '.png']));




