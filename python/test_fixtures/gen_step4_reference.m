% Regenerates the network-metrics ground-truth fixtures used by
% test_pipeline_step4.py. Calls MATLAB's own BCT functions
% (findNodeDegEdgeWeight, strengths_und, density_und, clustering_coef_wu,
% distance_wei/charpath, efficiency_wei, betweenness_wei) directly on the
% real thresholded adjacency matrices saved in a MATLAB pipeline run
% (OutputData03Mar2026/ExperimentMatFiles/*.mat), replicating the
% active-node-subsetting logic from ExtractNetMet.m. Saves both the
% resulting metrics AND the inclusionIndex (so the Python-side test can
% reconstruct the exact same node subset) as .mat, then convert to .npz
% (see the snippet at the bottom of gen_sttc_reference.m for the pattern).
%
% Run from the repo root:
%   matlab -batch "run('python/test_fixtures/gen_step4_reference.m')"

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(genpath(fullfile(repo_root, 'Functions')));

recs = {'NGN2_20230208_P1_DIV14_A2', 'NGN2_20230208_P1_DIV14_A3'};
lags = [10, 25, 50];
minActivityLevel = 0.01;
edge_thresh = 0.0001;
exclude_zeros = 1;  % Params.excludeEdgesBelowThreshold = 1

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

        % active node inclusion, matching ExtractNetMet.m
        nodeStrength = sum(adjM, 1);
        activityLevelPerNode = full(sum(d.spikeMatrix, 1)) / duration_s;
        inclusionIndex = find((nodeStrength ~= 0) & (activityLevelPerNode >= minActivityLevel));
        aN = length(inclusionIndex);

        adjMsub = adjM(inclusionIndex, inclusionIndex);

        [ND, MEW] = findNodeDegEdgeWeight(adjMsub, edge_thresh, exclude_zeros);
        NS = strengths_und(adjMsub)';
        [Dens, ~, ~] = density_und(adjMsub);

        % raw (non-null-model-normalized) clustering coefficient and path length
        CCraw = clustering_coef_wu(adjMsub);
        CCrawMean = mean(CCraw);

        WCon = weight_conversion(adjMsub, 'lengths');
        DistM = distance_wei(WCon);
        [PLraw, ~, ~, ~, ~] = charpath(DistM, 0, 0);

        Eglob = efficiency_wei(adjMsub);

        adjM_nrm = weight_conversion(adjMsub, 'normalize');
        Eloc = efficiency_wei(adjM_nrm, 2);
        ElocMean = mean(Eloc);

        smallFactor = 0.01;
        pathLengthNetwork = 1 ./ (adjMsub + smallFactor);
        BC = betweenness_wei(pathLengthNetwork);
        BC = BC / ((length(adjMsub)-1)*(length(adjMsub)-2));

        mDist = mean(DistM, 1);
        NE = 1 ./ mDist;
        NE = NE';

        fn = sprintf('lag%d', lag);
        results.(fn).aN = aN;
        results.(fn).inclusionIndex = inclusionIndex;
        results.(fn).ND = ND;
        results.(fn).MEW = MEW;
        results.(fn).NS = NS;
        results.(fn).Dens = Dens;
        results.(fn).CCrawMean = CCrawMean;
        results.(fn).CCraw = CCraw;
        results.(fn).PLraw = PLraw;
        results.(fn).Eglob = Eglob;
        results.(fn).Eloc = Eloc;
        results.(fn).ElocMean = ElocMean;
        results.(fn).BC = BC;
        results.(fn).NE = NE;

        fprintf('%s lag=%d aN=%d Dens=%.4f Eglob=%.4f CCrawMean=%.4f PLraw=%.4f ElocMean=%.4f\n', ...
            rec, lag, aN, Dens, Eglob, CCrawMean, PLraw, ElocMean);
    end
    save(fullfile(outdir, [rec '_step4_ref.mat']), 'results', '-v7');
end
disp('DONE');
