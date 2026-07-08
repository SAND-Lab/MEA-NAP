% Regenerates the coordinate-lookup ground-truth fixture used to validate
% channel_layout.py's get_coords_from_layout() against MATLAB's
% getCoordsFromLayout.m directly. Prints channel/coord counts; save the
% .mat and diff channels/coords array-for-array in Python (see
% src/meanap/pipeline/channel_layout.py's docstring for the exact
% comparison this supports).
%
% Run from the repo root:
%   matlab -batch "run('python/test_fixtures/gen_coords_reference.m')"

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo_root, 'Functions'));

layouts = {'MCS60old', 'MCS60', 'MCS59', 'Axion64', 'Axion16'};
outdir = fullfile(repo_root, 'python', 'test_fixtures');

for i = 1:numel(layouts)
    [channels, coords] = getCoordsFromLayout(layouts{i});
    results.(layouts{i}).channels = channels;
    results.(layouts{i}).coords = coords;
    fprintf('%s: %d channels\n', layouts{i}, length(channels));
end
save(fullfile(outdir, 'coords_ref.mat'), 'results', '-v7');
disp('DONE');
