%% PVCALC - compute p-value for the pdf fit
% Calculates the p-value by Monte Carlo. The method uses a raw pdf with a 
% model that assumes a power law distribution with exponent tau for the 
% section of the data bounded by support [xmin,xmax]. The function 
% generates many sample distributions using a model that is composed of a 
% power-law within [xmin,xmax]. p is the proportion of sample distributions 
% with KS statistics larger than the KS statistic between the original pdf 
% and the model distribution. For computational efficiency, the function 
% continually updates the likelihood of successful results using the 
% binomial distribution and halts for statistically unlikely results.
%
% Syntax: [p, ks, sigmaTau] = pvcalc(x, tau, varargin)
%
% Inputs:
%   x (vector double) - empirical data, assumed to be power-law distributed
%   tau (scalar double) - the exponent of the power-law distribution
%
% Variable Inputs:
%   (..., 'xmin', xmin) - sets lower truncation of distribution (scalar
%     double) [default: min(x)]
%   (..., 'xmax', xmax) - sets upper truncation of distribution (scalar
%     double) [default: max(x)]
%   (..., 'samples', nSamples) - the number of sample distributions to draw.
%     Sets the resolution of the p-value (scalar double) (default: 500)
%   (..., 'threshold', pCrit) - for computational efficiency, a critical
%     p-value can be used to halt the computation if the likelihood of a
%     successful trial (given by the binomial distribution) drops below a
%     pre-determined likelihood value. If pCrit is set to 1, the 
%     computation will execute in full (scalar double) (default: 1)
%   (..., 'likelihood', likelihood) - likelihood threshold for binomial
%     process (scalar double) (default: 10^(-3))
%
% Outputs:
%   p (scalar double) - proportion of sample distributions with KS
%     statistics larger than the KS statistic between the empirical pdf and
%     the model distribution. p is bounded by 0 and 1. A p-value of 1 
%     indicates that the KS statistic between the empirical pdf and the 
%     model was smaller than the KS statistic between the sample 
%     distributions and the model. Conversely, a p-value of 0 indicates 
%     that KS(simulated) > KS(empirical) for every sample.
%   ks (scalar double) - Kolmogorov-Smirnov statistic between the 
%     empirical pdf and the model
%   sigmaTau (scalar double) - error of the tau original fit estimated 
%     using the samples drawn from the model fit. If p is small, this error
%     is not valid. 
%
% Example:
%   x = pldist(10^4);
%     % generate non-truncated, power-law distributed data
%   tau = plmle(x);
%   [p, ks, sigma] = pvcalc(x, tau)
%     % compute (truncated) p-value, KS statistic, and error on power law 
%     % exponent
%   p = pvcalc(x, tau, 'threshold', 1)
%     % compute full p-value
%   p = pvcalc(x, tau, 'likelihood', 10^-5)
%     % compute p-value with threshold for binomial process set to 10^-5
%
% Other m-files required: MYMNRND
% Subfunctions: MYMNRND
% MAT-files required: none
%
% See also: PLDIST, PLMLE, MYMNRND

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% November 2013; Last revision: 1-Jun-2015

% Version Information
%
%   1.0: 11/4/13 - Creation of the original program. (Nick Timme)
%
%   2.0: 11/8/13 - Modification of the ks statistic calculation algorithm.
%   Also, the pdf is cut to only include the region between xmin and xmax.
%   (Nick Timme)
%
%   3.0: 6/1/15 - Addition of exponential modification functionality. (Nick
%   Timme)
%

%==============================================================================
% Copyright (c) 2013, The Trustees of Indiana University
% All rights reserved.
% 
% Authors: Nick Timme (nicholas.m.timme@gmail.com)
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

