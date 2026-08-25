%% ASDF2TORASTER - converts ASDF2 formatted data into a spike raster
%
% Syntax:   [raster, binSize] = asdf2toraster(asdf2)
%
% Inputs:
%   asdf2 (structure array) - contains time raster and other information
%
% Variable Inputs: none
%
% Outputs:
%   raster (double) - matrix whose rows represent neurons and columns
%     represent time bins
%   binSize (double) - integer unit of time per bin in the data in ms
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: RASTERTOASDF2, REBIN

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% May 2013; Last revision: 13-July-2014

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

function [raster, binSize] = asdf2toraster(asdf2)
%%
binSize = asdf2.binSize;

% pre-allocate spike raster
raster = zeros(numel(asdf2.raster), asdf2.nBins);

nNeurons = size(raster, 1);

% insert 1 at each time bin when the neuron spikes
for iNeuron = 1:nNeurons
    raster(iNeuron, asdf2.raster{iNeuron}) = 1;
end
end