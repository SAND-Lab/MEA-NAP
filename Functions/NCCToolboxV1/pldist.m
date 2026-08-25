%% PLDIST - generates power-law distributed data
% Generates perfectly power-law distributed data with optional arguments
% for creating lower, upper, or doubly truncated data. Non-power-law
% distributed regions are exponentially distributed. The data are discrete.
%
% Syntax: x = pldist(nStart, varargin)
%
% Input: nStart (scalar double) - number of starting points
%
% Variable Inputs:
%   (..., 'infimum', infimum) - sets the absolute minimum value of the data
%     [default: 1]
%   (..., 'supremum', supremum) - sets the absolute maximum value of the
%     data [default: 10^(ceil(log10(nStart)) + 1)]
%   (..., 'slope', slope) - sets the slope for non-truncated power-law
%     distribution, which the function creates by default [default: 1.5]
%   (..., 'lambda', lambda) - sets the lambda value used for non-power-law
%     distributed data [default: 0.025]
%   (..., 'upper', xmax) - generates power-law distributed
%     data x such that x <= xmax. x within the truncated region is 
%     distributed with scaling exponent slope and is exponentially
%     distributed outside the truncated region.
%   (..., 'lower', xmin) - generates power-law distributed data x such that
%     x >= xmin with exponent slope. xmin must be strictly greater than the
%     infimum.
%   (..., 'double', xmin, xmax) - generates power-law distributed data x
%     such that xmin <= x <= xmax. xmin and xmax must be strictly greater
%     and lower than the infimum and supremum.
%   (..., 'plot') - plots distribution
%
% Output:
%   x (vector double) - random data distributed within two disjoint power 
%     law regions
%
% Example:
%   x = pldist(10000);
%
% Other m-files required: RLDECODE
% Subfunctions: RLDECODE
% MAT-files required: none
%
% See also: RLDECODE, PLMLE, PLPLOT, PLPARAMS

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% June 2013; Last revision: 7-July-2014

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

function x = pldist(nStart, varargin)
%% Parse command line for parameters
infimum = 1;
supremum = 10^(ceil(log10(nStart)) + 1);
slope = 1.5;
lambda = .025;
distType = 'non-truncated';
plotFlag = false;

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'infimum'
                infimum = varargin{iVarArg+1};
                iVarArg = iVarArg + 2;
            case 'supremum'
                supremum = varargin{iVarArg+1};
                iVarArg = iVarArg + 2;
            case 'slope'
                slope = varargin{iVarArg+1};
                iVarArg = iVarArg + 2;
            case 'lambda'
                lambda = varargin{iVarArg+1};
                iVarArg = iVarArg + 2;
            case 'upper'
                distType = 'truncated above';
                xmax = varargin{iVarArg+1};
                iVarArg = iVarArg + 2;
            case 'lower'
                distType = 'truncated below';
                xmin = varargin{iVarArg+1};
                iVarArg = iVarArg + 2;
            case 'double'
                distType = 'double truncated';
                xmin = varargin{iVarArg+1};
                xmax = varargin{iVarArg+2};
                iVarArg = iVarArg + 3;
            case 'plot'
                plotFlag = true;
                iVarArg = iVarArg + 1;
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(PLDIST) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
end

%% Make probability density function for distribution
switch distType
    case 'non-truncated'
        pdf = round(nStart * (infimum:supremum).^(-slope));
        
    case 'truncated above'
        assert(xmax < supremum, ['xmax must be strictly less than supremum.',...
            'Increase number of starting points or choose a smaller xmax.'])
        
        coeff1 = nStart;
        coeff2 = nStart * (xmax^(-slope) / exp(-lambda * xmax));
        
        pdf = round([coeff1 * (infimum:xmax).^(-slope),...
            coeff2 * exp(-lambda * ((xmax+1):supremum))]);
        
    case 'truncated below'
        assert(xmin > infimum, ['xmin must be strictly greater than infimum.',...
            'Choose a larger xmin.'])
        
        coeff1 = nStart * (xmin^(-slope) / exp(-lambda * xmin));
        coeff2 = nStart;
        
        pdf = round([coeff1 * exp(-lambda * (infimum:(xmin-1))),...
            coeff2 * (xmin:supremum).^(-slope)]);
        
    case 'double truncated'
        assert(xmin > infimum, ['xmin must be strictly greater than infimum.',...
            'Choose a larger xmin.'])
        assert(xmax < supremum, ['xmax must be strictly less than supremum.',...
            'Increase number of starting points or choose a smaller xmax.'])
        
        coeff1 = nStart * (xmin^(-slope) / exp(-lambda * xmin));
        coeff2 = nStart;
        coeff3 = nStart * (xmax^(-slope) / exp(-lambda * xmax));
        
        pdf = round([coeff1 * exp(-lambda * (infimum:(xmin-1))),...
            coeff2 * (xmin:xmax).^(-slope),...
            coeff3 * exp(-lambda * ((xmax+1):supremum))]);
end

%% Generate data and plot if indicated
x = rldecode(pdf, infimum:supremum);

if plotFlag
    plplottool(x);
end