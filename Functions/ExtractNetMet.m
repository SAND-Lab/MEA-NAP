function [NetMet] = ExtractNetMet(adjMs, activityMatrix, lagval, Info, Params, originalCoords, channels, oneFigureHandle)
% EXTRACTNETMET Extract network metrics from adjacency matrices 
% 
% Parameters 
% ----------
% adjMs : N x N matrix
% lagval : int
%     lag for use in STTC calculation (in ms)
% Info : structure 
% Params : structure 
%     contains parameters for analysis and plotting, notably, the key
%     ones use are
%         Params.oneFigure : one shared figure handle for all figures (so figurse don't pop
%             in and out whilst the code is running the background)
%         coords : N X 2 matrix 
%            the coordinates of each network 
% coords : N x 2 matrix
%       spatial coordinates of the channels
% channels : N x 1 vector
%       channel numbering (for visualisation purpopse)
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
%     'aN' : Number of active nodes
%     'Dens' : Density
%     'Ci' : Community affiliation vector
%     'Q' : Modularity index
%     'nMod' : Number of modules
%     'Eglob' : Global efficiency
%     'CC' :  Clustering Coefficient
%     'PL' : Mean path length
%     'SW' : Small-worldness sigma coefficient
%     'SWw' : Small-wordlness omega coefficient
%     'Eloc' : Local efficiency
%     'BC' : Betwenness Centrality
%     'PC' : Participation Coefficient with normalization
%     'PC_raw' : Participation Coefficient without normalization
%     'Cmcblty' : Communicability
%     'Z' : Within-module z-score
%     'Hub4' : Number of hubs satisfying all 4 of the hub criteria
%     'Hub3' : Number of hubs satisfying 3 out of 4 of the hub criteria
%     'NE' : Nodal efficiency
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
unitMetToCal = Params.unitLevelNetMetToPlot;

% edge threshold for adjM
edge_thresh = 0.0001;

% Preallocate 
meanSTTC = zeros(length(lagval), 1);
maxSTTC = zeros(length(lagval), 1);

% Folder to save figures 
networkActivityFolder = Params.networkActivityFolder;

% Previous analysis data
if (Params.priorAnalysis == 1)
    priorAnalysisExpMatFolder = fullfile(Params.priorAnalysisPath, 'ExperimentMatFiles');
    matFiles = dir(fullfile(priorAnalysisExpMatFolder, '*.mat'));
    matFileNames = {matFiles.name};
    matFileBaseNames = {};
    for fileIdx = 1:length(matFileNames)
        matFileBaseNames{fileIdx} = erase(matFileNames{fileIdx}, ['_',  Params.priorAnalysisSubFolderName,'.mat']);
    end 
    prevNetMetFpathIdx = strcmp(matFileBaseNames,Info.FN);
    prevNetMetFpath = fullfile(priorAnalysisExpMatFolder, matFileNames{prevNetMetFpathIdx});
    
    if isfile(prevNetMetFpath)
        prevNetMetData = load(prevNetMetFpath);
    else
        prevNetMetData = struct();
    end
    
    if isfield(prevNetMetData, 'NetMet')
        prevNetMet = prevNetMetData.NetMet;
    else 
        prevNetMet = {};
    end
else
    prevNetMet = {};
end

