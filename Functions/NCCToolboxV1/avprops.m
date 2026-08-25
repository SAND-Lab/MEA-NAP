%% AVPROPS - computes avalanche properties
% Neuronal avalanches are contiguous (time) bins of activity preceded and 
% followed by at least one bin of quiescence. Avalanches are characterized
% by their duration (number of active time bins), size (total number of
% activated neurons), shape (number of neurons activated at each time bin),
% and branching ratio (number of neurons active at time step t divided by
% the number active at time step t-1). By default this function returns the
% avalanche size, duration, and shape, but the branching ratio and
% fingerprint (defined below) may also be computed if indicated by the
% user.
%
% Syntax:   Avalanche = avprops(asdf2, varargin)
%
% Inputs:
%   asdf2 (structure array) - contains time raster and other information
%
% Variable Inputs:
%   (..., 'ratio') - authorizes function to compute the branching ratio.
%     Note, this branching ratio is calculated as simply the ratio of the
%     activity at time step t to the activity at time step t + 1. For
%     branching ratio estimate under subsampling, see the function
%     brestimate.m.
%   (..., 'fingerprint') - authorizes function to compute avalanche finger
%     print, a cell array containing matrix arrays M whose first row is 
%     event times and second row the corresponding channels. 
%     size(M) = [2, s, num(avs_s)], where s is a size and num(avs_s) is the
%     number of avalanches with size s. Avalanche.fingerPrint is sorted by
%     increasing size and size(Avalanche.fingerPrint) = [max(s), 1].
%
% Output:
%   Avalanche (structure array) - contains avalanche properties
%
% Example: 
%   raster = randi([0 1], [3 10]);
%   asdf2 = rastertoasdf2(raster, 1, 'organotypic', 'LFP', '2014-01-01-OrgSet1');
%   Av = avprops(asdf2, 'ratio')
%     % compute branching ratio in addition to basic 3 properties
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: ASDFTOASDF2, BRESTIMATE

% Author: Najja Marshall and Nick Timme and Rashid Williams-Garcia
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% May 2013; Last revision: 27-June-2014

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

function Avalanche = avprops(asdf2, varargin)
%% Parse command line for variable arguments
Flag.branchingRatio = false;
Flag.fingerPrint = false;

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'ratio',         Flag.branchingRatio = true;
            case 'fingerprint',   Flag.fingerPrint = true;
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(AVPROPS) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Detect avalanches
allTimes = []; allSites = [];
for iAv = 1:length(asdf2.raster)
    % Extract all event times (e.g. LFP peaks, neuron firings)
    allTimes = [allTimes asdf2.raster{iAv}];
    
    % Extract corresponding channel (e.g. electrode) for each event
    allSites = [allSites iAv*ones(1,numel(asdf2.raster{iAv}))];
end

assert(~isempty(allTimes), 'Empty raster; no avalanches detected.')

[allTimes, sortedTimesIndex] = sort(allTimes);
allSites = allSites(sortedTimesIndex);
sortedEvents = vertcat(allTimes,allSites);

% Take differences in event times to determine avalanche boundaries
diffTimes = diff(allTimes); 
diffTimes(diffTimes==1) = 0;
avBoundaries = find(diffTimes); 
avBoundaries = [avBoundaries size(sortedEvents,2)];
nAvs = numel(avBoundaries);

%% Compute avalanche properties

% Pre-allocate structure fields
Avalanche.duration = zeros(1,nAvs);

Avalanche.size = zeros(1,nAvs);

Avalanche.shape = cell(nAvs,1);

if Flag.fingerPrint
    % Determine maximum avalanche size
    if length(avBoundaries) == 1
        maxAvSize = avBoundaries;
    else
        lengthFirstAv = length(1:avBoundaries(1));
        lengthOtherAvs = max(diff(avBoundaries));
        
        maxAvSize = max(lengthFirstAv, lengthOtherAvs);
    end
    Avalanche.fingerPrint = cell(maxAvSize,1);
end

if Flag.branchingRatio
    Avalanche.branchingRatio = zeros(1, nAvs);
end


% Start search for avalanches and compute their properties
avStart = 1;
for iAv = 1:nAvs
    avEnd = avBoundaries(iAv);
    
    Avalanche.shape{iAv} = histc(sortedEvents(1, avStart:avEnd),...
        unique(sortedEvents(1, avStart:avEnd)));
    
    % Get current avalanche
    thisAv = allTimes(avStart:avEnd);
    Avalanche.duration(iAv) = numel(unique(thisAv));
    Avalanche.size(iAv) = numel(thisAv);
    
    if Flag.fingerPrint
        if isempty(Avalanche.fingerPrint{Avalanche.size(iAv)})
            Avalanche.fingerPrint{Avalanche.size(iAv)} = ...
                sortedEvents(:, avStart:avEnd);
        else
            fingerPrintIndex = ...
                size(Avalanche.fingerPrint{Avalanche.size(iAv)}, 3) + 1;
            Avalanche.fingerPrint{Avalanche.size(iAv)}(:, :, fingerPrintIndex) = ...
                sortedEvents(:, avStart:avEnd);
        end
    end
    
    if Flag.branchingRatio
        thisShape = Avalanche.shape{iAv};
        Avalanche.branchingRatio(iAv)= ...
            sum(thisShape(2:end) ./ thisShape(1:end-1)) ...
            / Avalanche.duration(iAv);
    end
    
    avStart = avEnd + 1;
end