%% RASTERTOASDF2 - converts a spike raster into asdf2 format
% asdf2 is a structure-array based format for storing time raster data.
% asdf2 is the required format for avalanche statistics analysis.
%
% Syntax:   asdf2 = rastertoasdf2(raster, binSize, expSys, dataType, dataID, varargin)
%
% Inputs:
%   raster (double) - matrix whose rows represent neurons and columns
%     represent time bins
%   binSize (scalar double) - unit of time represented by each bin in the
%     data in ms
%   expSys (string) - description of the experimental system
%   dataType (string) - name of data type e.g. 'spikes' or 'LFP'
%   dataID (string) - name of the data set, date when it was collected, etc.
%
% Variable Inputs:
%   (..., 'experimenter', name) - adds name of experimenter, 'name' (string)
%   (..., 'visvers', visionversion) - adds version # of vision software 
%     used to collect data, 'visionversion' (string)
%   (..., 'comment', usercomment) - adds additional comment, 'usercomment'
%     (string)
%   (..., 'x', x) - adds physical horizontal positions of the channel on 
%     the array, x (integer double)
%   (..., 'y', y) - adds physical vertical positions of the channel on the 
%     array, y (integer double)
%   (..., 'hipp', hippInd) - adds list of channels which correspond to
%     hippocampal cells, hippInd (integer double)
%   (..., 'custom', label, value) - adds additional information, value, in
%     any format, denoted by 'label' (string)
%
% Output:
%   asdf2 (structure array). Fields (see list of inputs for more details):
%        .raster (cell array) - an array with one cell per channel (neuron),
%          containing the times when each neuron spikes
%        .binSize (input)
%        .nBins (scalar double) - number of time bins in raster
%        .nChannels (scalar double) - number of neurons, electrodes, or 
%          multiunit sources in the recording (scalar double)
%        .expSys (input)
%        .dataType (input)
%        .dataID (input)
%
% Example: 
%   raster = randi([0 1], [3 10]);
%   asdf2 = rastertoasdf2(raster, 1, 'organotypic', 'LFP', '2014-01-01-OrgSet1',...
%     'custom', 'recordingDuration', '1 hr');
%      % includes custom field "recordingDuration" with a value of "1 hr"
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: ASDF2TORASTER

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

function asdf2 = rastertoasdf2(raster, binSize, expSys, dataType, dataID, varargin)
%% Build asdf2 structure
nNeurons = size(raster, 1);

asdf2.raster = cell(nNeurons, 1);
% extract the indices for which each neuron fires
for iNeuron = 1:nNeurons
    asdf2.raster{iNeuron} = find(raster(iNeuron, :));
end

asdf2.binSize = binSize;

asdf2.nBins = size(raster, 2);

asdf2.nChannels = nNeurons;

%% Add information from inputs
asdf2.expSys = expSys;
asdf2.dataType = dataType;
asdf2.dataID = dataID;

%% Parse command line for variable arguments to append to structure
iVarArg = 1;

while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'experimenter', asdf2.experimenter = varargin{iVarArg+1};
            case 'visvers',      asdf2.visionversion = varargin{iVarArg+1};
            case 'comment',      asdf2.comment = varargin{iVarArg+1};
            case 'x',            asdf2.x = varargin{iVarArg+1};
            case 'y',            asdf2.y = varargin{iVarArg+1};
            case 'hippind',      asdf2.hippind = varargin{iVarArg+1};
            case 'custom'
                fieldName = varargin{iVarArg+1};
                value = varargin{iVarArg+2};
                asdf2 = setfield(asdf2, fieldName, value);
                iVarArg = iVarArg + 1;
            otherwise, 
                argOkay = false;
        end
        iVarArg = iVarArg + 1;
    end
    if ~argOkay
        disp(['(RASTERTOASDF2) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end