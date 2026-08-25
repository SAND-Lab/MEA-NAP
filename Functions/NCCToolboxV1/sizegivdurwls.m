%% SIZEGIVDURWLS - size given duration weighted least squares
% Computes the average size given duration for avalanche data and performs
% the weighted least squares fit to determine the scaling parameter and
% its standard deviation.
%
% Syntax: [sigmaNuZInv, sigmaNuZInvStd, logCoeff] =
%           sizegivdurwls(sizes, durations, varargin)
%
% Inputs:
%   sizes (vector double) - avalanche sizes
%   durations (vector double) - avalanche durations
%
% Variable Inputs:
%   (..., 'durmin', durMin) - sets duration minimum at durMin (scalar
%     double)
%   (..., 'durmax', durMax) - sets duration maximum at durMax (scalar
%     double)
%   (..., 'plot') - visualizes results
%
% Outputs:
%   sigmaNuZInv (scalar double) - 1/(sigma nu z) estimate from average size
%     given duration WLS fit
%   sigmaNuZInvStd (scalar double) - standard deviation on 1/(sigma nu z)
%     estimate from WLS fit
%   logCoeff - logarithm of scaling coefficient for the fit
%
% Example:
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: AVPROPS, AVPROPVALS

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% May 2014; Last revision: 14-July-2014

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

function [sigmaNuZInv, sigmaNuZInvStd, logCoeff] = sizegivdurwls(sizes, durations, varargin)
%% Parse command line for variable inputs
durMin = min(durations);
durMax = max(durations);
plotFlag = false;

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'durmin',  durMin = max([durMin,varargin{iVarArg+1}]);
            case 'durmax',  durMax = min([durMax,varargin{iVarArg+1}]);
            case 'plot',    plotFlag = true;
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(SIZEGIVDURWLS) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end



%% Process data

% find unique durations
unqDurations = unique(durations);
nUnqDurs = length(unqDurations);

% make histogram of duration values
durHist = histc(durations, unqDurations);

% calculate average size given durations
sizeGivDur = zeros(1, nUnqDurs);

for iUnqDur = 1:nUnqDurs
    sizeGivDur(iUnqDur) = mean(sizes(durations == unqDurations(iUnqDur)));
end

% remove NaN values
sizeGivDur = sizeGivDur(isfinite(sizeGivDur));

%% Prepare data

% Logarithmically transform unique durations and average sizes
logUnqDurs = log10(unqDurations)'; 
logSizeGivDur = log10(sizeGivDur)';

% find minimum and maximum duration histogram indices
durMinInd = find(unqDurations == durMin);
durMaxInd = find(unqDurations == durMax);

% create the design matrix for least squares
X = [logUnqDurs(durMinInd:durMaxInd), ones([durMaxInd - durMinInd + 1,1])];

%% Perform the weighted least squares fit
[B,S] = lscov(X, logSizeGivDur(durMinInd:durMaxInd), ...
    durHist(durMinInd:durMaxInd));

% extract parameter values
sigmaNuZInv = B(1);
logCoeff = B(2);
sigmaNuZInvStd = S(1);

% convert 1/(sigma nu z) standard deviation to string
sigmaNuZInvStdStr = num2str(sigmaNuZInvStd);

% determine shorter string length, 1/(sigma nu z) estimate or standard dev.
minStrLen = min(length(num2str(sigmaNuZInv)), length(sigmaNuZInvStdStr));

% trim 1/(sigma nu z) standard deviation to minimum string length
sigmaNuZInvStdStr = sigmaNuZInvStdStr(1:minStrLen);


%% Plot (optional)

if plotFlag
    
    % calculate scaling coefficient for the fit
    coeff = 10^logCoeff;
    
    figure; hold on
    
    scatter(unqDurations,sizeGivDur,20,'r','filled');
    plot(unqDurations(durMinInd:durMaxInd),...
        coeff*(unqDurations(durMinInd:durMaxInd).^sigmaNuZInv), 'k');
    
    set(gca, 'xscale', 'log');
    set(gca, 'yscale', 'log');
    
    % get x- and y-positions for fit information text
    xPos = 10^(ceil(log10(min(durations)))+1);
    yPos = 10^(ceil(log10(sizeGivDur(find(unqDurations >= durMin, 1)))));
    
    text(xPos, yPos, ['T^{',num2str(sigmaNuZInv),'}'],...
        'FontSize', 14);
    
    % set axes labels and plot title
    xLabel = 'Duration, T (bins)';
    yLabel = 'Average # of Neurons Fired, <s>(t,T)';
    plotTitle = ['Average Size Given Duration', char(10),...
        '1/(sigma nu z) = ', num2str(sigmaNuZInv), ' +/- ',sigmaNuZInvStdStr,...
        char(10),'(', num2str(durMin), '<= d <=', num2str(durMax),' )'];
    
    xlabel(xLabel, 'fontsize', 14)
    ylabel(yLabel, 'fontsize', 14)    
    title(plotTitle, 'fontsize', 14)
end

