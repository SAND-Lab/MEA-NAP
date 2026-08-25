%% GENDATA - generates random data
% Generates random, integer data drawn from a specified probability 
% distribution using the multinomial distribution. Capable of generating
% continuous data using the inverse transformation method [Devroye, 1986].
% In all cases, the random numbers are greater than or equal to 1.
%
% Syntax: [x, xVals, pdf] = gendata(N, distribution, varargin)
%
% Inputs:
%   N (scalar double) - number of data points
%   distribution (cell array) - distribution name and parameters
%     Format: {'distribution_name', [parameters]}
%     Options:
%       {'exponential', lambda} 
%       {'lognormal', [mu, sigma]} Note: continuous distribution not yet
%         available
%       {'powerlaw', tau}
%       {'truncated_powerlaw', [tau, lambda, xmin, xmax]} Note: continuous
%         distribution not yet available
%       {'exp_powerlaw', [tau, lambda]} Note: continuous distribution not
%         yet available for this distribution
%     Note: the truncated powerlaw option generates a powerlaw distribution
%     truncated by an exponential. Setting xmin > infimum, xmax < supremum,
%     or both determines if the distribution is truncated above, below, or
%     both. Infimum and supremum set as optional parameters.
%
% Variable Inputs:
%   (..., 'continuous') - returns continuous data
%   (..., 'inf', infimum) - smallest integer value drawn from distribution
%       for discrete data [default: 1]
%   (..., 'sup', supremum) - largest integer value drawn from distribution
%       for discrete data [default: 100]
%   (..., 'xmin', xmin) - smallest continuous value drawn from the 
%       distribution for continuous powerlaw [default: 1]
%   (..., 'xmax', xmax) - largest continuous value drawn from the
%       distribution for continuous powerlaw [default: inf]
%
%
% Output:
%   x (vector double) - random data
%   xVals (vector double) - x values of sampled pdf
%   pdf (vector double) - probability density function from which the data
%     are drawn
%
% Examples:
%   x = gendata(10000, {'powerlaw', 1.5});
%       % Generate 10000 samples from a discrete power-law with exponent
%       % 1.5
%   x = gendata(1000, {'truncated_powerlaw', [2, 0.125, 10, 50]});
%       % Generate 1000 samples from a truncated power-law with exponent 2
%       % between for 10 <= x <= 50, and exponential decay with constant
%       % equal to 0.125 otherwise
%
%
% Other m-files required: mymnrnd
% Subfunctions: none
% MAT-files required: none
%
% See also: plplottool

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% May 2013

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


function [x, xVals, pdf] = gendata(N, distribution, varargin)
%% Parse command line for plot type

dataType = 'INT';
infimum = 1;
supremum = 100;
xmin = 1;
xmax = inf;


iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'continuous',       dataType = 'CONT';
            case 'inf',           infimum = varargin{iVarArg+1};
            case 'sup',           supremum = varargin{iVarArg+1};
            case 'xmin',           xmin = varargin{iVarArg+1};
            case 'xmax',           xmax = varargin{iVarArg+1};
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(GENDATA) Ignoring invalid argument #' num2str(iVarArg)]);
    end
    iVarArg = iVarArg + 1;
end

%% Integer Data

if strcmp(dataType, 'INT')
    xVals = infimum:supremum;
    nX = length(xVals);
    
    switch distribution{1}
        case 'exponential'
            lambda = distribution{2};
            pdf = exp(-lambda * xVals);
            
        case 'lognormal'
            mu = distribution{2}(1);
            sigma = distribution{2}(2);
            
            pdf = 1./xVals .* exp(-(log(xVals) - mu).^2 / (2 * sigma^2));
            
        case 'powerlaw'
            tau = distribution{2};
            pdf = xVals.^(-tau);
            
        case 'truncated_powerlaw'
            tau = distribution{2}(1);
            lambda = distribution{2}(2);
            xmin = distribution{2}(3);
            xmax = distribution{2}(4);
            
            pdf = zeros(1, nX);
            
            distHead = infimum:(xmin-1);
            for i = 1:length(distHead)
                xi = distHead(i);
                pdf(xi) = (xmin^(-tau) / exp(-lambda * xmin)) * exp(-lambda * xi);
            end
            
            distBody = xmin:xmax;
            for i = 1:length(distBody)
                xi = distBody(i);
                pdf(xi) = xi^(-tau);
            end
            
            distTail = (xmax+1):supremum;
            for i = 1:length(distTail)
                xi = distTail(i);
                pdf(xi) = (xmax^(-tau) / exp(-lambda * xmax)) * exp(-lambda * xi);
            end
        case 'exp_powerlaw'
            tau = distribution{2}(1);
            lambda = distribution{2}(2);
            pdf = exp(-lambda * xVals).*(xVals.^(-tau));
    end
    
    % normalize pdf and get counts
    pdf = pdf./sum(pdf);
    counts = mymnrnd(N, pdf);
    
    % make data
    x = zeros(N,1);    
    idx = 1;
    for xi = 1:nX
        for jCount = 1:counts(xi)
            x(idx) = xVals(xi);
            idx = idx + 1;
        end
    end
end

%% Continuous Data

if strcmp(dataType, 'CONT')
        % random, uniformly distributed data
        u = rand(N, 1);
        
        switch distribution{1}
            case 'exponential'
                
                lambda = distribution{2};
                
                % Calculate the adjustment to limit outputs to greater than
                % or equal to 1
                a = 1 - exp(-lambda);
                u = (1 - a)*u + a;
                x = -(1/lambda) * log(1 - u);
                
            case 'lognormal'
                
                error('Continuous lognormal distribution not currently available')
                
            case 'powerlaw'
                
                tau = distribution{2};
                
                if tau <= 1
                    error('tau must be greater than 1')
                end
                
                % Calculate adjustments to limit the range of generated
                % values
                a = 1 - xmin^(1 - tau);
                b = 1 - xmax^(1 - tau);
                u = (b - a)*u + a;
                
                x = exp(log(1 - u)./(1 - tau));
                
            case 'truncated_powerlaw'
               
                error('Continuous truncated powerlaw distribution not currently available')
                
            case 'exp_powerlaw'
                
                error('Continuous exponentially modified distribution not currently available')
                
        end
end