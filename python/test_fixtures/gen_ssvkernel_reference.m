function gen_ssvkernel_reference()
% Ground truth for the ssvkernel port. Reads fixed PSTH-sample inputs
% (ssvkernel_inputs.mat: tin + x_big/x_mid/x_small, pooled from real analyzed
% channels) and runs MEA-NAP's ssvkernel.m on each, saving y/optw.
% Regenerate with: matlab -batch gen_ssvkernel_reference
addpath(genpath('/home/timsit/MEA-NAP/Functions'));
here = fileparts(mfilename('fullpath'));
S = load(fullfile(here, 'ssvkernel_inputs.mat'));
tin = S.tin(:)';
out = struct();
for label = {'big', 'mid', 'small'}
    lab = label{1};
    x = S.(['x_' lab])(:)';
    [y, ~, optw] = ssvkernel(x, tin);
    out.(['y_' lab]) = y;
    out.(['optw_' lab]) = optw;
end
save(fullfile(here, 'ssvkernel_reference.mat'), '-struct', 'out', '-v7');
fprintf('DONE\n');
end
