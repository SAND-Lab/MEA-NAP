%% AVPROPVALS - avalanche property values
% High level macro that returns the values associated with an avalanche 
% property. The function handles size and duration data stored in a cell
% array by overlaying plots onto a single figure, however this feature is
% incompatible with size given duration data stored in a cell array.
%
% Syntax: [tau, xmin, xmax, sigmaTau, p, pCrit, ks, PlotData] = ...
%               avpropvals(Avalanche, property, varargin)
%
% Inputs:
%   Avalanche (vector double or cell array) - avalanche property, size,
%     duration, or size given duration. Size and duration distributions can
%     either be input as a vector double or cell array. Size given duration
%     distribution must be input as a cell array with the size distribution
%     in the first cell and the duration distribution in the second.
%   property (string) - specifies for which avalanche property to 
%     compute the associated values. Options: 'size', 'duration', or
%     'sizgivdur' (average size given duration).
%
% Variable Inputs:
%   (..., 'plot') - plots property distribution
%   (..., 'save') - saves plot of property distribution. If not used in
%     conjunction with 'plot', the function suppresses the visual output.
%   (..., 'plot title', plotTitle) - specifics a plot title (string)
%   (..., 'save title', saveTitle) - specifices a save title (string)
%   (..., 'xlabel', xLabel) - specifies a particular x-axis label (string)
%   (..., 'ylabel', yLabel) - specifies a particular y-axis label (string)
%   (..., 'samples', nSamples) - the number of sample distributions to draw.
%     Sets the resolution of the p-value (scalar double) (default: 500)
%   (..., 'threshold', pCrit) - for computational efficiency, a critical
%     p-value can be used to halt the computation if the likelihood of a
%     successful trial (given by the binomial distribution) drops below a
%     pre-determined likelihood value. If pCrit is set to 1, the 
%     computation will execute in full. Note: this only affects the greedy
%     search process; final p-value is computed in full (scalar double) 
%     (default: .2)
%   (..., 'likelihood', likelihood) - likelihood threshold for binomial
%     process (scalar double) (default: 10^(-3))
%   (..., 'durmin', durMin) - sets duration minimum at durMin for weighted
%     least squares estimate of 1/(sigma nu z) (scalar double)
%   (..., 'durmax', durMax) - sets duration maximum at durMax for weighted
%     least squares estimate of 1/(sigma nu z) (scalar double)
%
% Outputs:
%   tau (cell array) - slope of power law region
%   xmin (cell array) - lower truncation of distribution
%   xmax (cell array) - upper truncation of distribution
%   sigmaTau (cell array) - error of the tau original fit estimated 
%     using the samples drawn from the model fit. If p is small, this error
%     is not valid.
%   p (cell array) - proportion of sample distributions with KS
%     statistics larger than the KS statistic between the empirical pdf and
%     the model distribution. p is bounded by 0 and 1. A p-value of 1 
%     indicates that the KS statistic between the empirical pdf and the 
%     model was smaller than the KS statistic between the sample 
%     distributions and the model. Conversely, a p-value of 0 indicates 
%     that KS(simulated) > KS(empirical) for every sample.
%   pCrit (cell array) - critical p-value used to truncate computation
%   ks (scalar double) - Kolmogorov-Smirnov statistic between the 
%     empirical pdf and the model
%   PlotData (structure) - contains the organized plotted results that can 
%       be used for other, more specialized plotting applications. Fields 
%       include:
%           PlotData.x: An nData by 1 cell array. Each element is a 2 by 
%               number of data points double array. The top row is the x 
%               value and the bottom row is the corresponding y value.
%           PlotData.fit: An nFits by 1 cell array. Each element is a 2 by
%               number of data points double array. The top row is the x
%               value and the bottom row is the corresponding y value.
%
% Example:
%   raster = randi([0 1], [3 10]);
%   asdf2 = rastertoasdf2(raster, 1, 'organotypic', 'LFP', '2014-01-01-OrgSet1');
%   Av = avprops(asdf2);
%   [tau, xmin, xmax, sigma, p, pCrit] = avpropvals(Av.size, 'size')
%     % compute all statistics for size distribution
%   [snzi, xmin, xmax] = avpropvals({Av.size, Av.duration}, 'sizgivdur')
%     % compute all statistics for size given duration distribution
%
% Other m-files required: PLPARAMS, PLPLOT, PLMLE, PVCALC, MYMNRND, SIZEGIVDURWLS
% Subfunctions: PLPARAMS, PLPLOT, SIZEGIVDURWLS
% MAT-files required: none
%
% See also: PLMLE, PVCALC, PLPARAMS, PLPLOT, SIZEGIVDURWLS, MYMNRND

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% June 2013; Last revision: 11-Aug-2014

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

