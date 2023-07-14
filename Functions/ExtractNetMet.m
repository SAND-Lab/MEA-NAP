function [NetMet] = ExtractNetMet(adjMs, spikeTimes, lagval,Info,HomeDir,Params, spikeMatrix, oneFigureHandle)
%
% Extract network metrics from adjacency matrices for organoid data
% 
% Parameters 
% ----------
% adjMs : N x N matrix
% spikeTimes : 
% lagval : int
%     lag for use in STTC calculation (in ms)
% Info : structure 
% HomeDir :
% Params : structure 
%     contains parameters for analysis and plotting, notably, the key
%     ones use are
%         Params.oneFigure : one shared figure handle for all figures (so figurse don't pop
%             in and out whilst the code is running the background)
%         coords : N X 2 matrix 
%            the coordinates of each network 
% 
% spikeMatrix : (N x T sparse or full matrix)
% 
% Returns
% ---------
% 
% NetMet : structure
%     structure with network metrics 
%     'ND' : Node degree
%     'EW' : mean edge weight of each node
%     'NS' : Node strength
%     'aN' : 
%     'Dens' : 
%     'Ci' :
%     'Q' :  
%     'nMod' : 
%     'Eglob' : 
%     'CC' :  
%     'PL' : 
%     'SW' : 
%     'SWw' :
%     'Eloc' :
%     'BC' : 
%     'PC' :  
%     'PC_raw' :
%     'Cmcblty' : 
%     'Z' : 
%     'Hub4' : 
%     'Hub3' : 
%     'NE' : 
% 
% 
% % List of plotting functions used in this script: 
%     - plotConnectivityProperties
%     - plotNullModelIterations
%     - electrodeSpecificMetrics
%     - StandardisedNetworkPlot
% 
% Parameters defined in this function: 
% 
% LatticeNetwork : (N x N matrix) 
% Ci : 
% aN : number of active nodes
% 
% Author : RCFeord March 2021
% Edited by Tim Sit


% specify list of network metrics to calculate
netMetToCal = Params.netMetToCal;

% edge threshold for adjM
edge_thresh = 0.0001;

% Preallocate 
meanSTTC = zeros(length(lagval), 1);
maxSTTC = zeros(length(lagval), 1);

% Folder to save figures 
networkActivityFolder = Params.networkActivityFolder;

