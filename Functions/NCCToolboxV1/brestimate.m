%% BRESTIMATE - branching ratio estimate
% Estimates the branching ratio for asdf2 format data under the assumption
% the data is sub-sampled using the method established by Priesemann and
% Wilting.
%
%   Citation: V. Priesemann and J. Wilting, Spike rate homeostasis tunes
%   networks to sub-criticality, Neuroscience 2015 Abstracts (2015).
%
% Syntax:   [br,slopevals,brsimple] = brestimate(asdf2, varargin)
%
% Inputs:
%   asdf2 (structure array) - contains time raster and other information
%
% Variable Inputs:
%   (..., 'actrange', actrange) - sets the range of activity values to 
%       consider (vector) (default: 0:asdf2.nchannels)
%   (..., 'delayrange', delayrange) - sets the range of delays to fit 
%       (vector) (default: 1:100)
%
% Output:
%   br (scalar) - branching ratio estimate for a sub-sampled system using
%       the method established by Priesemann and Wilting
%   slopevals (vector) - slope values found from regressions for the
%       specificed delayrange
%   brsimple (scalar) - branching ratio estimate assuming no sub-sampling
%
% Example: 
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%

% Authors: Nicholas Timme
% Email: nicholas.m.timme@gmail.com
% November 2015

%==============================================================================
% Copyright (c) 2015, The Trustees of Indiana University
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

function [br,slopevals,brsimple] = brestimate(asdf2, varargin)
%% Parse command line for variable arguments
actrange = 0:asdf2.nchannels;
delayrange = 1:100;

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    switch varargin{iVarArg},
        case 'actrange',        actrange = varargin{iVarArg+1};     iVarArg = iVarArg + 1;
        case 'delayrange',      delayrange = varargin{iVarArg+1};   iVarArg = iVarArg + 1;
        otherwise,
            argOkay = false;
    end
    if ~argOkay
        disp(['(BRESTIMATE) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end


%% Calculate the branching ratios

% First, find the total activity vector
Act = zeros([1,asdf2.nbins]);
for iChannel = 1:asdf2.nchannels
    Act(asdf2.raster{iChannel}) = Act(asdf2.raster{iChannel}) + 1;
end

% Second, calculate the branching ratio under the assumption of no
% sub-sampling
At = Act(1:(asdf2.nbins - 1));
At1 = Act(2:asdf2.nbins);
At1(~ismember(At,actrange)) = [];
At(~ismember(At,actrange)) = [];
Coeffs = polyfit(At,At1,1);
brsimple = Coeffs(1);

% Now, calculate the regression slopes 
slopevals = zeros([1,length(delayrange)]);
for ik = 1:length(delayrange)
    
    At = Act(1:(asdf2.nbins - delayrange(ik)));
    Atk = Act((1 + delayrange(ik)):asdf2.nbins);
    Atk(~ismember(At,actrange)) = [];
    At(~ismember(At,actrange)) = [];
    Coeffs = polyfit(At,Atk,1);
    slopevals(ik) = Coeffs(1);
    
end

% Perform the exponential fit on the slopes
x0 = [1,1];
[ExpCoeffs,resnorm] = lsqcurvefit(@expfit,x0,delayrange,slopevals);

br = ExpCoeffs(1);

end

% The exponential fit
function F = expfit(x,xdata)
F = x(2)*(x(1).^(xdata));


end