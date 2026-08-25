%% PLPARAMS - automated computation of power law parameters using MLE
% Higher level macro and automated algorithm that computes the exponent for
% power-law distributed data and its uncertainty, the p-value and ks
% statistic for the fit, and searches for optimal support [xmin,xmax]. The
% function utilizes a "smart" greedy search algorithm to settle on a
% support pair. Prior to initiating the greedy search, all support pairs
% for which xmin and xmax differ by 1 are removed; the remainder are then
% sorted by log(xmax/xmin).
%
% Syntax: [tau, xmin, xmax, sigmaTau, p, pCrit, ks] = plparams(x, varargin)
%
% Input:
%   x (vector double) - random data that we would like to fit to the power
%     law distribution p(x) ~ x^(-tau) for x >= xmin and x <= xmax.
%
% Variable Inputs:
%   (..., 'samples', nSamples) - the number of sample distributions to draw.
%     Sets the resolution of the p-value (scalar double) (default: 500)
%   (..., 'threshold', pCrit) - for computational efficiency, a critical
%     p-value can be used to halt the computation if the likelihood of a
%     successful trial (given by the binomial distribution, see likelihood
%     below) drops below a pre-determined likelihood value. If pCrit is set
%     to 1, the computation will execute in full. Note: this only affects 
%     the greedy search process; final p-value is computed in full (scalar 
%     double) (default: .2)
%   (..., 'likelihood', likelihood) - likelihood threshold for binomial
%     process (scalar double) (default: 10^(-3))
%
% Outputs:
%   tau (scalar double) - slope of power law region
%   xmin (scalar double) - lower truncation of distribution
%   xmax (scalar double) - upper truncation of distribution
%   sigmaTau (scalar double) - error of the tau original fit estimated 
%     using the samples drawn from the model fit. If p is small, this error
%     is not valid.
%   p (scalar double) - proportion of sample distributions with KS
%     statistics larger than the KS statistic between the empirical pdf and
%     the model distribution. p is bounded by 0 and 1. A p-value of 1 
%     indicates that the KS statistic between the empirical pdf and the 
%     model was smaller than the KS statistic between the sample 
%     distributions and the model. Conversely, a p-value of 0 indicates 
%     that KS(simulated) > KS(empirical) for every sample.
%   pCrit (scalar double) - critical p-value used to truncate computation
%   ks (scalar double) - Kolmogorov-Smirnov statistic between the 
%     empirical pdf and the model
%
% Example:
%   x = bentpl(10000);
%     % generates random data distributed between two disjoint power law
%       regions with slopes 1.5 and 2.5 and first upper truncation of 50
%   [tau, xmin, xmax, sigma, p, pCrit, ks] = plparams(x);
%     % compute all power law parameters
%   [tau,~,~,~,p] = plparams(x, 'threshold', 1);
%     % compute power law exponent and full p-value
%   [~,~,~,~,p] = plparams(x, 'threshold', 1, 'samples', 1000);
%     % compute full p-value using 1000 simulated sets (increases
%       resolution of p-value)
%
% Other m-files required: PLMLE, PVCALC, MYMNRND
% Subfunctions: PLMLE, PVCALC
% MAT-files required: none
%
% See also: BENTPL, PLMLE, PVCALC, MYMNRND

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% May 2014; Last revision: 13-Apr-2016

%==============================================================================
% Copyright (c) 2014, The Trustees of Indiana University
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

function [tau, xmin, xmax, sigmaTau, p, pCrit, ks] = plparams(x, varargin)
%% Parse command line for parameters

nSamples = 500;
pCrit = .2;
likelihood = 10^(-3);

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    switch varargin{iVarArg},
        case 'samples',    nSamples = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'threshold',  pCrit = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'likelihood', likelihood = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        otherwise,
            argOkay = false;
    end
    if ~argOkay
        disp(['(PLPARAMS) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Process data

% ensure data is oriented vertically
nX = numel(x);
x = reshape(x, nX, 1);

% find unique x values
unqX = unique(x);

%% Sort data in decreasing order by normalized Euclidean distance

% get all support pairs
support = nchoosek(unqX,2);

% remove adjacent unique points
for iUnqX = 1:length(unqX)
    support(find(support(:,1) == unqX(iUnqX),1,'first'),:) = [];
end

% compute 1/r = xmax/xmin for all support pairs
rInv = support(:,2)./support(:,1);

% get the amount of data covered by each support pair (nData)
nSupport = size(support, 1);

% compute and normalize natural log of 1/r
lnRInv = log(rInv) / log(max(rInv));

% rank support pairs by normalized ln(1/r)
rank = lnRInv.^2;

% sort support pairs by rank in descending order
[unused, idx] = sort(rank, 'descend');
support = support(idx,:);

%% Initiate greedy search for optimal support

% Try support pairs in ranked order until p = pCrit
sweepFlag = true;
iSupport = 1;
while sweepFlag && iSupport <= nSupport
    
    % print the current support pair to inform user
    iSupport
    
    xmin = support(iSupport,1); 
    xmax = support(iSupport,2);
    
    % MLE of truncated distribution
    [tau, waste1, waste2, waste3] = plmle(x, 'xmin', xmin, 'xmax', xmax);
    
    % p-value for MLE
    p = pvcalc(x, tau, 'xmin', xmin, 'xmax', xmax, 'samples', nSamples,...
        'threshold', pCrit, 'likelihood', likelihood);
    
    % halt search if p-value reaches critical p-value
    if p >= pCrit
        sweepFlag = false;
    else
        iSupport = iSupport + 1;
    end
end

%% Compute final statistics and full p-value

[p, ks, sigmaTau] = pvcalc(x, tau, 'xmin', xmin, 'xmax', xmax,...
    'samples', nSamples, 'threshold', 1);

end