for e = 1:length(lagval)
    
    % load adjM
    % eval(['adjM = adjMs.adjM' num2str(lagval(e)) 'mslag;']);
    lagValStr = strcat('adjM', num2str(lagval(e)), 'mslag');
    adjM = adjMs.(lagValStr);
    adjM(adjM<0) = 0;
    adjM(isnan(adjM)) = 0;
    
    % create subfolder
    lagFolderName = fullfile(networkActivityFolder, strcat(num2str(lagval(e)),'mslag'));
    if ~isfolder(lagFolderName)
        mkdir(lagFolderName)
    end 
 
    
    %% connectivity measures
    
    % mean and max STTC
    if Params.excludeEdgesBelowThreshold 
        edge_weights = adjM(adjM > 0);
    else
        edge_weights = adjM(:);
    end 

    meanSTTC(e) = nanmean(edge_weights);

    max_edge_weights = max(edge_weights);
    max_edge_weights = max([max_edge_weights, 0.001]);  % impose a minimum in case of all zeros
    maxSTTC(e) = max_edge_weights;

    % create list of channel IDs
    ChannelID = 1:size(adjM,1);
    
    %% active nodes
    
    aNtemp = sum(adjM,1);
    iN = find(aNtemp==0);
    aNtemp(aNtemp==0) = [];  % ??? why remove the zeros?
    aN = length(aNtemp);
    
    clear aNtemp
    
    %adjM(iN,:) = [];
    % adjM(:,iN) = [];

    % Tim 2022-10-14 fix
    nodeStrength = sum(adjM, 1);
    inclusionIndex = find(nodeStrength ~= 0);
    adjM = adjM(inclusionIndex, inclusionIndex);
    coords = Params.coords(inclusionIndex, :);
    Params.netSubsetChannels = Params.channels(inclusionIndex);
    
    %% node degree, edge weight, node strength
    if Params.excludeEdgesBelowThreshold 
        exclude_zeros = 1;
    else 
        exclude_zeros = 0;
    end 
    
    [ND,MEW] = findNodeDegEdgeWeight(adjM, edge_thresh, exclude_zeros);
    
    % Node strength
    NS = strengths_und(adjM)';
    
    % Tim 2021-12-02: Actually strengths_und is just the sum for each node?
    % If you are using the function here: https://github.com/eglerean/NBEHBC/blob/master/code/external/BCT/2017_01_15_BCT/strengths_und.m
    % NS = sum(adjM)'; 
    
    % plot properties
    plotConnectivityProperties(adjM, e, lagval, maxSTTC, meanSTTC, ...
        ND, NS, MEW, char(Info.FN),Params, lagFolderName, oneFigureHandle)
    
    
    % mean node degree of the network 
    NDmean = nanmean(ND);
    
    % mean node degree of the top 25% of the nodes by node degree 
    ND75thpercentile = prctile(ND, 75);
    NDtop25 = mean(ND(ND >= ND75thpercentile));
    
    % mean of the significant edges
    sigEdges = adjM(abs(adjM) > 0);
    sigEdgesMean = mean(sigEdges);
    
    % mean of the top 10 percentile of significant edges
    sigEdges90thpercentile = prctile(sigEdges, 90); 
    sigEdgesTop10 = mean(sigEdges(sigEdges >= sigEdges90thpercentile));
    
    % mean node strength 
    NSmean = nanmean(NS);
    
    %% if option stipulates binary adjM, binarise the matrix
    
    if strcmp(Params.adjMtype,'binary')
        adjM = weight_conversion(adjM, 'binarize');
    end
    
    %% network metrics - whole experiment
    
    % density
    [Dens, ~, ~] = density_und(adjM);

    % Modularity
    try
        [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    catch
        Ci = 0;
        Q = 0;
    end
    nMod = max(Ci);
    
    % global efficiency
    if strcmp(Params.adjMtype,'weighted')
        Eglob = efficiency_wei(adjM);
    elseif strcmp(Params.adjMtype,'binary')
        Eglob = efficiency_bin(adjM);
    end
    
    % Lattice-like model
    if length(adjM)> Params.minNumberOfNodesToCalNetMet
        ITER = 10000;
        Z = pdist(adjM);
        D = squareform(Z);
        % TODO: rename L to Lattice to avoid confusion with path length
        [LatticeNetwork,Rrp,ind_rp,eff,met] = latmio_und_v2(adjM,ITER,D,'SW');
    
        % Random rewiring model (d)
        ITER = 5000;
        [R, ~,met2] = randmio_und_v2(adjM, ITER,'SW');
    
        plotNullModelIterations(met, met2, lagval, e, char(Info.FN), Params, oneFigureHandle)
    
        %% Calculate network metrics (+normalization).
        
        [SW, SWw, CC, PL] = small_worldness_RL_wu(adjM,R,LatticeNetwork);
        
        % local efficiency
        %   For ease of interpretation of the local efficiency it may be
        %   advantageous to rescale all weights to lie between 0 and 1.
        if strcmp(Params.adjMtype,'weighted')
            adjM_nrm = weight_conversion(adjM, 'normalize');
            Eloc = efficiency_wei(adjM_nrm,2);
        elseif strcmp(Params.adjMtype,'binary')
            adjM_nrm = weight_conversion(adjM, 'normalize');
            Eloc = efficiency_bin(adjM_nrm,2);
        end
        
        % mean local efficiency across nodes
        ElocMean = mean(Eloc);
   
        % betweenness centrality
        %   Note: Betweenness centrality may be normalised to the range [0,1] as
        %   BC/[(N-1)(N-2)], where N is the number of nodes in the network.
        if strcmp(Params.adjMtype,'weighted')
            smallFactor = 0.01; % prevent division by zero
            pathLengthNetwork = 1 ./ (adjM + smallFactor);   
            BC = betweenness_wei(pathLengthNetwork);
        elseif strcmp(Params.adjMtype,'binary')
            BC = betweenness_bin(adjM);
        end
        BC = BC/((length(adjM)-1)*(length(adjM)-2));
        
        BC95thpercentile = prctile(BC, 95);
        BCmeantop5 = mean(BC(BC >= BC95thpercentile));
else
     fprintf('Not enough nodes to calculate network metrics! \n')
     SW = nan;
     SWw = nan;
     CC = nan;
     PL = nan;
     Eloc = nan;
     ElocMean = nan;
     BC = nan;
     BCmeantop5 = nan;
 end
    
    % participation coefficient
%     PC = participation_coef(adjM,Ci,0);
    if length(adjM) >= Params.minNumberOfNodesToCalNetMet
        [PC,~,~,~] = participation_coef_norm(adjM,Ci);
        % within module degree z-score
        Z = module_degree_zscore(adjM,Ci,0);
        
        % percentage of within-module z-score greater and less than zero
        percentZscoreGreaterThanZero = sum(Z > 0) / length(Z) * 100;
        percentZscoreLessThanZero = sum(Z < 0) / length(Z) * 100;
        
        % mean participation coefficient 
        PCmean = mean(PC);
        PC90thpercentile = prctile(PC, 90);
        PC10thpercentile = prctile(PC, 10);
        PCmeanTop10 = mean(PC(PC >= PC90thpercentile));
        PCmeanBottom10 = mean(PC(PC <= PC10thpercentile));
        
    else 
        PC = nan;
        Z = nan;
        
        percentZscoreGreaterThanZero = nan;
        percentZscoreLessThanZero = nan;
        PCmean = nan;
        PCmeanTop10 = nan;
        PCmeanBottom10 = nan;
    end 
    

    
    %% nodal efficiency
    
    if strcmp(Params.adjMtype,'weighted')
        WCon = weight_conversion(adjM, 'lengths');
        DistM = distance_wei(WCon);
        mDist = mean(DistM,1);
        NE = 1./mDist;
        NE = NE';
    elseif strcmp(Params.adjMtype,'binary')
        DistM = distance_bin(adjM);
        % exclude infinite distances (beware this treats disconnected nodes
        % as having distance of 0, which is counterintuitive)
        DistM = weight_conversion(DistM,'autofix');
        % correct distances of disconnected nodes to make minimum distance
        % of 1 because if they were connected path length would have to be
        % at least 1
        DistM(DistM==0) = 1;
        mDist = mean(DistM,1);        
        NE = 1./mDist;
        NE = NE';
    end
    
    %% Hub classification (only works when number of nodes exeed criteria)
    if aN >= Params.minNumberOfNodesToCalNetMet
        sortND = sort(ND,'descend');
        sortND = sortND(1:round(aN/10));
        hubNDfind = ismember(ND, sortND);
        [hubND, ~] = find(hubNDfind==1);
        
        sortPC = sort(PC,'descend');
        sortPC = sortPC(1:round(aN/10));
        hubPCfind = ismember(PC, sortPC);
        [hubPC, ~] = find(hubPCfind==1);
        
        sortBC = sort(BC,'descend');
        sortBC = sortBC(1:round(aN/10));
        hubBCfind = ismember(BC, sortBC);
        [hubBC, ~] = find(hubBCfind==1);
        
        sortNE = sort(NE,'descend');
        sortNE = sortNE(1:round(aN/10));
        hubNEfind = ismember(NE, sortNE);
        [hubNE, ~] = find(hubNEfind==1);
        
        hubs = [hubND; hubPC; hubBC; hubNE];
        [GC,~] = groupcounts(hubs);
        Hub4 = length(find(GC==4))/aN;
        Hub3 = length(find(GC>=3))/aN;
    else
        Hub4 = nan;
        Hub3 = nan;
    end 

    %% Find hubs and plot raster sorted by hubs 
    % convert spike times to spike matrix 
    if aN >= Params.minNumberOfNodesToCalNetMet
        [hub_peripheral_xy, hub_metrics, hub_score_index] = ...
            fcn_find_hubs_wu(Info.channels,spikeMatrix,adjM,Params.fs);
        
        PC_raw_idx = find(contains(hub_metrics.metric_names, 'Participation coefficient'));
        PC_raw = hub_metrics.metrics_unsorted(:, PC_raw_idx);
        Cmcblty_idx = find(contains(hub_metrics.metric_names, 'Communicability'));
        Cmcblty = hub_metrics.metrics_unsorted(:, Cmcblty_idx);
    else 
        hub_peripheral_xy = nan;
        hub_metrics = nan;
        hub_score_index = nan;
        PC_raw = nan;
        Cmcblty = nan;
    end 

    %% Calculate non-negative matrix factorisation components
    if any(strcmp(netMetToCal, 'num_nnmf_components'))
        fprintf('Calculating NMF \n')
        minSpikeCount = 10;
        includeRandomMatrix = 1;
        nmfCalResults = calNMF(spikeMatrix, Params.fs, Params.NMFdownsampleFreq, ...
                                Info.duration_s, minSpikeCount, includeRandomMatrix, ...
                                Params.includeNMFcomponents);
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).num_nnmf_components = nmfCalResults.num_nnmf_components;
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).nComponentsRelNS = nmfCalResults.nComponentsRelNS; 
        if Params.includeNMFcomponents
            NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).nmfFactors = nmfCalResults.nmfFactors;
            NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).nmfWeights = nmfCalResults.nmfWeights;
            NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).downSampleSpikeMatrix = nmfCalResults.downSampleSpikeMatrix;
        end 

    end 

    %% Calculate effective rank 
    if any(strcmp(netMetToCal,'effRank'))
        fprintf('Calculating effective rank \n')
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).effRank = ...
            calEffRank(spikeMatrix, Params.effRankCalMethod);
    end 

    %% Calculate average and modal controllability 
    if any(strcmp(netMetToCal, 'aveControl'))
        aveControl = ave_control(adjM);
        
        aveControlMean = mean(aveControl);
        aveControl75thpercentile = prctile(aveControl, 75);
        aveControlTop25 = mean(aveControlMean(aveControlMean >= aveControl75thpercentile));
        
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).aveControl = aveControl;
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).aveControlTop25 = aveControlTop25;
    end 

    if any(strcmp(netMetToCal, 'modalControl'))
        modalControl = modal_control(adjM);
        
        modalControlMean = mean(modalControl);
        modalControlThreshold = 0.975;
        modalControlPrctLessThanThreshold = sum(modalControl < modalControlThreshold) / length(modalControl);
        
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).modalControl = modalControl;
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).modalControlMean = modalControlMean;
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).modalControlPrctLessThanThreshold = modalControlPrctLessThanThreshold;
    end 
    
    
    %% Spatial and Temporal autocorrelation 
    if any(strcmp(netMetToCal, 'SA_lambda')) || any(strcmp(netMetToCal, 'SA_inf'))
        dist = squareform(pdist(Params.coords));
        cm = adjM;
        discretization = 15;  % arbitrary number to get good number of samples per bin
        [SA_lambda, SA_inf] = spatial_autocorrelation(dist, cm, discretization);
    end 
    
    if any(strcmp(netMetToCal, 'TA_regional')) || any(strcmp(netMetToCal, 'TA_global'))
        % TODO: calculate temporal autocorrelatio
    end 
    

    
    %% reassign to structures
    
    Var = {'ND', 'NDmean', 'NDtop25', ...
          'MEW', 'sigEdgesMean', 'sigEdgesTop10', ...
          'NS', 'NSmean', ...
          'aN', 'Dens', 'Ci', 'Q', 'nMod', 'Eglob', ...,
        'CC', 'PL' 'SW','SWw', ...
        'Eloc', 'ElocMean', ...
        'BC', 'BCmeantop5', ...
        'PC' , 'PC_raw', 'PCmean', 'PCmeanTop10', 'PCmeanBottom10', ...
        'Cmcblty', ...
        'Z', 'percentZscoreGreaterThanZero', 'percentZscoreLessThanZero', ...
        'Hub4','Hub3', 'NE'};

    % 'NCpn1', 'NCpn2','NCpn3','NCpn4','NCpn5','NCpn6' were moved
    
    for i = 1:length(Var)
        % TODO: remove eval 
        VN = cell2mat(Var(i));
        VNs = strcat('NetMet.adjM',num2str(lagval(e)),'mslag.',VN);
        eval([VNs '=' VN ';']);
    end
    
    % clear variables
    clear ND MEW NS Dens Ci Q nMod CC PL SW SWw Eloc BC PC Z Var NCpn1 NCpn2 NCpn3 NCpn4 NCpn5 NCpn6 Hub3 Hub4 NE PC_raw Cmcblty
    

end

end
