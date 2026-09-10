function [mergedStart, mergedEnd] = mergeCloseBursts(tStart, tEnd, gapSec)
%MERGECLOSEBURSTS Join bursts separated by less than gapSec into one.
%
% Parameters
% ----------
% tStart : vector
%     burst start times, in seconds
% tEnd : vector
%     burst end times, in seconds
% gapSec : double
%     bursts closer together than this are one burst. 0 or negative disables
%     merging and returns the input unchanged.
%
% OUTPUT
% ------
% mergedStart, mergedEnd : vectors of merged burst start/end times, seconds
%
% Why this exists
% ---------------
% ISI_N detection segments on the interval between individual spikes, which on
% a densely firing array breaks a single network event into many pieces: the
% array's own background firing keeps ISI_N hovering around the threshold, so
% it crosses back and forth several times inside one event. A 400 ms event on
% a 460 Hz 16-channel recording comes out of the detector as 21 bursts whose
% gaps are a few milliseconds each.
%
% Merging only re-segments -- it takes bursts the detector already found and
% joins adjacent ones, so it cannot add time or spikes that were not detected
% as bursting. What it fixes is burst count, rate and duration, which are
% otherwise counting fragments rather than events. See Pasquale et al. 2010,
% who merge on a minimum inter-burst interval for the same reason.
%
% Tim Sit 2026

if gapSec <= 0 || numel(tStart) < 2
    mergedStart = tStart;
    mergedEnd = tEnd;
    return
end

% Bursts come out of BurstDetectISIn in time order, but merging is only
% correct on sorted input, so do not rely on it.
[tStart, order] = sort(tStart(:));
tEnd = tEnd(:);
tEnd = tEnd(order);

mergedStart = zeros(size(tStart));
mergedEnd = zeros(size(tEnd));
mergedStart(1) = tStart(1);
mergedEnd(1) = tEnd(1);
n = 1;

for i = 2:numel(tStart)
    if tStart(i) - mergedEnd(n) <= gapSec
        % max, not tEnd(i): a short burst fully inside a longer one must not
        % shorten it.
        mergedEnd(n) = max(mergedEnd(n), tEnd(i));
    else
        n = n + 1;
        mergedStart(n) = tStart(i);
        mergedEnd(n) = tEnd(i);
    end
end

mergedStart = reshape(mergedStart(1:n), 1, []);
mergedEnd = reshape(mergedEnd(1:n), 1, []);

end
