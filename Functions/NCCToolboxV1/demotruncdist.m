%% DEMOTRUNCDIST - fitting truncated power-law distributions
% Demonstrates the features of the T_AvStats toolbox for handling power-law
% distributed data with or without a lower and/or upper truncation point 
% using simulated data.

% Other m-files required: PLDIST, RLDECODE, PLMLE, PVCALC, MYMNRND, 
% Subfunctions: PLDIST, PLMLE, PVCALC
% MAT-files required: none
%
% See also: PLPLOT

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% July 2014; Last revision: 5-Oct-2014

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

%% Make simulated power-law distributed data
% Note, variables will make use of the following suffixes:
% NT: non-truncated
% UT: upper-truncated
% LT: lower-truncated
% DT: doubly-truncated

slopeNT = 1.25;
slopeUT = 1.5;  xmaxUT = 50;
slopeLT = 1.75; xminLT = 10;
slopeDT = 2;    xminDT = 10; xmaxDT = 60;

xNT = pldist(10^4, 'slope', slopeNT);               
xUT = pldist(10^4, 'upper', xmaxUT, 'slope', slopeUT);  
xLT = pldist(10^4, 'lower', xminLT, 'slope', slopeLT);  
xDT = pldist(10^5, 'double', xminDT, xmaxDT, 'slope', slopeDT);

%% Estimate slope of power-law distibuted region for known ranges with error

tauNT = plmle(xNT);
[waste, waste, tauNTstd] = pvcalc(xNT, tauNT);

tauUT = plmle(xUT, 'xmax', xmaxUT);
[waste, waste, tauUTstd] = pvcalc(xUT, tauUT, 'xmax', xmaxUT);

tauLT = plmle(xLT, 'xmin', xminLT);
[waste, waste, tauLTstd] = pvcalc(xLT, tauLT, 'xmin', xminLT);

tauDT = plmle(xDT, 'xmin', xminDT, 'xmax', xmaxDT);
[waste, waste, tauDTstd] = pvcalc(xDT, tauDT, 'xmin', xminDT, 'xmax', xmaxDT);

% print results
MLEresults = {'distribution type', 'tau', 'MLE(tau)', 'std(tau)';
    'non-truncated', slopeNT, tauNT, tauNTstd;
    'upper-truncated', slopeUT, tauUT, tauUTstd;
    'lower-truncated', slopeLT, tauLT, tauLTstd;
    'doubly-truncated', slopeDT, tauDT, tauDTstd};

disp(MLEresults)

%% Compute p-value for doubly-truncated distribution with and without cutoff

pFitted = pvcalc(xDT, tauDT, 'xmin', xminDT, 'xmax', xmaxDT);

pFull = pvcalc(xDT, plmle(xDT));

fprintf(['p-value for the fitted doubly truncated distribution: %g.\n', ...
    'p-value for the full doubly truncated distribution: %g.\n'],...
    pFitted, pFull)