%% MYMNRND - custom-made multinomial random number generator
% Custom version of the MatLab program mnrnd. 
%
% Syntax: y = mymnrnd(n,p)
%
% Inputs:
%   n (scalar double) - number of trials for each multinomial outcome
%     (a.k.a. sample size)
%   p (vector double) - 1-by-K vector of multinomial probabilities, where K
%     is the number of multinomial bins or categories. p must sum to 1. K
%     must be greater than 1.
%
% Output:
%   y (vector double) - 1-by-K vector containing the counts for each of the
%     K multinomial bins
%
% Example:
%   y = mymnrnd(10^3, [.2, .3, .5])
%
% Other m-files required: none
% Subfunctions: poissrnd, normrnd, binornd
% MAT-files required: none
%
% See also: BENTPL, PLPLOT, PLPARAMS

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% September 2012; Last revision: 24-October-2014

%==============================================================================
% Copyright (c) 2012, The Trustees of Indiana University
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

function y = mymnrnd(n,p)
%%
% constants for the threshold between Poisson and normal approximations
coeff = [-1.060102688009665, -0.781485955904560];

%% Process and pre-allocate data

% number of multinomial bins or categories
k = length(p);

% rank the probabilities
[sortedp, idx] = sort(p);
[unused, unsortidx] = sort(idx);

y = zeros(size(p));

%% Draw the random numbers

% Set initial values
iSmProb = 1;
iBgProb = k;
nTemp = n;
renormFactor = 1;

for i = 1:(k-1)
    if nTemp >= 1000 % use Poisson or Gaussian approximations
        
        % calculate the threshold between Poisson and normal distribution
        threshold = (2^coeff(2)) * nTemp^(coeff(1)/log2(10));
        
        if ((sortedp(iBgProb)/renormFactor) >= threshold) && ...
                ((sortedp(iBgProb)/renormFactor) <= (1-threshold))
            
            % use a normal distribution to approximate the largest p            
            y(iBgProb) =...
                round(normrnd(nTemp * sortedp(iBgProb) / renormFactor, ...
                sqrt(nTemp * (sortedp(iBgProb)/renormFactor) * (1 - (sortedp(iBgProb)/renormFactor)))));
            
            % recalculate nTemp
            nTemp = nTemp - y(iBgProb);
            
            % adjust the renormalization factor
            renormFactor = renormFactor - sortedp(iBgProb); 
            
            % adjust the index for the highest prob
            iBgProb = iBgProb - 1;
            
        else % use a poisson distribution to approximate the smallest p
            
            y(iSmProb) = poissrnd(nTemp * sortedp(iSmProb) / renormFactor);          
            
            % recalculate NTemp
            nTemp = nTemp - y(iSmProb); 
            
            % adjust the renormalization factor
            renormFactor = renormFactor - sortedp(iSmProb); 
            
            % adjust the index for the lowest prob
            iSmProb = iSmProb + 1;
            
        end
    elseif nTemp < 1000 % use binomial random number generator
        
        y(iSmProb) = binornd(nTemp,sortedp(iSmProb) / renormFactor);
        
        % recalculate NTemp
        nTemp = nTemp - y(iSmProb);
        
        % adjust the renormalization factor
        renormFactor = renormFactor - sortedp(iSmProb); 

        % adjust the index for the lowest prob
        iSmProb = iSmProb + 1;
        
    end
end

% fill in the last random number
y(iSmProb) = nTemp;

% reorder the counts
y = y(unsortidx);


end

