% Regenerates the small-worldness ground-truth fixture used by
% test_pipeline_small_worldness.py. Unlike the other gen_*_reference.m
% scripts, this does NOT depend on a real MATLAB pipeline run's saved
% adjacency matrices (OutputData03Mar2026/ExperimentMatFiles isn't always
% present in every environment) — it builds a small, fixed-seed random
% weighted network directly, then calls MATLAB's own latmio_und_v2 /
% randmio_und_v2 / small_worldness_RL_wu on it exactly as ExtractNetMet.m
% does (same ITER counts, same 'SW' metric flag). This isolates "does the
% deterministic small_worldness_RL_wu formula assembly match" (the actual
% port target) from "do the two languages' independent RNG streams agree"
% (impossible by design — latmio_und_v2/randmio_und_v2 are themselves
% stochastic, see null_models.py's module docstring) — same pattern as
% gen_cartography_reference.m feeding a fixed Ci rather than re-deriving
% Louvain's own randomness.
%
% Run from the repo root:
%   matlab -batch "run('python/test_fixtures/gen_small_worldness_reference.m')"
%
% Then convert to .npz:
%   uv run python -c "
%   import numpy as np
%   from scipy.io import loadmat
%   ref = loadmat('python/test_fixtures/small_worldness_ref.mat')
%   np.savez('python/test_fixtures/small_worldness_reference.npz',
%            A=ref['A'], R=ref['R'], L=ref['L'],
%            SW=ref['SW'], SWw=ref['SWw'], CC=ref['CC'], PL=ref['PL'])
%   "

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(genpath(fullfile(repo_root, 'Functions')));

outdir = fullfile(repo_root, 'python', 'test_fixtures');

rng(42);
n = 24;
A = rand(n, n);
A = (A + A') / 2;
A(A < 0.55) = 0;      % sparsify to a realistic-ish density
A = A - diag(diag(A));

% distance-between-connectivity-profiles matrix, exactly as
% ExtractNetMet.m computes it for latmio_und_v2's 3rd argument
Z = pdist(A);
D = squareform(Z);

L = latmio_und_v2(A, 10000, D, 'SW', 1000);
R = randmio_und_v2(A, 5000, 'SW', 1000);

[SW, SWw, CC, PL] = small_worldness_RL_wu(A, R, L);

fprintf('SW=%.6f SWw=%.6f CC=%.6f PL=%.6f\n', SW, SWw, CC, PL);

save(fullfile(outdir, 'small_worldness_ref.mat'), 'A', 'R', 'L', 'SW', 'SWw', 'CC', 'PL', '-v7');
disp('DONE');
