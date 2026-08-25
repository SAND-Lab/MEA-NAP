
numRandomisations = 100;
numNodes = 60;
PC_store = zeros(numRandomisations, numNodes);
PC_rawstore = zeros(numRandomisations, numNodes);
for randomisationIdx = 1:numRandomisations
    randomTimeCourses = randi(1000, numNodes);
    adjM = corr(randomTimeCourses);
    adjM = abs(adjM);

    % remove self connections (set diagonal to 0)
    adjM(logical(eye(size(adjM)))) = 0;
    
    try
        [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    catch
         Ci = 0;
    end 
    
    [PC,~,~,~] = participation_coef_norm(adjM, Ci);

    M = community_louvain(adjM);
    PC_raw = participation_coef(adjM, M);
    
    PC_store(randomisationIdx, :) = PC;
    PC_rawstore(randomisationIdx, :) = PC_raw;
end 

%% Load data to find negative PCs 

matFolder = '/Volumes/Elements/MAT_files/AnalysisPipeline/OutputData03Nov2022/ExperimentMatFiles';
matFiles = dir(fullfile(matFolder, '*mat'));

hasNegPC = zeros(length(matFiles), 1);
meanEW = zeros(length(matFiles), 1);
ranks = zeros(length(matFiles), 1);
numModules = zeros(length(matFiles), 1);

for nMat = 1:length(matFiles)
    matFpath = fullfile(matFiles(nMat).folder, matFiles(nMat).name);
    matData = load(matFpath);
    PCvals = matData.NetMet.adjM10mslag.PC;
    if min(PCvals) < 0
        fprintf(sprintf('%.f \n', nMat))
        hasNegPC(nMat) = 1;
    end 
    adjM_nmat = matData.adjMs.adjM10mslag;
    adjM_nmat(~isfinite(adjM_nmat)) = 0;
    [Ci,Q,~] = mod_consensus_cluster_iterate(adjM_nmat,0.4,50);
    
    numM = length(unique(Ci));
    numModules(nMat) = numM;
    meanEW(nMat) = mean(adjM_nmat(:));
    ranks(nMat) = rank(adjM_nmat);

    close all
end 



%% look at file 22
matFolder = '/Volumes/Elements/MAT_files/AnalysisPipeline/OutputData03Nov2022/ExperimentMatFiles';
matFiles = dir(fullfile(matFolder, '*mat'));
nMat = 22;
matFpath = fullfile(matFiles(nMat).folder, matFiles(nMat).name);
matData = load(matFpath);
originalPC = matData.NetMet.adjM10mslag.PC;
adjM = matData.adjMs.adjM10mslag;

% make the diagonals have a value of 1 
% adjM(logical(eye(size(adjM)))) = 1;

[Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
[PC,~,~,~] = participation_coef_norm(adjM, Ci);
[PC_tim,~,~,~] = participation_coef_norm_tim(adjM, Ci);


% Run it a few more times 
numRand = 100;
numNodes = size(adjM, 2);
PC_store = zeros(numRand, numNodes);
for n = 1:numRand 
    % [PC,~,~,~] = participation_coef_norm(adjM, Ci);
    M = community_louvain(adjM);
    PC = participation_coef(adjM, M);
    PC_store(n, :) = PC;
end 


%% Run through the dataset and look at mean edge weight, rank etc. 

figure;
hasNegPCIdx = find(hasNegPC == 1);
xvals1 = zeros(length(hasNegPCIdx), 1);
xvals2 = zeros(length(hasNegPC) - length(hasNegPCIdx), 1) + 1;
scatter(xvals1, meanEW(hasNegPC == 1))
hold on
scatter(xvals2, meanEW(hasNegPC == 0))

xlim([-0.5, 1.5])
xticks([0, 1])
xticklabels({'Has negative PC', 'Normal'})
ylabel('Mean edge weight')
set(gcf, 'color', 'w')


figure;
hasNegPCIdx = find(hasNegPC == 1);
xvals1 = normrnd(0, 0.1, length(hasNegPCIdx), 1);
xvals2 = normrnd(1, 0.1, length(hasNegPC) - length(hasNegPCIdx), 1);
scatter(xvals1, ranks(hasNegPC == 1))
hold on
scatter(xvals2, ranks(hasNegPC == 0))

xlim([-0.5, 1.5])
xticks([0, 1])
xticklabels({'Has negative PC', 'Normal'})
ylabel('Rank')
set(gcf, 'color', 'w')


figure;
hasNegPCIdx = find(hasNegPC == 1);
xvals1 = normrnd(0, 0.1, length(hasNegPCIdx), 1);
xvals2 = normrnd(1, 0.1, length(hasNegPC) - length(hasNegPCIdx), 1);
scatter(xvals1, numModules(hasNegPC == 1))
hold on
scatter(xvals2, numModules(hasNegPC == 0))

xlim([-0.5, 1.5])
xticks([0, 1])
xticklabels({'Has negative PC', 'Normal'})
ylabel('Number of modules')
set(gcf, 'color', 'w')


%% check whether it's to do with the edge weight magnitude 

numRandomisations = 5;
numNodes = 58;
PC_store = zeros(numRandomisations, numNodes);
PC_rawstore = zeros(numRandomisations, numNodes);
PC_tim_store = zeros(numRandomisations, numNodes);
for randomisationIdx = 1:numRandomisations
    randomTimeCourses = randi(1000, numNodes);
    adjM = corr(randomTimeCourses);
    adjM = abs(adjM) / 100;  
    adjM(1, 3) = 0.7;
    adjM(3, 1) = 0.7;

    % remove self connections (set diagonal to 0)
    adjM(logical(eye(size(adjM)))) = 0;
    
    try
        [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    catch
         Ci = 0;
    end 
    
    [PC_original,~,~,~] = participation_coef_norm(adjM, Ci);
    % [PC_tim, PC_original, ~,~,~] = participation_coef_norm_tim(adjM, Ci);

    M = community_louvain(adjM);
    PC_raw = participation_coef(adjM, M);
    
    PC_store(randomisationIdx, :) = PC_original;
    PC_rawstore(randomisationIdx, :) = PC_raw;
    % PC_tim_store(randomisationIdx, :) = PC_tim;
end 

figure; 
scatter(PC_store(:), PC_tim_store(:))
hold on 
unity_vals = linspace(-0.2, 1, 100);
plot(unity_vals, unity_vals)
xline(0);
yline(0);
xlabel('normalized PC original code')
ylabel("normalized PC Tim's code")
set(gcf, 'color', 'white')


%% Compare my implemenation and their implementation 
matFolder = '/Volumes/Elements/MAT_files/AnalysisPipeline/OutputData03Nov2022/ExperimentMatFiles';
matFiles = dir(fullfile(matFolder, '*mat'));
nMat = 22;
matFpath = fullfile(matFiles(nMat).folder, matFiles(nMat).name);
matData = load(matFpath);
originalPC = matData.NetMet.adjM10mslag.PC;
adjM = matData.adjMs.adjM10mslag;

% make the diagonals have a value of 1 
% adjM(logical(eye(size(adjM)))) = 1;

numRandomisations = 30;
PC_tim_store = zeros(numRandomisations, size(adjM, 1));
PC_original_store = zeros(numRandomisations, size(adjM, 1));

for nRand = 1:numRandomisations
    [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    % [PC,~,~,~] = participation_coef_norm(adjM, Ci);
    [PC_tim, PC_original, ~,~,~] = participation_coef_norm_tim(adjM, Ci);
    PC_tim_store(nRand, :) = PC_tim;
    PC_original_store(nRand, :) = PC_original;
end 

M = community_louvain(adjM);
PC_raw = participation_coef(adjM, M);

figure; 
scatter(PC_original_store(:), PC_tim_store(:))
hold on 
unity_vals = linspace(-0.2, 1, 100);
plot(unity_vals, unity_vals)
xline(0);
yline(0);
xlabel('normalized PC original code')
ylabel("normalized PC Tim's code")
set(gcf, 'color', 'white')

% look at how they correlate with the original PC 
figure; 
subplot(1, 2, 1)
scatter(PC_original_store(1, :), PC_raw);
hold on 
unity_vals = linspace(-0.2, 1, 100);
plot(unity_vals, unity_vals)
xline(0);
yline(0);
xlabel('normalized PC original code')
ylabel("PC")

subplot(1, 2, 2)
scatter(PC_tim_store(1, :), PC_raw);
hold on 
unity_vals = linspace(-0.2, 1, 100);
xline(0);
yline(0);
plot(unity_vals, unity_vals)
xlabel("normalized PC Tim's code")
ylabel("PC")
set(gcf, 'color', 'white')

% Look at histogram of particular node
figure 
node = 29;
scatter(PC_original_store(:, node), PC_tim_store(:, node))


%% quick check 

rand_val_1 = randi(100, 1000, 1) / 100; 
rand_val_2 = randi(100, 1000, 1) / 100;
a = median(sqrt((rand_val_1 - rand_val_2) .^2));
b = sqrt(median((rand_val_1 - rand_val_2) .^2 ));

% a = median(sqrt(rand_val .^2));
% b = sqrt(median(rand_val .^2 ));



