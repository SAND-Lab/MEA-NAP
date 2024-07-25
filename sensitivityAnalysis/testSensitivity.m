%% MEANAP Sensitivity Analysis
addpath(genpath('/home/timothysit/AnalysisPipeline/Functions'))
% This script asks what is the smallest difference in network
% metrics that can be detected by MEA-NAP
numNodes = 60;
numRandomNetworks = 100;
p = 0.1;
G = rand(numNodes,numNodes) < p;
G = triu(G,1);
% Make the graph symmetric
G = G + G';
% sample weights from a distribution and assign them to
numEdges = sum(sum(G == 1));
edgeWeights = rand(numEdges, 1);
G(G == 1) = edgeWeights;
G = (G + G') / 2;
% remove diagonal elements
G(logical(eye(size(G)))) = 0;

%% Betweeness centrality
numRandomNetworks = 100;
numNodes = 60;
p = 0.2;
BC_store = size(numRandomNetworks, 1) + nan;
num_modules_store = size(numRandomNetworks, 1) + nan;
for rand_idx = 1:numRandomNetworks
    G_random = genRandNetwork(numNodes, p);
    smallFactor = 0.01; % prevent division by zero
    pathLengthNetwork = 1 ./ (G_random + smallFactor);
    % Betweeness centrality
    BC = betweenness_wei(pathLengthNetwork);
    BC_norm = BC/((length(G_random)-1)*(length(G_random)-2));
    BC_store(rand_idx) = mean(BC_norm);
    % Calculate number of modules
    [Ci,Q,~] = mod_consensus_cluster_iterate(G_random,0.4,50);
    nMod = max(Ci);
    num_modules_store(rand_idx) = nMod;
end

figure;
hist(BC_store)

%% Number of modules : get random networks

numNetworksToCompare = 15;
numberOfModulesGroup1 = [3, 3, 3, 3, 3];  %[5, 5, 5, 5, 5];
numberOfModulesGroup2 = [3, 4, 5, 6, 7];  % [6, 7, 8, 9, 10];

pGroup1 = [0.7, 0.7, 0.7, 0.7, 0.7]; 
pGroup2 = [0.7, 0.7, 0.7, 0.7, 0.7];

maxNumRandomNetworks = 2000;
numNodes = 60;
numRewiringRepeats = 20;

edgeReplacementProb = [0, 0.1, 0.2, 0.3, 0.4, 0.5]; 

numPairs = length(numberOfModulesGroup1);

group1NetworkStore = cell(numNetworksToCompare, numPairs);
group2NetworkStore = cell(numNetworksToCompare, numPairs);
networkMetricStore = zeros(maxNumRandomNetworks, numPairs, 2) + nan;

for pairIdx = 1:numPairs 
    
    group1networkCounter = 1; 
    group2networkCounter = 1;
    
    % sample networks until we get 15 with group 1 number of modules
    for rand_idx = 1:maxNumRandomNetworks
        
        success = 0;
        
        G_random_1 = genRandNetwork(numNodes, pGroup1(pairIdx));
        G_random_2 = genRandNetwork(numNodes, pGroup2(pairIdx));
        
        [Ci,Q,~] = mod_consensus_cluster_iterate(G_random_1,0.4,50);
        nMod1 = max(Ci);
        
        [Ci,Q,~] = mod_consensus_cluster_iterate(G_random_2,0.4,50);
        nMod2 = max(Ci);
        
        networkMetricStore(rand_idx, pairIdx, 1) = nMod1;
        networkMetricStore(rand_idx, pairIdx, 2) = nMod2;
                
        if (nMod1 == numberOfModulesGroup1(pairIdx)) && (group1networkCounter <= numNetworksToCompare)
            group1NetworkStore{group1networkCounter, pairIdx} = G_random_1;
            group1networkCounter = group1networkCounter + 1;
        elseif (nMod2 ==  numberOfModulesGroup2(pairIdx)) && (group2networkCounter <= numNetworksToCompare)
            group2NetworkStore{group2networkCounter, pairIdx} = G_random_2;
            group2networkCounter = group2networkCounter + 1;
        end
        
        if (group1networkCounter > numNetworksToCompare) && (group1networkCounter > numNetworksToCompare)
           fprintf(sprintf('Finished finding networks at iteration %.f \n', rand_idx))
           success = 1;
           break  
        end
    end
    
    if success == 0
        fprintf('Failed to find networks \n')
    end
    
end

% save these results 
save('nModulesSampleNetworks.mat', 'group1NetworkStore', 'group2NetworkStore', ...
    'numNetworksToCompare', 'numberOfModulesGroup1', 'numberOfModulesGroup2', ...
    'pGroup1', 'pGroup2', 'maxNumRandomNetworks', 'numNodes');


%% do random re-wiring, then compute the number of modules 

probRejectNullPerEdgeReplacementProb = zeros(length(edgeReplacementProb), numPairs) + nan; 

progressbar()
for pairIdx = 1:numPairs 
    for replaceIdx = 1:length(edgeReplacementProb)
       replaceProb = edgeReplacementProb(replaceIdx);

       reject_null_store = zeros(numRewiringRepeats, 1) + nan;

       for rewiringIdx = 1:numRewiringRepeats
           group1Metric = zeros(numNetworksToCompare, 1) + nan;
           group2Metric = zeros(numNetworksToCompare, 1) + nan;

           for netIdx = 1:numNetworksToCompare
               group1networkRandomised = rewireNetwork(group1NetworkStore{netIdx, pairIdx}, replaceProb);
               [Ci,Q,~] = mod_consensus_cluster_iterate(group1networkRandomised,0.4,50);
               nMod = max(Ci);
               group1Metric(netIdx) = nMod;

               group2networkRandomised = rewireNetwork(group2NetworkStore{netIdx, pairIdx}, replaceProb);
               [Ci,Q,~] = mod_consensus_cluster_iterate(group2networkRandomised,0.4,50);
               nMod = max(Ci);
               group2Metric(netIdx) = nMod;
           end

           % do significance test on the two sets of network (assume
           % independence for now)
           [reject_null, p_val] = ttest(group1Metric, group2Metric);
           reject_null_store(rewiringIdx) = reject_null;

       end

       probRejectNullPerEdgeReplacementProb(replaceIdx, pairIdx) = mean(reject_null_store);

 
    end
    progressbar(pairIdx / numPairs)
    fprintf('Sensitivity analysis complete for number of modules complete \n') 
end 

%% save results 

save('nModulesSampleNetworks.mat', 'probRejectNullPerEdgeReplacementProb', ...
     'numRewiringRepeats', 'edgeReplacementProb', '-append')



%% Plot results

% subplots: true number of differences in modules
% x-axis : percentage of re-wiring
% y-axis : number of times that the difference is statistically significant

figure;
for pairIdx = 1:numPairs
    subplot(1, numPairs, pairIdx)
    plot(edgeReplacementProb, probRejectNullPerEdgeReplacementProb(:, pairIdx), 'k', 'linewidth', 1.5)
    hold on
    scatter(edgeReplacementProb, probRejectNullPerEdgeReplacementProb(:, pairIdx), 'k', 'filled')
    title(sprintf('%.f vs %.f', numberOfModulesGroup1(pairIdx), numberOfModulesGroup2(pairIdx)))
    
    if pairIdx == 1
        xlabel('Edge replacement probability')
        ylabel('Proportion of succesful detection')
    end
    ylim([-0.05, 1.05]);
    set(gca,'TickDir','out');
    box off
end
sgtitle('Number of modules')
set(gcf, 'color', 'w')





%% Participation coefficient



%% Small-worldnes omega 

swGroup1 = {[0, 0.25], [0, 0.25], [0, 0.25], [0, 0.25]};
swGroup2 = {[0, 0.25], [0.25, 0.5], [0.5, 0.75], [0.75, 1]};

% test code to generate small-world network 
K_edge = 3;
beta = 0.4; % 0 = ring, 1 = random
G_random_1 = genRandSmallWorldNetwork(numNodes, K_edge, beta);

% beta | K_edge |  swW table 
% ---------------------------
% 1.00 | 20     | 0.0447
% 1.00 | 10     | 0.2277
% 1.00 | 5      | 0.5373
% 1.00 | 3      | 0.7793
% 0.5  | 3      | 0.5110
% 0.4  | 3      | 0.25 
% 0.3  | 3      | 0.1104
% 0.2  | 3      | -0.3351
% 0.00 | 3      | -0.7639
% 0.50 | 10     | 0.2018
% 0.15 | 10     | 0.1329 
% 0.00 | 10     | -0.1750

betaGroup1 = [0.3, 0.3, 0.3, 0.3];
betaGroup2 = [0.3, 0.4, 0.5, 1]; 

numPairs = length(betaGroup1);
group1NetworkStore = cell(numNetworksToCompare, numPairs);
group2NetworkStore = cell(numNetworksToCompare, numPairs);
networkMetricStore = zeros(maxNumRandomNetworks, numPairs, 2) + nan;

for pairIdx = 1:numPairs 
    
    group1networkCounter = 1; 
    group2networkCounter = 1;
    
    swGroup1Range = swGroup1{pairIdx};
    swGroup2Range = swGroup2{pairIdx};
    
    % sample networks until we get 15 with group 1 number of modules
    for rand_idx = 1:maxNumRandomNetworks
        
        success = 0;
        
        % G_random_1 = genRandNetwork(numNodes, pGroup1(pairIdx));
        % G_random_2 = genRandNetwork(numNodes, pGroup2(pairIdx));
        G_random_1 = genRandSmallWorldNetwork(numNodes, K_edge, betaGroup1(pairIdx));
        G_random_2 = genRandSmallWorldNetwork(numNodes, K_edge, betaGroup2(pairIdx));
        
        ITER = 10000;
        Z = pdist(G_random_1);
        D = squareform(Z);
        [LatticeNetwork_1, Rrp, ind_rp, eff, met] = latmio_und_v2(G_random_1, ITER, D,'SW');
        
        Z = pdist(G_random_2);
        D = squareform(Z);
        [LatticeNetwork_2, Rrp, ind_rp, eff, met] = latmio_und_v2(G_random_2, ITER, D,'SW');
        
        ITER = 5000;
        [R, ~,met2] = randmio_und_v2(G_random_1, ITER,'SW');
        [SW, SWw_group1, CC, PL] = small_worldness_RL_wu(G_random_1, R, LatticeNetwork_1);
        
        [R, ~,met2] = randmio_und_v2(G_random_2, ITER,'SW');
        [SW, SWw_group2, CC, PL] = small_worldness_RL_wu(G_random_2, R, LatticeNetwork_2);
        
        
        networkMetricStore(rand_idx, pairIdx, 1) = SWw_group1;
        networkMetricStore(rand_idx, pairIdx, 2) = SWw_group2;
                
        if (SWw_group1 > swGroup1Range(1)) && (SWw_group1 < swGroup1Range(2)) && (group1networkCounter <= numNetworksToCompare)
            group1NetworkStore{group1networkCounter, pairIdx} = G_random_1;
            group1networkCounter = group1networkCounter + 1;
            fprintf('Group 1 hit! \n')
        elseif (SWw_group2 > swGroup2Range(1)) && (SWw_group2 < swGroup2Range(2)) && (group2networkCounter <= numNetworksToCompare)
            group2NetworkStore{group2networkCounter, pairIdx} = G_random_2;
            group2networkCounter = group2networkCounter + 1;
            fprintf('Group 2 hit! \n')
        end
        
        if (group1networkCounter > numNetworksToCompare) && (group2networkCounter > numNetworksToCompare)
           fprintf(sprintf('Finished finding networks at iteration %.f \n', rand_idx))
           success = 1;
           break  
        end
    end
    
    if success == 0
        fprintf('Failed to find networks \n')
    end
    
end

%% Temp code to only get group2 

swGroup1 = {[0, 0.25], [0, 0.25], [0, 0.25], [0, 0.25]};
swGroup2 = {[0, 0.25], [0.25, 0.5], [0.5, 0.75], [0.75, 1]};

% test code to generate small-world network 
K_edge = 3;
beta = 0.4; % 0 = ring, 1 = random
G_random_1 = genRandSmallWorldNetwork(numNodes, K_edge, beta);

% beta | K_edge |  swW table 
% ---------------------------
% 1.00 | 20     | 0.0447
% 1.00 | 10     | 0.2277
% 1.00 | 5      | 0.5373
% 1.00 | 3      | 0.7793
% 0.5  | 3      | 0.5110
% 0.4  | 3      | 0.25 
% 0.3  | 3      | 0.1104
% 0.2  | 3      | -0.3351
% 0.00 | 3      | -0.7639
% 0.50 | 10     | 0.2018
% 0.15 | 10     | 0.1329 
% 0.00 | 10     | -0.1750

betaGroup1 = [0.3, 0.3, 0.3, 0.3];
betaGroup2 = [0.3, 0.4, 0.5, 1]; 

numPairs = length(betaGroup1);
group2NetworkStore = cell(numNetworksToCompare, numPairs);
networkMetricStore = zeros(maxNumRandomNetworks, numPairs, 2) + nan;

for pairIdx = 1:numPairs 
    
    group2networkCounter = 1;
    
    swGroup2Range = swGroup2{pairIdx};
    
    % sample networks until we get 15 with group 1 number of modules
    for rand_idx = 1:maxNumRandomNetworks
        
        success = 0;
        group1networkCounter = 20;
        SWw_group1 = nan;
        % G_random_1 = genRandNetwork(numNodes, pGroup1(pairIdx));
        % G_random_2 = genRandNetwork(numNodes, pGroup2(pairIdx));
        % G_random_1 = genRandSmallWorldNetwork(numNodes, K_edge, betaGroup1(pairIdx));
        G_random_2 = genRandSmallWorldNetwork(numNodes, K_edge, betaGroup2(pairIdx));
        
        % ITER = 10000;
        % Z = pdist(G_random_1);
        % D = squareform(Z);
        % [LatticeNetwork_1, Rrp, ind_rp, eff, met] = latmio_und_v2(G_random_1, ITER, D,'SW');
        
        Z = pdist(G_random_2);
        D = squareform(Z);
        [LatticeNetwork_2, Rrp, ind_rp, eff, met] = latmio_und_v2(G_random_2, ITER, D,'SW');
        
        % ITER = 5000;
        % [R, ~,met2] = randmio_und_v2(G_random_1, ITER,'SW');
        % [SW, SWw_group1, CC, PL] = small_worldness_RL_wu(G_random_1, R, LatticeNetwork_1);
        
        [R, ~,met2] = randmio_und_v2(G_random_2, ITER,'SW');
        [SW, SWw_group2, CC, PL] = small_worldness_RL_wu(G_random_2, R, LatticeNetwork_2);
        
        networkMetricStore(rand_idx, pairIdx, 2) = SWw_group2;
                
        if (SWw_group1 > swGroup1Range(1)) && (SWw_group1 < swGroup1Range(2)) && (group1networkCounter <= numNetworksToCompare)
            group1NetworkStore{group1networkCounter, pairIdx} = G_random_1;
            group1networkCounter = group1networkCounter + 1;
            fprintf('Group 1 hit! \n')
        elseif (SWw_group2 > swGroup2Range(1)) && (SWw_group2 < swGroup2Range(2)) && (group2networkCounter <= numNetworksToCompare)
            group2NetworkStore{group2networkCounter, pairIdx} = G_random_2;
            group2networkCounter = group2networkCounter + 1;
            fprintf('Group 2 hit! \n')
        end
        
        if (group1networkCounter > numNetworksToCompare) && (group2networkCounter > numNetworksToCompare)
           fprintf(sprintf('Finished finding networks at iteration %.f \n', rand_idx))
           success = 1;
           break  
        end
    end
    
    if success == 0
        fprintf('Failed to find networks \n')
    end
    
end



%% save these results 
save('smallWorldOmegaSampleNetworks.mat', 'group1NetworkStore', 'group2NetworkStore', ...
    'networkMetricStore', ...
    'numNetworksToCompare', 'swGroup1', 'swGroup2', ...
    'numNodes', 'K_edge', 'betaGroup1', 'betaGroup2', 'maxNumRandomNetworks');

%% Do the re-wiring

numRewiringRepeats = 20;
edgeReplacementProb = [0, 0.1, 0.2, 0.3, 0.4, 0.5]; 
numPairs = size(swGroup1, 2);

probRejectNullPerEdgeReplacementProb = zeros(length(edgeReplacementProb), numPairs) + nan; 

progressbar()
parpool(8)
for pairIdx = [3, 4]
    tic
    for replaceIdx = 1:length(edgeReplacementProb)
       replaceProb = edgeReplacementProb(replaceIdx);

       reject_null_store = zeros(numRewiringRepeats, 1) + nan;
       
       parfor rewiringIdx = 1:numRewiringRepeats
           group1Metric = zeros(numNetworksToCompare, 1) + nan;
           group2Metric = zeros(numNetworksToCompare, 1) + nan;

           for netIdx = 1:numNetworksToCompare
               
               group1networkRandomised = rewireNetwork(group1NetworkStore{netIdx, pairIdx}, replaceProb);
               group2networkRandomised = rewireNetwork(group2NetworkStore{netIdx, pairIdx}, replaceProb);
               
               ITER = 10000;
               Z = pdist(group1networkRandomised);
               D = squareform(Z);
               [LatticeNetwork_1, Rrp, ind_rp, eff, met] = latmio_und_v2(group1networkRandomised, ITER, D,'SW');

               Z = pdist(group2networkRandomised);
               D = squareform(Z);
               [LatticeNetwork_2, Rrp, ind_rp, eff, met] = latmio_und_v2(group2networkRandomised, ITER, D,'SW');

               ITER = 5000;
               [R, ~,met2] = randmio_und_v2(group1networkRandomised, ITER,'SW');
               [SW, SWw_group1, CC, PL] = small_worldness_RL_wu(group1networkRandomised, R, LatticeNetwork_1);

               [R, ~,met2] = randmio_und_v2(group2networkRandomised, ITER,'SW');
               [SW, SWw_group2, CC, PL] = small_worldness_RL_wu(group2networkRandomised, R, LatticeNetwork_2);
                
               group1Metric(netIdx) = SWw_group1;
               group2Metric(netIdx) = SWw_group2;
           end

           % do significance test on the two sets of network (assume
           % independence for now)
           [reject_null, p_val] = ttest(group1Metric, group2Metric);
           reject_null_store(rewiringIdx) = reject_null;

       end

       probRejectNullPerEdgeReplacementProb(replaceIdx, pairIdx) = mean(reject_null_store);

 
    end
    toc
    progressbar(pairIdx / numPairs)
    fprintf('Sensitivity analysis complete for number of modules complete \n') 
end 

delete(gcp('nocreate'))

%% Save results

save('smallWorldOmegaSampleNetworks.mat', 'probRejectNullPerEdgeReplacementProb', ...
     'numRewiringRepeats', 'edgeReplacementProb', '-append')

 
%% Participation Coefficient 
 
%% Network Density (This shouldn't take long)
maxNumRandomNetworks = 1000;
numNetworksToCompare = 15;
numNodes = 60;
densityGroup1= {[0.095, 0.105], [0.095, 0.105], [0.095, 0.105], [0.095, 0.105]};
densityGroup2 = {[0.095, 0.105], [0.095+0.005, 0.105+0.005], ...
                 [0.095+0.01, 0.105+0.01], [0.095+0.015, 0.105+0.015]};


pGroup1 = [0.1, 0.1, 0.1, 0.1];
pGroup2 = [0.1, 0.105, 0.11, 0.115];

numPairs = length(densityGroup1);

group1NetworkStore = cell(numNetworksToCompare, numPairs);
group2NetworkStore = cell(numNetworksToCompare, numPairs);
networkMetricStore = zeros(maxNumRandomNetworks, numPairs, 2) + nan;

for pairIdx = 1:numPairs 
    
    group1networkCounter = 1; 
    group2networkCounter = 1;
    densityGroup1Range = densityGroup1{pairIdx};
    densityGroup2Range = densityGroup2{pairIdx};
    
    % sample networks until we get 15 with group 1 number of modules
    for rand_idx = 1:maxNumRandomNetworks
        
        success = 0;
        
        G_random_1 = genRandNetwork(numNodes, pGroup1(pairIdx));
        G_random_2 = genRandNetwork(numNodes, pGroup2(pairIdx));
        
        [Dens1, ~, ~] = density_und(G_random_1);
        [Dens2, ~, ~] = density_und(G_random_2);
        
        networkMetricStore(rand_idx, pairIdx, 1) = Dens1;
        networkMetricStore(rand_idx, pairIdx, 2) = Dens2;
                
        if (Dens1 > densityGroup1Range(1)) && (Dens1 < densityGroup1Range(2)) && (group1networkCounter <= numNetworksToCompare)
            group1NetworkStore{group1networkCounter, pairIdx} = G_random_1;
            group1networkCounter = group1networkCounter + 1;
            fprintf('Group 1 hit! \n')
        elseif (Dens2 > densityGroup2Range(1)) && (Dens2 < densityGroup2Range(2)) && (group2networkCounter <= numNetworksToCompare)
            group2NetworkStore{group2networkCounter, pairIdx} = G_random_2;
            group2networkCounter = group2networkCounter + 1;
            fprintf('Group 2 hit! \n')
        end
        
        if (group1networkCounter > numNetworksToCompare) && (group2networkCounter > numNetworksToCompare)
           fprintf(sprintf('Finished finding networks at iteration %.f \n', rand_idx))
           success = 1;
           break  
        end
    end
    
    if success == 0
        fprintf('Failed to find networks \n')
    end
    
end

%% Do the re-wiring
numRewiringRepeats = 100;
edgeReplacementProb = [0, 0.1, 0.2, 0.3, 0.4, 0.5]; 
numPairs = size(densityGroup1, 2);

probRejectNullPerEdgeReplacementProb = zeros(length(edgeReplacementProb), numPairs) + nan; 

progressbar()
for pairIdx = 1:numPairs
    tic
    for replaceIdx = 1:length(edgeReplacementProb)
       replaceProb = edgeReplacementProb(replaceIdx);
       
       
       reject_null_store = zeros(numRewiringRepeats, 1) + nan;
       
       for rewiringIdx = 1:numRewiringRepeats
           group1Metric = zeros(numNetworksToCompare, 1) + nan;
           group2Metric = zeros(numNetworksToCompare, 1) + nan;

           for netIdx = 1:numNetworksToCompare
               
               group1networkRandomised = rewireNetwork(group1NetworkStore{netIdx, pairIdx}, replaceProb);
               group2networkRandomised = rewireNetwork(group2NetworkStore{netIdx, pairIdx}, replaceProb);
               
               [Dens1, ~, ~] = density_und(group1networkRandomised);
               [Dens2, ~, ~] = density_und(group2networkRandomised);
                
               group1Metric(netIdx) = Dens1;
               group2Metric(netIdx) = Dens2;
           end

           % do significance test on the two sets of network (assume
           % independence for now)
           [reject_null, p_val] = ttest(group1Metric, group2Metric);
           reject_null_store(rewiringIdx) = reject_null;

       end

       probRejectNullPerEdgeReplacementProb(replaceIdx, pairIdx) = mean(reject_null_store);

 
    end
    toc 
    progressbar(pairIdx / numPairs)
    fprintf('Sensitivity analysis complete for number of modules complete \n') 
end 

%% Save results

 save('networkDensitySampleNetworks.mat', ...
     'group1NetworkStore', 'group2NetworkStore', ...
     'networkMetricStore', ...
     'numNetworksToCompare', 'densityGroup1', 'densityGroup2', ...
     'numNodes', 'pGroup1', 'pGroup2', 'maxNumRandomNetworks', ...
     'probRejectNullPerEdgeReplacementProb', ...
     'numRewiringRepeats', 'edgeReplacementProb');

 %% Plot results 


 