function [tau, xmin, xmax, sigmaTau, p, pCrit, ks, PlotData] = avpropvals(avProp, property, varargin)
%% Set presets based on property
switch property
    case 'size'
        plotTitle = 'Size Distribution';
        saveTitle = 'SizeDist'; 
        xLabel = 'Neurons fired, s';
        yLabel = 'p(s)';
        expTag = 's';
    case 'duration'
        plotTitle = 'Duration Distribution';
        saveTitle = 'DurDist'; 
        yLabel = 'p(T)';
        xLabel = 'Duration, T (bins)'; 
        expTag = 'T';
    case 'sizgivdur'
        plotTitle = 'Average Size Given Duration Distribution';
        saveTitle = 'SizeGivDurDist';
        yLabel = 'Average # neurons fired <s>(t,T)';
        xLabel = 'Duration, T (bins)';
        
        durMin = min(avProp{2});
        durMax = max(avProp{2});
    otherwise
        error('Invalid property string')
end

%% Parse command line for parameters
plotFlag = false;
saveFlag = false;
nSamples = 500;
pCritIn = .2;
likelihood = 10^(-3);

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    switch varargin{iVarArg}
        case 'plot',       plotFlag = true;
        case 'save',       saveFlag = true;
        case 'plot title', plotTitle = varargin{iVarArg+1};  iVarArg = iVarArg+1;
        case 'save title', saveTitle = varargin{iVarArg+1};  iVarArg = iVarArg+1;
        case 'xlabel',     xLabel = varargin{iVarArg+1};     iVarArg = iVarArg+1;
        case 'ylabel',     yLabel = varargin{iVarArg+1};     iVarArg = iVarArg+1;
        case 'samples',    nSamples = varargin{iVarArg+1}; iVarArg = iVarArg+1;
        case 'threshold',  pCritIn = varargin{iVarArg+1}; iVarArg = iVarArg+1;
        case 'likelihood', likelihood = varargin{iVarArg+1}; iVarArg = iVarArg+1;
        case 'durmin',     durMin = varargin{iVarArg+1}; iVarArg = iVarArg+1;
        case 'durmax',     durMax = varargin{iVarArg+1}; iVarArg = iVarArg+1;
        otherwise
            iVarArg = iVarArg+1;
    end
    if ~argOkay
        disp(['(AVPROPVALS) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg+1;
end

%% Process data
if ~iscell(avProp)
    % convert data to a single cell arrays to streamline the function
    avProp = {avProp};
%else
%    assert(strcmp(property, 'size') || strcmp(property, 'duration'),...
%        'size given duration data must be in vector double format');
end

nCells = length(avProp);

tau = cell(nCells,1);
xmin = cell(nCells,1);
xmax = cell(nCells,1);
sigmaTau = cell(nCells,1);
p = cell(nCells,1);
pCrit = cell(nCells,1);
ks = cell(nCells,1);
PlotData = NaN;

%% Compute property distribution and plot results
if strcmp(property,'size') || strcmp(property,'duration')
    
    for iCell = 1:nCells
        [tau{iCell}, xmin{iCell}, xmax{iCell}, sigmaTau{iCell}, p{iCell}, pCrit{iCell}, ks{iCell}] =...
            plparams(avProp{iCell}, 'samples', nSamples, 'threshold', pCritIn,...
            'likelihood', likelihood);
    end
    
    % terminate function if neither plotting nor saving results
    if ~plotFlag && ~saveFlag
        return;
    end
    
    % otherwise, plot property distribution
    fitParams = struct;
    fitParams.tau = zeros([nCells,1]);
    fitParams.xmin = zeros([nCells,1]);
    fitParams.xmax = zeros([nCells,1]);
    for i = 1:nCells
        fitParams.tau(i) = tau{i};
        fitParams.xmin(i) = xmin{i};
        fitParams.xmax(i) = xmax{i};
    end
    fitParams.x2fit = (1:nCells)';
    PlotData = plplottool(avProp,'fitParams',fitParams);
    
    fh = figure(get(0,'CurrentFigure'));
            
    title(plotTitle, 'fontsize', 14)
    xlabel(xLabel, 'fontsize', 14)
    ylabel(yLabel, 'fontsize', 14)
    
    if nCells == 1
        unqProps = numel(unique(avProp{1}));
        
        xLoc = 10^(floor(log10(unqProps)));
        yLoc = 10^-1;
        
        text(xLoc, yLoc, [expTag,'^{-',num2str(tau{1}),'}'],'FontSize',14)
        
    end
else
    % weighted least squares estimate of 1/(sigma nu z)
    if ~plotFlag && ~saveFlag
        [tau, sigmaTau] = sizegivdurwls(avProp{1}, avProp{2},...
            'durmin', durMin, 'durmax', durMax);
    else
        [tau, sigmaTau] = sizegivdurwls(avProp{1}, avProp{2},...
            'durmin', durMin, 'durmax', durMax, 'plot');
        
        fh = figure(get(0,'CurrentFigure'));
    end
    
    p = [];
    pCrit = [];
end

if saveFlag
    saveas(fh,saveTitle)
    if ~plotFlag, set(fh,'visible','off'); end
end