for e = 1:length(lagval)
    
    
    %% load adjacency matrix
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
    
    activeNodeIndices = find(aNtemp > 0);
    
    clear aNtemp
    
    %adjM(iN,:) = [];
    % adjM(:,iN) = [];

    % Tim 2022-10-14 fix
    nodeStrength = sum(adjM, 1);
    inclusionIndex = find(nodeStrength ~= 0);
    adjM = adjM(inclusionIndex, inclusionIndex);
    coords = originalCoords(inclusionIndex, :);
    Params.netSubsetChannels = channels(inclusionIndex);
    activeChannel = channels(inclusionIndex);  % this will be saved in NetMet
    
    %% node degree, edge weight, node strength
    if Params.excludeEdgesBelowThreshold 
        exclude_zeros = 1;
    else 
        exclude_zeros = 0;
    end 
    
    [ND,MEW] = findNodeDegEdgeWeight(adjM, edge_thresh, exclude_zeros);
    if isempty(adjM)
        ND = double.empty([0, 1]);
        MEW = double.empty([0, 1]);
    end
    
    % Node strength
    NS = strengths_und(adjM)';
    if isempty(adjM)
        NS = double.empty([0, 1]);
    end
    
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
    if checkIfRecomputeMetric(Params, prevNetMet, lagValStr, 'Eglob') == 1
        if strcmp(Params.adjMtype,'weighted')
            Eglob = efficiency_wei(adjM);
        elseif strcmp(Params.adjMtype,'binary')
            Eglob = efficiency_bin(adjM);
        end
    else 
        Eglob = prevNetMet.(lagValStr).Eglob;
    end 
    
    % Lattice-like model
    if length(adjM)> Params.minNumberOfNodesToCalNetMet
        ITER = 10000;
        
        if checkIfRecomputeMetric(Params, prevNetMet, lagValStr, 'SW') == 1
            Z = pdist(adjM);
            D = squareform(Z);

            [LatticeNetwork,Rrp,ind_rp,eff,met] = latmio_und_v2(adjM,ITER,D,'SW');

            % Random rewiring model (d)
            ITER = 5000;
            [R, ~,met2] = randmio_und_v2(adjM, ITER,'SW');

            plotNullModelIterations(met, met2, lagval, e, char(Info.FN), ...
                Params, lagFolderName, oneFigureHandle)
    
            % Calculate small-worldness (+normalization).
        
            [SW, SWw, CC, PL] = small_worldness_RL_wu(adjM,R,LatticeNetwork);
        else
            SW = prevNetMet.(lagValStr).SW;
            SWw = prevNetMet.(lagValStr).SWw;
            CC = prevNetMet.(lagValStr).CC;
            PL = prevNetMet.(lagValStr).PL;
        end
        
        % local efficiency
        %   For ease of interpretation of the local efficiency it may be
        %   advantageous to rescale all weights to lie between 0 and 1.
        if checkIfRecomputeMetric(Params, prevNetMet, lagValStr, 'Eloc') == 1
            if strcmp(Params.adjMtype,'weighted')
                adjM_nrm = weight_conversion(adjM, 'normalize');
                Eloc = efficiency_wei(adjM_nrm,2);
            elseif strcmp(Params.adjMtype,'binary')
                adjM_nrm = weight_conversion(adjM, 'normalize');
                Eloc = efficiency_bin(adjM_nrm,2);
            end

            % mean local efficiency across nodes
            ElocMean = mean(Eloc);
        else 
            Eloc = prevNetMet.(lagValStr).Eloc;
            ElocMean = prevNetMet.(lagValStr).ElocMean;
        end
   
        % betweenness centrality
        if checkIfRecomputeMetric(Params, prevNetMet, lagValStr, 'BC') == 1
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
            BC = prevNetMet.(lagValStr).BC;
            BC95thpercentile = prctile(BC, 95);
            BCmeantop5 = mean(BC(BC >= BC95thpercentile));
            % BCmeantop5 = prevNetMet.(lagValStr).BCmeantop5;
        end
    else
         fprintf('Not enough nodes to calculate network metrics! \n')
         SW = nan;
         SWw = nan;
         CC = nan;
         PL = nan;
         Eloc = nan(length(NS), 1);
         ElocMean = nan;
         BC = nan(length(NS), 1);
         BCmeantop5 = nan;
     end
    
    % participation coefficient
    % PC = participation_coef(adjM,Ci,0);
    if any(strcmp(netMetToCal, 'PC')) || any(strcmp(netMetToCal, 'Hub3')) || any(strcmp(netMetToCal, 'Hub4'))
        if length(adjM) >= Params.minNumberOfNodesToCalNetMet
            
            if checkIfRecomputeMetric(Params, prevNetMet, lagValStr, 'PC') == 1
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
                PC = prevNetMet.(lagValStr).PC;
                Z = prevNetMet.(lagValStr).Z;
                PCmean = prevNetMet.(lagValStr).PCmean;
                
                 % percentage of within-module z-score greater and less than zero
                percentZscoreGreaterThanZero = sum(Z > 0) / length(Z) * 100;
                percentZscoreLessThanZero = sum(Z < 0) / length(Z) * 100;
                
                % PC90thpercentile = prevNetMet.(lagValStr).PC90thpercentile;
                % PC10thpercentile = prevNetMet.(lagValStr).PC10thpercentile;
                % PCmeanTop10 = prevNetMet.(lagValStr).PCmeanTop10;
                % PCmeanBottom10 = prevNetMet.(lagValStr).PCmeanBottom10;
                PC90thpercentile = prctile(PC, 90);
                PC10thpercentile = prctile(PC, 10);
                PCmeanTop10 = mean(PC(PC >= PC90thpercentile));
                PCmeanBottom10 = mean(PC(PC <= PC10thpercentile));
            end

        else 
            PC = nan(length(NS), 1);
            Z = nan(length(NS), 1);
            percentZscoreGreaterThanZero = nan;
            percentZscoreLessThanZero = nan;
            PCmean = nan;
            PCmeanTop10 = nan;
            PCmeanBottom10 = nan;
        end 
    end 
    

    
    %% nodal efficiency
    if checkIfRecomputeMetric(Params, prevNetMet, lagValStr, 'NE') == 1
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
    else 
        NE = prevNetMet.(lagValStr).NE;
    end
    
    %% Hub classification (only works when number of nodes exeed criteria)
    if any(strcmp(netMetToCal, 'Hub3')) || any(strcmp(netMetToCal, 'Hub4'))
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
    end

    %% Find hubs and plot raster sorted by hubs 
    % convert spike times to spike matrix 
    %{
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
    %}

    %% Calculate non-negative matrix factorisation components
    % note these are only calcualted for the first lag field because they
    % do not depend on lag
    if e == 1
        firstLagField = strcat('adjM',num2str(lagval(e)),'mslag');
        if any(strcmp(netMetToCal, 'num_nnmf_components'))
            if strcmp(Params.verboseLevel, 'High')
                fprintf('Calculating NMF \n')
            end 
            minSpikeCount = 1;
            includeRandomMatrix = 1;
            if checkIfRecomputeMetric(Params, prevNetMet, firstLagField, 'num_nnmf_components') == 1
                
                if Params.fs < Params.NMFdownsampleFreq
                    Params.NMFdownsampleFreq = Params.fs;
                end 
                
                nmfCalResults = calNMF(activityMatrix, Params.fs, Params.NMFdownsampleFreq, ...
                                        Info.duration_s, minSpikeCount, includeRandomMatrix, ...
                                        Params.includeNMFcomponents, Params.verboseLevel, ...
                                        Params.suite2pMode);
                NetMet.(firstLagField).num_nnmf_components = nmfCalResults.num_nnmf_components;
                NetMet.(firstLagField).nComponentsRelNS = nmfCalResults.nComponentsRelNS; 
                NetMet.(firstLagField).nnmf_residuals = nmfCalResults.nnmf_residuals; 
                NetMet.(firstLagField).nnmf_var_explained = nmfCalResults.nnmf_var_explained;
                NetMet.(firstLagField).randResidualPerComponent = nmfCalResults.randResidualPerComponent;
                if Params.includeNMFcomponents
                    NetMet.(firstLagField).nmfFactors = nmfCalResults.nmfFactors;
                    NetMet.(firstLagField).nmfWeights = nmfCalResults.nmfWeights;
                    NetMet.(firstLagField).downSampleSpikeMatrix = nmfCalResults.downSampleSpikeMatrix;
                    NetMet.(firstLagField).nmfFactorsVarThreshold = nmfCalResults.nmfFactorsVarThreshold;
                    NetMet.(firstLagField).nmfWeightsVarThreshold = nmfCalResults.nmfWeightsVarThreshold;
                end 
            else 
                NetMet.(firstLagField).num_nnmf_components = prevNetMet.(firstLagField).num_nnmf_components;
                NetMet.(firstLagField).nComponentsRelNS = prevNetMet.(firstLagField).nComponentsRelNS; 
                NetMet.(firstLagField).nnmf_residuals = prevNetMet.(firstLagField).nnmf_residuals; 
                NetMet.(firstLagField).nnmf_var_explained = prevNetMet.(firstLagField).nnmf_var_explained;
                NetMet.(firstLagField).randResidualPerComponent = prevNetMet.(firstLagField).randResidualPerComponent;
                
                if Params.includeNMFcomponents
                    NetMet.(firstLagField).nmfFactors = prevNetMet.(firstLagField).nmfFactors;
                    NetMet.(firstLagField).nmfWeights = prevNetMet.(firstLagField).nmfWeights;
                    NetMet.(firstLagField).downSampleSpikeMatrix = prevNetMet.(firstLagField).downSampleSpikeMatrix;
                    NetMet.(firstLagField).nmfFactorsVarThreshold = prevNetMet.(firstLagField).nmfFactorsVarThreshold;
                    NetMet.(firstLagField).nmfWeightsVarThreshold = prevNetMet.(firstLagField).nmfWeightsVarThreshold;
                end 
            end
            
        end 

        %% Calculate effective rank 
        if any(strcmp(netMetToCal,'effRank'))
            if strcmp(Params.verboseLevel, 'High')
                fprintf('Calculating effective rank \n')
            end
            if checkIfRecomputeMetric(Params, prevNetMet, lagValStr, 'effRank') == 1
                
                if Params.effRankDownsampleFreq > Params.fs 
                   Params.effRankDownsampleFreq = Params.fs; 
                end
                
                downSampleMatrix = downSampleSum(full(activityMatrix), Params.effRankDownsampleFreq * Info.duration_s);
                NetMet.(firstLagField).effRank = ...
                    calEffRank(downSampleMatrix, Params.effRankCalMethod);
            else 
                NetMet.(firstLagField).effRank = prevNetMet.(firstLagField).effRank;
            end
        end 
        
    end 
    %% Calculate average and modal controllability 
    if any(strcmp(netMetToCal, 'aveControl'))
        lagFieldStr = strcat('adjM',num2str(lagval(e)),'mslag');
        if checkIfRecomputeMetric(Params, prevNetMet, firstLagField, 'aveControl') == 1
            
            if isempty(adjM) 
                aveControl = double.empty([0, 1]);
            else
                aveControl = ave_control(adjM);
            end

            aveControlMean = mean(aveControl);
            aveControl75thpercentile = prctile(aveControl, 75);
            aveControlTop25 = mean(aveControl(aveControl >= aveControl75thpercentile));
                
        else 
            aveControl = prevNetMet.(lagFieldStr).aveControl;
            aveControlMean = prevNetMet.(lagFieldStr).aveControlMean;
            aveControlTop25 = prevNetMet.(lagFieldStr).aveControlTop25;
        end
        NetMet.(lagFieldStr).aveControl = aveControl;
        NetMet.(lagFieldStr).aveControlMean = aveControlMean;
        NetMet.(lagFieldStr).aveControlTop25 = aveControlTop25;
    end 

    if any(strcmp(netMetToCal, 'modalControl'))
        lagFieldStr = strcat('adjM',num2str(lagval(e)),'mslag');
        if checkIfRecomputeMetric(Params, prevNetMet, firstLagField, 'modalControl') == 1
        
            modalControl = modal_control(adjM);

            modalControlMean = mean(modalControl);
            modalControlThreshold = 0.975;
            modalControlPrctLessThanThreshold = sum(modalControl < modalControlThreshold) / length(modalControl);
        else 
            modalControl = prevNetMet.(lagFieldStr).modalControl;
            modalControlMean = prevNetMet.(lagFieldStr).modalControlMean;
            modalControlPrctLessThanThreshold = prevNetMet.(lagFieldStr).modalControlPrctLessThanThreshold;
            
        end 
        NetMet.(lagFieldStr).modalControl = modalControl;
        NetMet.(lagFieldStr).modalControlMean = modalControlMean;
        NetMet.(lagFieldStr).modalControlPrctLessThanThreshold = modalControlPrctLessThanThreshold;
      
    end 
    
    
    %% Spatial and Temporal autocorrelation 
    if any(strcmp(netMetToCal, 'SA_lambda')) || any(strcmp(netMetToCal, 'SA_inf'))
        dist = squareform(pdist(coords));
        cm = adjM;
        discretization = 15;  % arbitrary number to get good number of samples per bin
        [SA_lambda, SA_inf] = spatial_autocorrelation(dist, cm, discretization);
    end 
    
    if any(strcmp(netMetToCal, 'TA_regional')) || any(strcmp(netMetToCal, 'TA_global'))
        % TODO: calculate temporal autocorrelation
        time_bin_size = 0.1; % in units of seconds 
        spikeMatrixBinned = 1; % TODO: resample spike matrix
        lag_corr_per_channel = zeros(length(inclusionIndex), 1);
        for channel = 1:size(activityMatrix, 1)
            x = activityMatrix(inclusionIndex, :);
            lag_corr_per_channel = temporal_autocorrelation(x);
        end
    end 
    

    
    %% reassign to structures
    Var = horzcat(netMetToCal, unitMetToCal); 
    Var{end+1} = 'activeNodeIndices';
    Var{end+1} = 'Ci';  % community affiliation
    Var{end+1} = 'activeChannel';
    
    lagIndependentMetrics = {'effRank', 'num_nnmf_components', 'nComponentsRelNS', ...
                             'nnmf_residuals', 'nnmf_var_explained', 'randResidualPerComponent', ... 
                             'nmfFactors', 'nmfWeights', 'downSampleSpikeMatrix', 'nmfFactorsVarThreshold', ...
                             'nmfWeightsVarThreshold'};
    nodeCartographyMetrics = {'NCpn1', 'NCpn2','NCpn3','NCpn4','NCpn5','NCpn6'};
    
    for i = 1:length(Var)
        % TODO: remove eval 
        VN = cell2mat(Var(i));
        VNs = strcat('NetMet.adjM',num2str(lagval(e)),'mslag.',VN);
        if ~ismember(VN, lagIndependentMetrics) && ~ismember(VN, nodeCartographyMetrics)
            eval([VNs '=' VN ';']);
        end
    end
    
    % clear variables
    clear ND MEW NS Dens Ci Q nMod CC PL SW SWw Eloc BC PC Z Var NCpn1 NCpn2 NCpn3 NCpn4 NCpn5 NCpn6 Hub3 Hub4 NE PC_raw Cmcblty
    

end

end
