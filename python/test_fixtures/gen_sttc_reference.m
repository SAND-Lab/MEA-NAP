% Regenerates the STTC ground-truth fixtures used by test_pipeline_step3.py.
%
% Calls MATLAB's own get_sttc.m (the deterministic, unthresholded STTC
% computation) directly on the reference spike times in OutputData03Mar2026,
% and saves the resulting adjacency matrices as .mat files. These are then
% converted to .npz (see the inline snippet at the bottom of this comment)
% for use as fixtures in python/test_fixtures/, since MATLAB's own pipeline
% never persists the raw (unthresholded) STTC matrix — only the
% stochastically-thresholded adjMci, which isn't bit-reproducible.
%
% Run from the repo root:
%   matlab -batch "run('python/test_fixtures/gen_sttc_reference.m')"
%
% Then convert to .npz:
%   uv run python3 -c "
%   import numpy as np
%   from scipy.io import loadmat
%   for rec in ['NGN2_20230208_P1_DIV14_A2', 'NGN2_20230208_P1_DIV14_A3']:
%       ref = loadmat(f'python/test_fixtures/{rec}_sttc_ref.mat')
%       r = ref['results'][0, 0]
%       np.savez(f'python/test_fixtures/{rec}_sttc_reference.npz',
%                **{name: r[name] for name in r.dtype.names})
%   "

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(genpath(fullfile(repo_root, 'Functions', 'STTCandThresholding')));

recs = {'NGN2_20230208_P1_DIV14_A2', 'NGN2_20230208_P1_DIV14_A3'};
lags = [10, 25, 50];
method = 'bior1p5';
duration_s = 600;

use_c_code = test_sttc_c_code();
fprintf('use_c_code = %d\n', use_c_code);

outdir = fullfile(repo_root, 'python', 'test_fixtures');

for r = 1:numel(recs)
    rec = recs{r};
    s = load(fullfile(repo_root, 'OutputData03Mar2026', '1_SpikeDetection', ...
        '1A_SpikeDetectedData', [rec '_spikes.mat']));
    spikeTimes = s.spikeTimes;
    results = struct();
    for li = 1:numel(lags)
        lag = lags(li);
        tic;
        adjM = get_sttc(spikeTimes, lag, duration_s, method, use_c_code);
        elapsed = toc;
        fprintf('%s lag=%d done in %.2fs\n', rec, lag, elapsed);
        fieldname = sprintf('adjM_%dms', lag);
        results.(fieldname) = adjM;
    end
    save(fullfile(outdir, [rec '_sttc_ref.mat']), 'results', '-v7');
end
disp('DONE');