function [p, ks, sigmaTau] = pvcalc(x, tau, varargin)
%% Parse command line for arguments
xmin = min(x);
xmax = max(x);
nSamples = 500;
pCrit = 1;
likelihood = 10^(-3);

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    switch varargin{iVarArg},
        case 'xmin',       xmin = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'xmax',       xmax = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'samples',    nSamples = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'threshold',  pCrit = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'likelihood', likelihood = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        otherwise,
            argOkay = false;
    end
    if ~argOkay
        disp(['(PVCALC) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Process Data

% ensure data oriented vertically
x = reshape(x, length(x), 1);

if isempty(setdiff(x, floor(x))) % integer data
    
    % calculate pdf of data using unique bins
    pdfX = histc(x, xmin:xmax);
    nSupportEvents = sum(pdfX);
    pdfX = pdfX / nSupportEvents;
    
    % calculate pdf of fit
    pdfFit = (xmin:xmax) .^ (-tau);
    pdfFit = pdfFit / sum(pdfFit);
    
    % calculate cdfs of empirical data and spliced data
    cdfX = 1 - cumsum(pdfX);
    cdfFit = 1 - cumsum(pdfFit);
    
    % ensure cdfs are oriented vertically
    cdfX = reshape(cdfX, length(cdfX), 1);
    cdfFit = reshape(cdfFit, length(cdfFit), 1);
    
else % continuous data
    
    % Limit the data to only the range under study
    x(x < xmin) = [];
    x(x > xmax) = [];
    
    % Sort the values of the data
    sortedx = sort(x,'ascend');
    
    % Calculate the data cdf
    cdfX = (1:length(x))./length(x);
    
    % Calculate the y value of the fit cdf
    cdfFit = ((1 - (sortedx).^(1 - tau)) - (1 - xmin^(1 - tau))) / ((1 - xmax^(1 - tau)) - (1 - xmin^(1 - tau)));
    
    % ensure cdfs are oriented vertically
    cdfX = reshape(cdfX, length(cdfX), 1);
    cdfFit = reshape(cdfFit, length(cdfFit), 1);
end

%% Calculate the Kolmogorov-Smirnov statistic for the empirical data

empiricalKS = max(abs(cdfX - cdfFit));

% save result
ks = cell(2,1);
ks{2} = zeros(nSamples, 1);
ks{1} = empiricalKS;

%% Calculate the p-value
successCounts = zeros(1, nSamples);

% Computation reduces to binomial process. Carry out conditional on the
% likelihood of the number of successes given the number of trials
nSuccesses = 0;
thisLikelihood = 1;
binomialFlag = true; 
criticalThreshold = nSamples*pCrit;

iSample = 1;
sampleTau = zeros(nSamples, 1);
warning('off','MATLAB:nchoosek:LargeCoefficient')

while iSample <= nSamples && thisLikelihood > likelihood && binomialFlag
    
    if isempty(setdiff(x, floor(x))) % integer data
        
        % generate sample data using fit of the real data
        xSampleNo = mymnrnd(nSupportEvents, pdfFit);
        xSample = rldecode(xSampleNo, xmin:xmax);
        
        % compute sample pdf using unique bins
        pdfSample = histc(xSample, xmin:xmax) / nSupportEvents;
        
        % fit sample to pre-determined support range (only compute if we'll use
        % it)
        if pCrit == 1
            thisTau = plmle(xSample, 'xmin', xmin, 'xmax', xmax);
            sampleTau(iSample) = thisTau;
        end
        
        % compute cdf of sample
        cdfSample = 1 - cumsum(pdfSample);
        
        % ensure cdfs are oriented vertically
        cdfSample = reshape(cdfSample, length(cdfSample), 1);
        
        
    else % continuous
        
        % generate sample data using fit of the real data
        xSample = gendata(length(x),{'powerlaw',tau},'continuous','xmin',xmin,'xmax',xmax);
        
        % fit sample to pre-determined support range (only compute if we'll use
        % it)
        if pCrit == 1
            thisTau = plmle(xSample, 'xmin', xmin, 'xmax', xmax);
            sampleTau(iSample) = thisTau;
        end
        
        % Sort the values of the sample
        sortedSample = sort(xSample,'ascend');
    
        % Calculate the cdf of the sample
        cdfSample = (1:length(x))./length(x);
        
         % Calculate the y value of the fit cdf
        cdfFit = ((1 - (sortedSample).^(1 - tau)) - (1 - xmin^(1 - tau))) / ((1 - xmax^(1 - tau)) - (1 - xmin^(1 - tau)));
        
        % ensure cdfs are oriented vertically
        cdfSample = reshape(cdfSample, length(cdfSample), 1);
        cdfFit = reshape(cdfFit, length(cdfFit), 1);
        
    end
    
    % calculate the KS statistic for simulated data
    sampleKS = max(abs(cdfSample - cdfFit));
    
    % Record the sample KS
    ks{2}(iSample) = sampleKS;
    
    % record a success if the empirical KS is bounded above by the sample KS
    if empiricalKS <= sampleKS
        successCounts(iSample) = 1;
        nSuccesses = nSuccesses + 1;
    end
    
    % stop computation if number of successes reaches threshold
    if nSuccesses == criticalThreshold
        binomialFlag = false;
    end
    
    % update likelihood if critical threshold less than 1
    if pCrit ~= 1
        thisLikelihood = 1 - binocdf(criticalThreshold - nSuccesses - 1,...
            nSamples - iSample, pCrit);
    end
    
    iSample = iSample + 1;
end

warning('on','MATLAB:nchoosek:LargeCoefficient')

p = sum(successCounts) / nSamples;

if iSample == (nSamples + 1)
    sigmaTau = std(sampleTau);
else
    sigmaTau = NaN;
end

end