% Ground-truth network metrics computed by MATLAB's OWN BCT functions on the
% adjacency matrices from THIS parity run (parityRun/OutputData_MATLAB_parity),
% so the Python port can be fed the identical graph.
%
% This isolates the step-4 metric arithmetic from step 3's probabilistic
% thresholding, which uses an independently-seeded RNG in each port and so
% produces slightly different graphs (different aN) even from identical spikes.
%
% Adapted from python/test_fixtures/gen_step4_reference.m (which points at the
% no-longer-present OutputData03Mar2026 run). Adds aveControl/modalControl.
%
% Run: matlab -batch "run('parityRun/gen_step4_parity_reference.m')"

repo_root = '/home/timsit/MEA-NAP';
addpath(genpath(fullfile(repo_root, 'Functions')));

recs = {'NGN2_20230208_P1_DIV14_A2', 'NGN2_20230208_P1_DIV14_A3'};
lags = [10, 25, 50];
minActivityLevel = 0.01;
edge_thresh = 0.0001;
exclude_zeros = 1;          % Params.excludeEdgesBelowThreshold = 1
outdir = fullfile(repo_root, 'parityRun');
runName = 'OutputData_MATLAB_parity';

for r = 1:numel(recs)
    rec = recs{r};
    matFpath = fullfile(repo_root, 'parityRun', runName, 'ExperimentMatFiles', ...
        [rec '_' runName '.mat']);
    d = load(matFpath);
    duration_s = d.Info.duration_s;

    results = struct();
    for li = 1:numel(lags)
        lag = lags(li);
        lagValStr = sprintf('adjM%dmslag', lag);
        adjM = d.adjMs.(lagValStr);
        adjM(adjM < 0) = 0;
        adjM(isnan(adjM)) = 0;

        % active node inclusion, matching ExtractNetMet.m.
        % ExtractNetMet uses sum(spikeMatrix,1)/duration_s; the saved .mat has no
        % spikeMatrix, but Ephys.FR is that exact quantity (verified: max abs
        % difference vs spike-count/duration is 0 on this run).
        nodeStrength = sum(adjM, 1);
        activityLevelPerNode = d.Ephys.FR(:)';
        inclusionIndex = find((nodeStrength ~= 0) & (activityLevelPerNode >= minActivityLevel));
        aN = length(inclusionIndex);

        adjMsub = adjM(inclusionIndex, inclusionIndex);

        [ND, MEW] = findNodeDegEdgeWeight(adjMsub, edge_thresh, exclude_zeros);
        NS = strengths_und(adjMsub)';
        [Dens, ~, ~] = density_und(adjMsub);

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
        NE = (1 ./ mDist)';

        % Controllability (Bassett lab), as called by ExtractNetMet.m
        aveControl = ave_control(adjMsub);
        modalControl = modal_control(adjMsub);

        fn = sprintf('lag%d', lag);
        results.(fn).aN = aN;
        results.(fn).inclusionIndex = inclusionIndex;
        results.(fn).adjMsub = adjMsub;
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
        results.(fn).aveControl = aveControl;
        results.(fn).modalControl = modalControl;

        fprintf('%s lag=%d aN=%d Dens=%.4f Eglob=%.4f CCrawMean=%.4f PLraw=%.4f aveCtrlMean=%.6f\n', ...
            rec, lag, aN, Dens, Eglob, CCrawMean, PLraw, mean(aveControl));
    end
    save(fullfile(outdir, [rec '_step4_parity_ref.mat']), 'results', '-v7');
end
disp('DONE');
