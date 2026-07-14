% Regenerates the node-cartography ground-truth fixture used by
% test_pipeline_cartography.py. Loads a real thresholded adjacency matrix,
% subsets to active nodes (same logic as gen_step4_reference.m), runs
% MATLAB's own modularity clustering ONCE to get a real Ci, then calls
% MATLAB's own participation_coef_norm / module_degree_zscore / rich_club_wu
% / node-cartography classification on that FIXED Ci — isolating the
% deterministic downstream metrics from Louvain's own run-to-run
% stochasticity (matches the general pattern used throughout this port: feed
% a known-good input, diff the deterministic computation on top of it).
%
% Run from the repo root:
%   matlab -batch "run('python/test_fixtures/gen_cartography_reference.m')"

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(genpath(fullfile(repo_root, 'Functions')));

recs = {'NGN2_20230208_P1_DIV14_A2', 'NGN2_20230208_P1_DIV14_A3'};
lags = [10, 25, 50];
minActivityLevel = 0.01;

% Node cartography boundaries (MATLAB defaults, see NodeCartography.m docstring)
hubBoundaryWMdDeg = 2.5;
periPartCoef = 0.625;
proHubpartCoef = 0.3;
nonHubconnectorPartCoef = 0.8;
connectorHubPartCoef = 0.75;

outdir = fullfile(repo_root, 'python', 'test_fixtures');

for r = 1:numel(recs)
    rec = recs{r};
    matFpath = fullfile(repo_root, 'OutputData03Mar2026', 'ExperimentMatFiles', ...
        [rec '_OutputData03Mar2026.mat']);
    d = load(matFpath);
    duration_s = d.Info.duration_s;

    results = struct();
    for li = 1:numel(lags)
        lag = lags(li);
        lagValStr = sprintf('adjM%dmslag', lag);
        adjM = d.adjMs.(lagValStr);
        adjM(adjM < 0) = 0;
        adjM(isnan(adjM)) = 0;

        nodeStrength = sum(adjM, 1);
        activityLevelPerNode = full(sum(d.spikeMatrix, 1)) / duration_s;
        inclusionIndex = find((nodeStrength ~= 0) & (activityLevelPerNode >= minActivityLevel));

        adjMsub = adjM(inclusionIndex, inclusionIndex);

        [Ci, Q, ~] = mod_consensus_cluster_iterate(adjMsub, 0.4, 50);

        % NOTE: participation_coef_norm's outputs are (PC_norm, PC_residual,
        % PC_raw, between_mod_k) in that order. ExtractNetMet.m's real call
        % is `[PC,~,~,~] = participation_coef_norm(...)` — i.e. what MATLAB
        % actually uses for cartography/hub classification downstream is
        % the FIRST output (PC_norm), despite the local variable there
        % being named "PC". Earlier versions of this script (and its
        % corresponding Python test) mistakenly used the 3rd (raw) output
        % for classification instead — fixed here to match real MATLAB
        % semantics. Both are still saved: PCraw for the already-existing
        % deterministic-given-Ci parity check, PCnorm for the
        % classification/hub check that mirrors the real pipeline.
        [PCnorm, PC_residual, PCraw, between_mod_k] = participation_coef_norm(adjMsub, Ci, 100, 0);
        Z = module_degree_zscore(adjMsub, Ci, 0);
        Rw = rich_club_wu(adjMsub);

        % Deterministic-given-(Ci) inputs used by Hub3/Hub4: ND, BC, NE
        aNforHub = length(inclusionIndex);
        [ND, ~] = findNodeDegEdgeWeight(adjMsub, 0.0001, 1);
        smallFactor = 0.01;
        pathLengthNetwork = 1 ./ (adjMsub + smallFactor);
        BC = betweenness_wei(pathLengthNetwork);
        BC = BC / ((length(adjMsub)-1)*(length(adjMsub)-2));
        WCon = weight_conversion(adjMsub, 'lengths');
        DistM = distance_wei(WCon);
        mDist = mean(DistM, 1);
        NE = 1 ./ mDist;
        NE = NE';

        sortND = sort(ND,'descend'); sortND = sortND(1:round(aNforHub/10));
        hubNDfind = ismember(ND, sortND); [hubND, ~] = find(hubNDfind==1);
        sortPC = sort(PCnorm,'descend'); sortPC = sortPC(1:round(aNforHub/10));
        hubPCfind = ismember(PCnorm, sortPC); [hubPC, ~] = find(hubPCfind==1);
        sortBC = sort(BC,'descend'); sortBC = sortBC(1:round(aNforHub/10));
        hubBCfind = ismember(BC, sortBC); [hubBC, ~] = find(hubBCfind==1);
        sortNE = sort(NE,'descend'); sortNE = sortNE(1:round(aNforHub/10));
        hubNEfind = ismember(NE, sortNE); [hubNE, ~] = find(hubNEfind==1);
        hubs = [hubND; hubPC; hubBC; hubNE];
        [GC,~] = groupcounts(hubs);
        Hub4 = length(find(GC==4))/aNforHub;
        Hub3 = length(find(GC>=3))/aNforHub;

        aN = length(inclusionIndex);
        NdCartDiv = zeros(aN, 1);
        PopNumNC = zeros(1, 6);
        for j = 1:aN
            if (Z(j) <= hubBoundaryWMdDeg) && (PCnorm(j) <= periPartCoef)
                NdCartDiv(j) = 1;
            elseif (Z(j) <= hubBoundaryWMdDeg) && (PCnorm(j) >= periPartCoef) && (PCnorm(j) <= nonHubconnectorPartCoef)
                NdCartDiv(j) = 2;
            elseif (Z(j) <= hubBoundaryWMdDeg) && (PCnorm(j) >= nonHubconnectorPartCoef)
                NdCartDiv(j) = 3;
            elseif (Z(j) >= hubBoundaryWMdDeg) && (PCnorm(j) <= proHubpartCoef)
                NdCartDiv(j) = 4;
            elseif (Z(j) >= hubBoundaryWMdDeg) && (PCnorm(j) >= proHubpartCoef) && (PCnorm(j) <= connectorHubPartCoef)
                NdCartDiv(j) = 5;
            elseif (Z(j) >= hubBoundaryWMdDeg) && (PCnorm(j) >= connectorHubPartCoef)
                NdCartDiv(j) = 6;
            end
        end
        for role = 1:6
            PopNumNC(role) = sum(NdCartDiv == role);
        end

        fn = sprintf('lag%d', lag);
        results.(fn).inclusionIndex = inclusionIndex;
        results.(fn).Ci = Ci;
        results.(fn).Q = Q;
        results.(fn).PC = PCraw;
        results.(fn).PCnorm = PCnorm;
        results.(fn).Z = Z;
        results.(fn).Rw = Rw;
        results.(fn).NdCartDiv = NdCartDiv;
        results.(fn).PopNumNC = PopNumNC;
        results.(fn).Hub3 = Hub3;
        results.(fn).Hub4 = Hub4;

        fprintf('%s lag=%d aN=%d nMod=%d Q=%.4f PopNumNC=[%s] Hub3=%.4f Hub4=%.4f\n', ...
            rec, lag, aN, max(Ci), Q, num2str(PopNumNC), Hub3, Hub4);
    end
    save(fullfile(outdir, [rec '_cartography_ref.mat']), 'results', '-v7');
end
disp('DONE');
