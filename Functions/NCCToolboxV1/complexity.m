%% COMPLEXITY - computes the neural complexity of a spike raster
% Computes the neural complexity measure as developed by (Tononi, 1994):
% the difference between the linear scale of the total system integration
% and the average integration of j subsets of sizes k. To handle the
% problem of combinatorial explosion for increasing system size, the
% algorithm subsamples j from the total possibilities.
%
% Syntax: [cn, IntInfPart] = complexity(raster, nSubSets, varargin)
%
% Inputs:
%   raster (double) - matrix whose rows represent neurons and columns
%       represent time bins
%   nSubSets (integer) - value that determines the maximum number of the j
%       subsets of size k to process. 
%
% Variable Inputs:
%   (..., 'subsampcorrect') - authorizes the function to perform the
%       subsampling correction. The original data are randomized and the
%       random data integration curve is subtracted from the real data
%       integration curve. Turn over in the corrected integration curve is
%       automatically detected and accounted for by removing subsets above
%       the turn over.
%
% Outputs:
%   cn (scalar double) - neural complexity
%   IntInfPart (scalar double vector) - integrated information for each
%       subset size. IntInfPart(k) is the integration for subsets of size
%       k. Note, the integrated information is the average across at most
%       nSubSets sample combinations.
%
% Example:
%   raster = randi([0,1], [100, 10^4]);
%   [cn intInfPart] = complexity(raster, 10^2)
%     % compute neural complexity and integrated information using an
%     % estimate of the entropy measures   
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: ASDF2TORASTER

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% July 2013; Last revision: 6-May-2015

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

function [Cn,IntInfPart] = complexity(X,nSubSets,varargin)
%% Parse command line for variable arguments
SubSampFlag = false;

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'subsampcorrect',	SubSampFlag = true;
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(COMPLEXITY) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Perform the Analysis

% Get basic information
nNeurons = size(X,1);
nT = size(X,2);

% Make the master list of states and variables
[B,I,J] = unique(X','rows');
MasterList = B;
MasterCounts = hist(J,1:size(B,1))';

% Calculate individual neuron entropies
nSpikes = sum(X,2);
NeurEnt = -((nSpikes/nT) .* log2(nSpikes/nT)) - (((nT - nSpikes)/nT) .* log2((nT - nSpikes)/nT));

% Go through the partitions
IntInfPart = zeros([1,nNeurons]);
warning('off','all')
for iNeurons = 2:nNeurons
    disp([num2str((iNeurons*100)/nNeurons),' Percent Done with Complexity Calculation'])
    if nchoosek(nNeurons,iNeurons) <= nSubSets
        NeuronSubSets = nchoosek(1:nNeurons,iNeurons);
    else
        NeuronSubSets = zeros([nSubSets,iNeurons]);
        for iSubSet = 1:nSubSets
            temp = randperm(nNeurons);
            NeuronSubSets(iSubSet,:) = temp(1:iNeurons);
        end
    end
    nTempSubSets = size(NeuronSubSets,1);
    TempIntInfo = zeros([1,nTempSubSets]);
    for iTempSubSet = 1:nTempSubSets
        [B,I,J] = unique(MasterList(:,NeuronSubSets(iTempSubSet,:)),'rows');
        p = accumarray(J,MasterCounts) / nT;
        TempIntInfo(iTempSubSet) = sum(NeurEnt(NeuronSubSets(iTempSubSet,:))) + sum(p .* log2(p));
    end
    IntInfPart(iNeurons) = mean(TempIntInfo);
end

Cn = sum(linspace(0,IntInfPart(end),nNeurons) - IntInfPart) / (nNeurons);


%% If necessary, perform the subsampling correction
if SubSampFlag
    
    % Mark the real data integration curve
    IntInfPartReal = IntInfPart;
    
    % Randomize the data
    for iNeuron = 1:nNeurons
        X(iNeuron,:) = X(iNeuron,randperm(nT));
    end
    
    % Make the master list of states and variables
    [B,I,J] = unique(X','rows');
    MasterList = B;
    MasterCounts = hist(J,1:size(B,1))';
    
    % Calculate individual neuron entropies
    nSpikes = sum(X,2);
    NeurEnt = -((nSpikes/nT) .* log2(nSpikes/nT)) - (((nT - nSpikes)/nT) .* log2((nT - nSpikes)/nT));
    
    % Go through the partitions
    IntInfPart = zeros([1,nNeurons]);
    warning('off','all')
    for iNeurons = 2:nNeurons
        disp([num2str((iNeurons*100)/nNeurons),' Percent Done with Complexity Calculation'])
        if nchoosek(nNeurons,iNeurons) <= nSubSets
            NeuronSubSets = nchoosek(1:nNeurons,iNeurons);
        else
            NeuronSubSets = zeros([nSubSets,iNeurons]);
            for iSubSet = 1:nSubSets
                temp = randperm(nNeurons);
                NeuronSubSets(iSubSet,:) = temp(1:iNeurons);
            end
        end
        nTempSubSets = size(NeuronSubSets,1);
        TempIntInfo = zeros([1,nTempSubSets]);
        for iTempSubSet = 1:nTempSubSets
            [B,I,J] = unique(MasterList(:,NeuronSubSets(iTempSubSet,:)),'rows');
            p = accumarray(J,MasterCounts) / nT;
            TempIntInfo(iTempSubSet) = sum(NeurEnt(NeuronSubSets(iTempSubSet,:))) + sum(p .* log2(p));
        end
        IntInfPart(iNeurons) = mean(TempIntInfo);
    end
    
    % Correct the integration curve
    IntInfPart = IntInfPartReal - IntInfPart;
    
    % Find the maximum slope and cut the extra points
    m = IntInfPart(2:end) ./ (1:(length(IntInfPart) - 1));
    mpd = round(0.1*length(IntInfPart));
    mpd(mpd < 3) = 3;
    if length(m) >= 3
        [peaks,locs] = findpeaks(m,'minpeakdistance',mpd);
        if ~isempty(locs)
            Cut = locs(1) + 2;
        else
            Cut = length(IntInfPart) + 1;
        end
    else
        Cut = length(IntInfPart) + 1;
    end
    IntInfPart(Cut:end) = [];
    
    % Calculate the complexity
    Cn = sum(linspace(0,IntInfPart(end),length(IntInfPart)) - IntInfPart) / (length(IntInfPart));
    
end

end

