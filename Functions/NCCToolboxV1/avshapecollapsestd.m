%% AVSHAPECOLLAPSESTD - computes error on shape collapse
% Computes the error on the shape collapse estimate of 1/(sigma nu z) by 
% non-parametric bootstrap.
%
% Syntax: sigmaNuZInvStd = avshapecollapsestd(avgShapes, varargin)
%
% Input:
%   avgShapes (cell array) - array of mean temporal profiles (vector double)
%
% Variable Inputs:
%   (..., 'precision', precision) - sets the decimal precision for the
%     parameter search, precision (scalar double) (default: 10^-3)
%   (..., 'interpPoints',ninterpPoints) - sets the number of interpolation
%     points used in calculating the shape collapse error (power of ten 
%     scalar double) (default: 10^3)
%   (..., 'bounds', bounds) - sets the bounds on the initial range of
%     exponent values (vector double) (default: [0 4])
%   (..., 'samples', sampleSize) - sets the size of each sample set
%     (scalar double) (default: (round(number of shapes / 2) )
%   (..., 'trials', nTrials) - sets the number of bootstrap samples 
%     (scalar double) (default: min(nchoosek(number of shapes, sample size), 100) )
%
% Output:
%   sigmaNuZInvStd (scalar double) - standard deviation 1/(sigma nu z)
%     shape collapse estimate
%
% Example:
%   raster = randi([0 1], [10 1000]);
%   asdf = sparse2asdf(raster, 1);
%   asdf2 = asdftoasdf2(asdf, 'test', 'spikes', 'date');
%   Av = avprops(asdf2, 'duration', 'shape');
%   avgProfiles = avgshapes(Av.shape, Av.duration, 'cutoffs', 5, 50);
%   sigmaNuZInv = avshapecollapse(avgProfiles);
%     % computes 1/(sigma nu z) estimate, though not needed for the error
%   sigmaNuZInvStd = avshapecollapsestd(avgProfiles)
%
% Other m-files required: AVSHAPECOLLAPSE
% Subfunctions: AVSHAPECOLLAPSE
% MAT-files required: none
%
% See also: AVPROPS, AVGSHAPES, AVSHAPECOLLAPSE

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% June 2013; Last revision: 11-September-2015

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

function sigmaNuZInvStd = avshapecollapsestd(avgShapes, varargin)
%% Parse command line for variable arguments
precision = 10^-3;
ninterpPoints = 10^3;
bounds = [0 4];
nShapes = length(avgShapes);
sampleSize = round(nShapes / 2);
nTrials = min(nchoosek(nShapes, sampleSize), 100);

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'precision'
                precision = varargin{iVarArg+1};            
            case 'samples'
                sampleSize = varargin{iVarArg + 1};
                nTrials = min(nchoosek(nShapes, sampleSize), 100);
            case 'interpPoints'
                ninterpPoints = varargin{iVarArg+1};
                iVarArg = iVarArg+1;
            case 'trials'
                nTrials = varargin{iVarArg + 1};
            case 'bounds'
                bounds = varargin{iVarArg + 1};
                iVarArg = iVarArg + 1;           
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(AVSHAPECOLLAPSESTD) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Get bootstrap samples
samplingIndices = cell(nTrials, 1);
for iTrial = 1:nTrials
    if sampleSize == 1
        % enumerate indices for small samples
        samplingIndices{iTrial} = iTrial;
    else
        TempRand = randperm(nShapes);
        samplingIndices{iTrial} = sort(TempRand(1:sampleSize));
    end
end

%% Compute 1/(sigma nu z) for all sample groups
sigmaNuZInvVec = zeros(length(samplingIndices), 1);
for iTrial = 1:nTrials
    avgShapesSample = avgShapes(samplingIndices{iTrial}');
    
    sigmaNuZInvVec(iTrial) = avshapecollapse(avgShapesSample,...
        'bounds', bounds, 'precision', precision, 'interpPoints', ninterpPoints);
end

%% Take standard deviation of all critical exponent values
sigmaNuZInvStd = std(sigmaNuZInvVec);
end