% MATLAB reference for python/test_spike_detection_wavelets.py.
% Run from this folder: matlab -batch make_wavelet_reference
% Writes wavelet_reference_raw.mat; the test reads the .npz the Python
% snippet at the bottom of this file makes from it (CWT kept for samples
% 2001-3000 only, to keep the fixture small). Generated with R2025b.
% determine_scales is a local function of detectSpikesWavelet.m; copy it
% out first, e.g.
%   awk '/function Scale = determine_scales/,/^end/' ../../matlab/Functions/WATERS-master/detectSpikesWavelet.m > determine_scales.m
addpath(fullfile('..', '..', 'matlab', 'Functions', 'WATERS-master'));
rng(1);
fs = 25000;
n = 25000*2; trace = randn(1,n)*5;                 % a synthetic filtered trace
t = (-25:25);
spk = -60*exp(-(t/3).^2) + 25*exp(-((t-8)/6).^2);  % with a spike every 1373 samples
for k = 200:1373:n-200, trace(k-25:k+25) = trace(k-25:k+25) + spk; end
out = struct('trace', trace, 'fs', fs, 'scales', [3 5 8 12 20]);
names = {'bior1.5','bior1.3','db2','sym2','haar'};
for i = 1:numel(names)
    w = names{i}; key = strrep(w,'.','p');
    [psi, ~] = intwave(w, 10);
    out.([key '_psi']) = psi;
    out.([key '_cwt']) = cwt(trace(1:5000), out.scales, w);
    out.([key '_spikes_250']) = detectSpikesWavelet(trace, 25, [0.4 0.8], 5, 'l', -0.12, w, 0, 0);
    % the same trace read as a 12.5 kHz recording
    out.([key '_spikes_125']) = detectSpikesWavelet(trace, 12.5, [0.4 0.8], 5, 'l', -0.12, w, 0, 0);
    for f = [12.5 20 25]
        out.(sprintf('%s_scales_%d', key, round(f*10))) = determine_scales(w, [0.4 0.8], f, 5);
    end
end
[ave, ~] = getTemplate(trace(:), 4.5, 2, fs, 100);    % mea: the template and its wavelet
out.gt_ave = ave;
adaptWavelet(ave);
[psi, ~] = intwave('mea', 10);
out.mea_psi = psi;
out.mea_cwt = cwt(trace(1:5000), out.scales, 'mea');
save('wavelet_reference_raw.mat', '-struct', 'out', '-v7');
% Then, in Python:
%   d = scipy.io.loadmat('wavelet_reference_raw.mat', squeeze_me=True)
%   d = {k: v for k, v in d.items() if not k.startswith('__')}
%   for k in [k for k in d if k.endswith('_cwt')]: d[k] = d[k][:, 2000:3000]
%   d['cwt_window'] = numpy.array([2000, 3000])
%   numpy.savez_compressed('wavelets_matlab_reference.npz', **d)
