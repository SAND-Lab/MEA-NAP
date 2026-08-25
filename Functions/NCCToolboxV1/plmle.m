%% PLMLE - maximum likelihood estimation for power law distributed data
% Estimates slope of power law distributed data using the method of maximum
% likelihood.
%
% Syntax: [tau, xmin, xmax, L] = plmle(x, varargin)
%
% Input:
%   x (vector double) - random data to be fitted to the power law 
%     distribution p(x) ~ x^(-tau) for x >= xmin and x <= xmax. 
%
% Variable Inputs:
%   (..., 'xmin', xmin) - specifies the lower truncation of distribution
%     for the fit (scalar double) (default: min(x))
%   (..., 'xmax', xmax) - specifies the upper truncation of distribution
%     for the fit (scalar double) (default: max(x))
%   (..., 'tauRange', tauRange) - sets the range of taus to test for the
%     MLE fit (vector double) (default: [1, 5])
%   (..., 'precision', precision) - sets the decimal precision for the MLE
%     search (scalar double (power of ten)) (default: 10^-3)
%
% Outputs:
%   tau (scalar double) - slope of power law region
%   xmin (scalar double) - lower truncation of distribution
%   xmax (scalar double) - upper truncation of distribution
%   L (vector double) - log-likelihood that we wish to maximize for the MLE
%
% Example:
%   x = pldist(10^4);
%     % generates perfectly non-truncated power-law distributed data with
%     % slope of 1.5
%   tau = plmle(x)
%     % computes tau by MLE for x
%   tau = plmle(x, 'precision', 10^-4)
%     % computes tau to 4 decimal places
%   x = pldist(10^4, 'upper', 50, 1.5);
%     % generates perfectly power-law distributed data for x <= 50
%   tau = plmle(x, 'xmax', 50)
%     % computes tau for truncated region
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: BENTPL, PLPLOT, PLPARAMS

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% May 2014; Last revision: 8-Apr-2016

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


function [tau, xmin, xmax, L] = plmle(x, varargin)
%% Parse command line for parameters
xmin = min(x);
xmax = max(x);
tauRange = [1,5];
precision = 10^-3;

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    switch varargin{iVarArg},
        case 'xmin',       xmin = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'xmax',       xmax = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'tauRange',   tauRange = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'precision',  precision = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        otherwise,
            argOkay = false;
    end
    if ~argOkay
        disp(['(PLMLE) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

% Error check the precision
if log10(precision) ~= round(log10(precision))
    error('The precision must be a power of ten.')
end

%% Process data
% Reshape
x = reshape(x, numel(x), 1);

% Determine data type
if nnz(abs(x - round(x)) > 3*eps) > 0
    dataType = 'CONT';
else
    dataType = 'INTS';
    x = round(x);
end

% Truncate
z = x(x >= xmin & x <= xmax);
unqZ = unique(z);
nZ = length(z);
nUnqZ = length(unqZ);
allZ = xmin:xmax;
nallZ = length(allZ);

%% MLE calculation
r = xmin / xmax;

nIterations = -log10(precision);   

for iIteration = 1:nIterations
    
    spacing = 10^(-iIteration);
    
    if iIteration == 1
        taus = tauRange(1):spacing:tauRange(2);
    else
        if tauIdx == 1
            taus = taus(1):spacing:taus(2);
        elseif tauIdx == length(taus)
            taus = taus(end-1):spacing:taus(end);
        else
            taus = taus(tauIdx-1):spacing:taus(tauIdx+1);
        end
    end
    
    nTaus = length(taus);
    
    if strcmp(dataType, 'INTS')
        
        % replicate arrays to equal size
        allZMat = repmat(reshape(allZ,[nallZ,1]),[1,nTaus]);
        tauMat = repmat(taus,[nallZ,1]);
        
        % compute the log-likelihood function
        L = - log(sum(allZMat.^(-tauMat), 1))...
            - (taus/nZ) * sum(log(z));
        
    elseif strcmp(dataType, 'CONT')
        
        % compute the log-likelihood function (method established via
        % Deluca and Corral 2013)
        L = log( (taus - 1) ./ (1 - r.^(taus - 1)) )...
            - taus * (1/nZ) * sum(log(z))...
            - (1 - taus) * log(xmin);
        
        if ismember(1,taus)
            L(taus == 1) = -log(log(1/r)) - (1/nZ) * sum(log(z));
        end
        
    end
    
    [unused, tauIdx] = max(L);
    
end

% Pick the tau value that maximizes the log-likelihood function
tau = taus(tauIdx);

end