%% Complexity Demo
% Demonstrates features of the T_Complexity toolbox using real dissociated
% culture data. This script requires the full T_Complexity toolbox as well
% as sample_data.mat. The demo functions using the first 40 neurons in the
% recording to speed up the calculation.
%
% Given a raster $X$ with elements $x_i$,
%
% * Entropy: 
%   $$H(X) = -\sum_i p(x_i) * log(p(x_i))$$
% * Integration: 
%   $$I(X) = \sum_i H(x_i) - H(X)$$
% * Complexity: 
%   $$C_N(X) = \sum_k \left[ \left(\frac{k-1}{n-1}\right) I(X) - \left\langle X_k^j \right\rangle \right]$$
%
% where $X_k^j$ denotes the $k^{\textrm{th}}$ subset of size $j$.

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


%% Load and process ASDF2 data
load sample_data
X = asdf2toraster(asdf2);  % extract raster as sparse matrix
X = uint8(X);              % convert to unsigned 8-bit integer
X(:,sum(X,1) == 0) = [];   % utilize only the avalanches

%% Estimate the integrated information and complexity and plot results
nSubSets = 100;
[Cn,IntInfPart] = complexity(X,nSubSets);

figure
hold on
nNeurons = length(IntInfPart);
fill(1:nNeurons,IntInfPart,[0.5,0.5,0.5],'EdgeColor','none')
line([1,nNeurons],[0,IntInfPart(end)],'Color','r','LineWidth',2)
plot(1:nNeurons,IntInfPart,'Color','b','LineWidth',2)
xlabel('Neurons')
ylabel('Integrated Information')
title(['Neural Complexity for Sample Data', char(10),...
    'C_N(X) = ', num2str(Cn),' bits/neuron'])

%% Perform the complexity analysis with the subsampling correction
nSubSets = 100;
[Cn,IntInfPart] = complexity(X,nSubSets,'subsampcorrect');

figure
hold on
nNeurons = length(IntInfPart);
fill(1:nNeurons,IntInfPart,[0.5,0.5,0.5],'EdgeColor','none')
line([1,nNeurons],[0,IntInfPart(end)],'Color','r','LineWidth',2)
plot(1:nNeurons,IntInfPart,'Color','b','LineWidth',2)
xlabel('Neurons')
ylabel('Integrated Information')
title(['Neural Complexity for Sample Data (Subsampling Correction)', char(10),...
    'C_N(X) = ', num2str(Cn),' bits/neuron'])





