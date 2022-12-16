function [NetMet] = ExtractNetMetOrganoid(adjMs, spikeTimes, lagval,Info,HomeDir,Params, spikeMatrix)
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
    maxSTTC(e) = max(edge_weights);

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
    
    [ND,MEW] = findNodeDegEdgeWeight(adjM,edge_thresh);
    
    % Node strength
    NS = strengths_und(adjM)';
    
    % Tim 2021-12-02: Actually strengths_und is just the sum for each node?
    % If you are using the function here: https://github.com/eglerean/NBEHBC/blob/master/code/external/BCT/2017_01_15_BCT/strengths_und.m
    % NS = sum(adjM)'; 
    
    % plot properties
    plotConnectivityProperties(adjM, e, lagval, maxSTTC, meanSTTC, ND, NS, MEW, char(Info.FN),Params, lagFolderName)
  
    
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
    
        plotNullModelIterations(met, met2, lagval, e, char(Info.FN), Params)
    
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
    
else
     fprintf('Not enough nodes to calculate network metrics! \n')
     SW = nan;
     SWw = nan;
     CC = nan;
     PL = nan;
     Eloc = nan;
     BC = nan;
 end
    
    % participation coefficient
%     PC = participation_coef(adjM,Ci,0);
    [PC,~,~,~] = participation_coef_norm(adjM,Ci);
    
    % within module degree z-score
    Z = module_degree_zscore(adjM,Ci,0);
    
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
    [hub_peripheral_xy, hub_metrics, hub_score_index] = ...
        fcn_find_hubs_wu(Info.channels,spikeMatrix,adjM,Params.fs);
    
    PC_raw_idx = find(contains(hub_metrics.metric_names, 'Participation coefficient'));
    PC_raw = hub_metrics.metrics_unsorted(:, PC_raw_idx);
    Cmcblty_idx = find(contains(hub_metrics.metric_names, 'Communicability'));
    Cmcblty = hub_metrics.metrics_unsorted(:, Cmcblty_idx);

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
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).aveControl = aveControl;
    end 

    if any(strcmp(netMetToCal, 'modalControl'))
        modalControl = modal_control(adjM);
        NetMet.(strcat('adjM',num2str(lagval(e)),'mslag')).modalControl = modalControl;
    end 

    %% electrode specific half violin plots
    % TODO: move the plotting to a separate function

    electrodeSpecificMetrics(ND, NS, MEW, Eloc, BC, PC, Z, lagval, ... 
            e, char(Info.FN), Params, lagFolderName)
    
    %% network plots
    [On,adjMord] = reorder_mod(adjM,Ci);

    try
        channels = Info.channels;
        channels(iN) = [];
    catch
        fprintf(2,'\n  WARNING: channel order not saved in spike matrix \n used default in line 50 of batch_getHeatMaps_fcn \n \n')
        channels = [47,48,46,45,38,37,28,36,27,17,26,16,35,25,15,14,24,34,..., 
            13,23,12,22,33,21,32,31,44,43,41,42,52,51,53,54,61,62,71,63, ..., 
            72,82,73,83,64,74,84,85,75,65,86,76,87,77,66,78,67,68,55,56,58,57];
    end
   
    StandardisedNetworkPlot(adjM, coords, edge_thresh, ND, 'MEA', char(Info.FN),'2',Params,lagval,e, lagFolderName);
   
    % grid network plot node degree betweeness centrality
    StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ND, 'Node degree', BC, 'Betweeness centrality', 'MEA', char(Info.FN), '3', Params, lagval, e, lagFolderName)
  
    % grid network plot node degree participation coefficient
    StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ND, 'Node degree', PC, 'Participation coefficient', 'MEA', char(Info.FN), '4', Params, lagval, e, lagFolderName)
  
    % grid network plot node strength local efficiency
    StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, NS, 'Node strength', Eloc, 'Local efficiency', 'MEA', char(Info.FN), '5', Params, lagval, e, lagFolderName)
  
    % simple circular network plot
    NDord = ND(On);
    StandardisedNetworkPlot(adjMord, coords, edge_thresh, NDord, 'circular', char(Info.FN),'6',Params,lagval,e, lagFolderName);
    
    
    % grid network plot for controllability metrics
    if any(strcmp(Params.unitLevelNetMetToPlot , 'aveControl'))
         StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ND, 'Node degree', ...
             aveControl, 'Average controllability', 'MEA', char(Info.FN), '3', Params, lagval, e, lagFolderName)
    end 

    if any(strcmp(Params.unitLevelNetMetToPlot , 'modalControl'))
         StandardisedNetworkPlotNodeColourMap(adjM, coords, edge_thresh, ND, 'Node degree', ...
             modalControl, 'Modal controllability', 'MEA', char(Info.FN), '3', Params, lagval, e, lagFolderName)
    end 

    % node cartography
    % NdCartDivOrd = NdCartDiv(On);
    % StandardisedNetworkPlotNodeCartography(adjMord, Params.coords, edge_thresh, NdCartDivOrd, 'circular', char(Info.FN), '7', Params, lagval, e)
    
   % colour map network plots where nodes are the same size
%     StandardisedNetworkPlotNodeColourMap2(adjM, coords, 0.00001, PC, 'Participation coefficient', 'grid', char(Info.FN), Params)
%     PCord = PC(On);
%     StandardisedNetworkPlotNodeColourMap2(adjMord, coords, 0.00001, PC, 'Participation coefficient', 'circular', char(Info.FN), Params)
%     

    clear coords
    
    %% reassign to structures
    
    Var = {'ND', 'MEW', 'NS', 'aN', 'Dens', 'Ci', 'Q', 'nMod', 'Eglob', ...,
        'CC', 'PL' 'SW','SWw' 'Eloc', 'BC', 'PC' , 'PC_raw', 'Cmcblty', 'Z', ...
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
    

% cd(HomeDir); cd(strcat('OutputData',Params.Date)); 
% cd('4_NetworkActivity'); cd('4A_IndividualNetworkAnalysis'); 
% cd(char(Info.Grp)); cd(char(Info.FN))

end

%% plot node cartography proportions
% plotNodeCartographyProportions(NetMet, lagval, char(Info.FN), Params)

%% plot metrics for different lag times
% TODO: move this
plotNetworkWideMetrics(NetMet, meanSTTC, maxSTTC, lagval, char(Info.FN), Params, networkActivityFolder)

end
