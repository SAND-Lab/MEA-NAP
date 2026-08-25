%% AVGSHAPES - averages avalanche shapes
% The shape, also known as the temporal profile, of a neuronal avalanche is
% the number of neurons active at each time bin. This function computes the
% mean temporal profile of neuronal avalanches. By default the function
% considers avalanches for all durations, but the user may specify an 
% alternative sampling method as a variable input.
%
% Syntax:   avgProfiles = avgshapes(shapes, durations, varargin)
%
% Inputs:
%   shapes (cell array) - array containing vectors representing avalanche
%     shapes
%   durations (double) - vector containing duration of each avalanche
%
% Variable Inputs (shape sampling methods):
%   (..., 'limits', lowerLim, upperLim) - uses avalanche shapes whose
%     durations are inclusively bound by specified limits (scalar doubles)
%   (..., 'order', magnitude) - uses avalanche shapes whose durations
%     occur with frequency on the same order of magnitude if magnitude is
%     scalar or within the bounds of decades 10^(min(magnitude)) and
%     10^(max(magnitude)) if magnitude is a vector.
%   (..., 'linspace', lowerLim, upperLim, n) - uses avalanche shapes of
%     n different durations, linearly spaced between specified limits
%     (scalar double)
%   (..., 'logspace', x, lowerLim, upperLim) - uses avalanche shapes whose
%     durations are logarithmically spaced between x^(lowerLim) and
%     x^(upperLim) (scalar doubles)
%   (..., 'durations', durs) - uses avalanche shapes of specific durations,
%     durs (vector double)
%   (..., 'cutoffs', minDur, threshold) - uses avalanche shapes bounded
%     below by both an absolute minimum duration (>= minDur) and a 
%     threshold for the frequency of occurrence (>= threshold) (scalar 
%     doubles)
%
% Output:
%   avgProfiles (cell array) - array of mean temporal profiles (vector double)
% 
% Examples:
%   raster = randi([0 1], [10 1000]);
%   asdf = sparse2asdf(raster, 1);
%   asdf2 = asdftoasdf2(asdf, 'test', 'spikes', 'date');
%   Av = avprops(asdf2, 'duration', 'shape');
%   avgProfiles1 = avgshapes(Av.shape, Av.duration, 'order', 2);
%     % computes aerage shapes for avalanches whose durations occur 
%       between 100 and 1000 times
%   avgProfiles2 = avgshapes(Av.shape, Av.duration, 'order', [1 3]);
%     % computes average shapes for avalanches whose durations occur 
%       between 10 and 1000 times.
%   avgProfiles3 = avgshapes(Av.shape, Av.duration, 'durations', [5 8 14]);
%     % computes average shapes for duration 5, 8, and 14 avalanches
%   avgProfiles4 = avgshapes(Av.shape, Av.duration, 'cutoffs', 5, 50);
%     % computes average shapes for durations greater than 5 and for 
%       avalanches whose durations occur at least 50 times.
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: AVPROPS

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% June 2013; Last revision: 10-Aug-2014

%==============================================================================
% Copyright (c) 2013, The Trustees of Indiana University
% All rights reserved.
% 
% Redistribution and use in source and binary forms, with or without
% modification, are permitted provided that the following conditions are met:
% 
%   1. Redistributions of source code must retain the above copyright notice,
%      this list of conditions and the following disclaimer.
% 
%   2. Redistributions in binary form must reproduce the above copyright notice,
%      this list of conditions and the following disclaimer in the documentation
%      and/or other materials provided with the distribution.
% 
%   3. Neither the name of Indiana University nor the names of its contributors
%      may be used to endorse or promote products derived from this software
%      without specific prior written permission.
% 
% THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
% AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
% IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
% ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
% LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
% CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
% SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
% INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
% CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
% ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
% POSSIBILITY OF SUCH DAMAGE.

function avgProfiles = avgshapes(shapes, durations, varargin)
%% Determine sampling method
if ~isempty(varargin)
    switch varargin{1}
        case 'limits'
            lowerLim = varargin{2};
            upperLim = varargin{3};
            
            targetIndices = (durations >= lowerLim & durations <= upperLim);
            
        case 'order'
            magnitude = varargin{2};
            
            unqDurations = unique(durations);
            nUnqDurations = zeros(1, numel(unqDurations));
            
            % Count number of unique durations
            for iUnqDur = 1:length(unqDurations)
                theseDurations = (durations == unqDurations(iUnqDur));
                nUnqDurations(iUnqDur) = nnz(theseDurations);
            end
            
            if isscalar(magnitude)
                lowerLim = 10^magnitude;
                upperLim = 10^(magnitude + 1);
            else
                lowerLim = 10^(min(magnitude));
                upperLim = 10^(max(magnitude));
            end
            
            targetDurations = ...
                (nUnqDurations >= lowerLim & nUnqDurations < upperLim);
            targetIndices = ...
                ismember(durations, unqDurations(targetDurations));
            
        case 'linspace'
            lowerLim = varargin{2};
            upperLim = varargin{3}; 
            n = varargin{4};
            
            targetDurations = round(linspace(lowerLim, upperLim, n));
            targetIndices = ismember(durations, targetDurations);
            
        case 'logspace'
            x = varargin{2};
            lowerLim = varargin{3}; 
            upperLim = varargin{4};
            
            targetDurations = x.^(lowerLim:upperLim);
            targetIndices = ismember(durations, targetDurations);
            
        case 'durations'
            targetDurations = varargin{2};
            targetIndices = ismember(durations, targetDurations);
            
        case 'cutoffs'
            lowerLim = varargin{2};
            threshold = varargin{3};
            
            unqDurations = unique(durations);
            nUnqDurations = zeros(1,numel(unqDurations));
            
            % Count number of unique durations
            for iUnqDur = 1:length(unqDurations)
                theseDurations = (durations == unqDurations(iUnqDur));
                nUnqDurations(iUnqDur) = nnz(theseDurations);
            end
            
            targetDurations = ...
                (unqDurations >= lowerLim & nUnqDurations >= threshold);
            targetIndices = ...
                ismember(durations, unqDurations(targetDurations));
    end
else
    targetIndices = true(1, length(durations));
end

%% Compute average shapes

% Subsample avalanche shapes and durations using targeted indices
sampledShapes = shapes(targetIndices);
sampledDurations = durations(targetIndices);

% Ensure proper alignment of shapes for vertical concatenation
sampledShapes = reshape(sampledShapes, length(sampledShapes), 1);

% Compute mean temporal profile of avalanches with identical durations
unqSampledDurations = unique(sampledDurations);

avgProfiles = cell(numel(unqSampledDurations), 1);
for iUnqDur = 1:length(unqSampledDurations)
    theseShapes = ...
        sampledShapes(sampledDurations == unqSampledDurations(iUnqDur));
    avgProfiles{iUnqDur} = mean(cell2mat(theseShapes),1);
end

avgProfiles = avgProfiles(~cellfun('isempty', avgProfiles));