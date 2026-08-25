%% DEMOEMPDATA - analyzing empirical data
% Demonstrates the features of the T_AvStat toolbox for extracting and
% analyzing neuronal avalanches from empirical data. 

% Other m-files required: REBIN, AVPROPS, AVPROPVALS, AVGSHAPES, 
%   AVSHAPECOLLAPSE, AVSHAPECOLLAPSESTD, PLPARAMS, PLPLOT, PLMLE, MYMNRND, 
%   SIZEGIVDURWLS, PVCALC
% Subfunctions: REBIN, AVPROPS, AVPROPVALS, AVGSHAPES, AVSHAPECOLLAPSE,
%               AVSHAPECOLLAPSESTD
% MAT-files required: sample_data
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

%% Load and process sample data

load sample_data

% Compute all avalanche properties
Av = avprops(asdf2, 'ratio', 'fingerprint');

%% Plot histogram of branching ratios

minBR = min(Av.branchingRatio);
maxBR = max(Av.branchingRatio);

nEdges = 25;

edges = minBR:((maxBR-minBR)/(nEdges - 1)):maxBR;

BRhist = histc(Av.branchingRatio, edges);

plot(edges, BRhist);

title('Histogram of Avalanche Branching Ratios', 'fontsize', 14)
xlabel('Branching Ratio (s_{t+1} / s_t)', 'fontsize', 14)
ylabel('Frequency of Occurrence', 'fontsize', 14)

%% Compute power-law parameters using macro

% size distribution (SZ)
[tau, xminSZ, xmaxSZ, sigmaSZ, pSZ, pCritSZ, ksDR, DataSZ] =...
    avpropvals(Av.size, 'size', 'plot');

% size distribution (SZ) with cutoffs
UniqSizes = unique(Av.size);
Occurances = hist(Av.size,UniqSizes);
AllowedSizes = UniqSizes(Occurances >= 20);
AllowedSizes(AllowedSizes < 4) = [];
LimSize = Av.size(ismember(Av.size,AllowedSizes));
[tau, xminSZ, xmaxSZ, sigmaSZ, pSZ, pCritSZ, DataSZ] =...
    avpropvals(LimSize, 'size', 'plot');

% duration distribution (DR)
[alpha, xminDR, xmaxDR, sigmaDR, pDR, pCritDR, ksDR, DataDR] =...
    avpropvals(Av.duration, 'duration', 'plot');

% size given duration distribution (SD)
[sigmaNuZInvSD, waste, waste, sigmaSD] = avpropvals({Av.size, Av.duration},...
    'sizgivdur', 'durmin', xminDR{1}, 'durmax', xmaxDR{1}, 'plot');

%% Perform avalanche shape collapse for all shapes

% compute average temporal profiles
avgProfiles = avgshapes(Av.shape, Av.duration, 'cutoffs', 4, 20);

% plot all profiles
figure;
for iProfile = 1:length(avgProfiles)
    hold on
    plot(1:length(avgProfiles{iProfile}), avgProfiles{iProfile});
end
hold off

xlabel('Time Bin, t', 'fontsize', 14)
ylabel('Neurons Active, s(t)', 'fontsize', 14)
title('Mean Temporal Profiles', 'fontsize', 14)

% compute shape collapse statistics (SC) and plot
[sigmaNuZInvSC, secondDrv, range, errors] = avshapecollapse(avgProfiles, 'plot');

sigmaSC = avshapecollapsestd(avgProfiles);

title(['Avalanche Shape Collapse', char(10), '1/(sigma nu z) = ',...
    num2str(sigmaNuZInvSC), ' +/- ', num2str(sigmaSC)], 'fontsize', 14)