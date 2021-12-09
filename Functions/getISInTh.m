function ISInTh = getISInTh(SpikeTimes, N, Steps, plotFig)
%GETISINTH Returns the threshold to use for BurstDetectISIn.m 
%   Tim Sit 2018 
%   Based on HistogramISIn.m by Douglas Bakkum, 2013, but automatically
%   returns the result rather than having to eyeball it, and uses a freely
%   available (and perhaps marginally better) smoothing function 

% This is from Bakkum 2013:
% GHistogramISIn(SpikeTimes, N, Steps) 
%   'SpikeTimes' [sec] % Vector of spike times 
%   'N'                % Vector of values for plotting ISI_N histograms 
                       % can also be a single real integer value.
%   'Steps' [sec]      % Vector of histogram edges 
%   'Plot'             % 1: make a plot, 0: don't plot (default)
% Steps should be of uniform width on a log scale. Note that histograms are
% smoothed using smooth.m with the default span and lowess method 
%
%
% Example code: 
%   Spike Times = -----; % load spike times here 
%   N           = [2:10]; % Range of N for ISI_N histograms 
%   Steps       = 10.^[-5:0.05:1.5] % Create uniform steps for log plot 
                % Sit 2018: I have made this optional, if no input, it will
                % automatically determine the steps, using
                % min(log(spikeTimes)):0.1:max(log(spikeTimes))
%   getISInTh(SpikeTimes, N, Steps) % Run function 


if ~exist('plotFig', 'var') 
    plotFig = 0; 
end 

if plotFig == 1
    figure; hold on 
end 


map = hsv(length(N)); 

cnt = 0; 

for FRnum = N 
    cnt = cnt + 1; 
    ISI_N = SpikeTimes(FRnum:end) - SpikeTimes(1:end-(FRnum-1)); 
    
    if ~exist('Steps', 'var') % Sit 2018
        Steps = min(log10(ISI_N)):0.1:max(log10(ISI_N));
        % This doesn't work as well as I expected, perhaps should stick to
        % their default values
        % I think it is because of the conversion to ms or something 
    end 
    
    n = histc(ISI_N * 1000, Steps * 1000); % Sit 2018: not really sure
    % what this 1000 is doing... I will just use my own hsitc method. Seems
    % to be some conversion of ms to s, but the input should be sec...
    
    % n = histcounts(log10(ISI_N), Steps);
    
    
    % n = smooth(n, 'lowess'); Bakkum 2014
    n = fLOESS(n, 8/round(length(n))); % used by Sit 2018
    % the fraction of data used is not specified in the paper 
    % so I will just make a guess (using the minimum value allowed).
    
    if plotFig == 1 
        plot(Steps * 1000, n/sum(n), '.-', 'color', map(cnt, :))
    end 
    % plot(Steps, n/sum(n), '.-', 'color', map(cnt, :))
    
    
end 

% SIT 2018 now we find peak in the curve to set threshold 
% don't know what to call that curve, so for now I will call it landscape
curve = n/sum(n);
% landscape = [Steps' * 1000, n/sum(n)]; 
% keeping the steps matched because we need it to determine threshold after
% we found the peaks and valleys of the curve
[pks,locs] = findpeaks(curve, 'minpeakdistance', 2); 

if length(pks) <= 1 
    % no peak or one peak, return default ISIn threshold value 
    ISInTh = 0.1; % in seconds, ie. 100ms (See Pasquale et al 2010) 
                  % actually also default value used in Bakkum et al 2014 
elseif length(pks) >= 2               
    % note that this entertains two conditions, peak == 2, in which case we get the
    % minimum value between those two peaks, and where peak > 2, in which
    % case we get the mimum value between the first two peaks (from
    % smallest to largest), in terms of x-axis values 
    peakOne = locs(1); 
    peakTwo = locs(2); 
    
    valleyPoint = find(curve == min(curve(peakOne:peakTwo))); 
    % this will find the first minimum, if there are multiples 
    
    ISInTh = valleyPoint / 1000; % convert ms back to seconds
    
end 


% check that ISInTh is smaller than 0.1, since in Pasquale 2010 they
% used that as the upper limit 
    
if ISInTh > 0.1 
    ISInTh = 0.1; 
end 


if plotFig == 1
    xlabel('ISI, T_i - T_{i-(N-1)}_{}[ms]') 
    ylabel('Probability [%]') 
    set(gca, 'xscale', 'log') 
    set(gca, 'yscale', 'log')
end 


% Things to do to make this code to work 

% find peak,
% if no peak: return default ISIn threshold value 
% if two peaks: return valley value (ie. the minimum value between the two
% peaks) 
% if >2 peaks: use the first minima between the first pair of peaks.


% Improvements that can be made: 

% legend for when N is a vector


end

