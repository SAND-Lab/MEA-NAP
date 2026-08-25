%% REBIN - rebins asdf2 formatted data
% Bins divide neuronal activity time series data into blocks of time which
% indicate whether or not a neuron was active. In this case time bins are 
% uniformly spaced and in units of milliseconds.
%
% Syntax:   newAsdf2 = rebin(asdf2, binSize)
%
% Inputs:
%   asdf2 (structure array) - contains time raster and other information
%   binSize (double) - integer unit of time per bin in the data in ms
%
% Variable Inputs: none
%
% Output:
%   newAsdf2 (structure array) - rebinned asdf2 structure array
%
% Example: 
%   raster = randi([0 1], [3 10]);
%   asdf = sparse2asdf(raster, 2);
%   asdf2 = asdftoasdf2(asdf, 'organotypic', 'LFP', '2014-01-01-OrgSet1');
%   newAsdf2 = rebin(asdf2, 4);
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: SPARSE2ASDF, ASDFTOASDF2

% Author: Najja Marshall and Nick Timme
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

function newAsdf2 = rebin(asdf2, binSize)
%%
resolution = (10^(ceil(log10(round(binSize/asdf2.binsize))) + 1))*eps;
newBinIsIntMult = (abs(round(binSize/asdf2.binsize) - (binSize/asdf2.binsize)) < resolution);
assert(newBinIsIntMult,...
    'binSize must be an integer multiple of asdf2.binsize.')

%%
newAsdf2 = asdf2;
rebinFactor = 1 / round(binSize/asdf2.binsize);
for iRaster = 1:newAsdf2.nchannels
    newAsdf2.raster{iRaster} = unique(ceil(asdf2.raster{iRaster} * rebinFactor));
end

newAsdf2.binsize = binSize;
newAsdf2.nbins = ceil(asdf2.nbins*rebinFactor);
