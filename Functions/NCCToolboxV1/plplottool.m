%% PLPLOTTOOL - visualizes power-law distributed data.
% Plot the probability distribution of input data on a log-log scale with
% functionality designed specifically for power-law or power-law like data.
% The function also outputs data prepared for plotting for use in other
% functions. The functional also allows the user to overlay multiple
% power-law fits and allows for the input of multiple data sets.
%
% Syntax: [Data] = plplot(x, varargin)
%
% Inputs:
%   x (vector double or cell array) - data that we would like to plot. If a
%       cell array is passed to the function, each element should be a
%       vector double list that contains data for each set to be plotted.
%       Call the number of data sets nData.
%
% Variable Inputs:
%   (..., 'plotParams', plotParams) - provides information about fits to be
%       plotted (structure). Optional arguments to the fields of the
%       structure are:
%           plotParams.color: An nData by 3 double array that specifies the
%               color of each plot in standard RGB format (default: 
%               plotParams.color = jet(nData)).
%           plotParams.linewidth: A double that sets the line width of the
%               plots (default: plotParams.linewidth = 1).
%           plotParams.linestyle: A string that sets the line style of the
%               plots (default: plotParams.linestyle = '-').
%           plotParams.dot: A string that sets whether to use filled
%               circular dots of color matching the line ('on' or 'off',
%               default: plotParams.dot = 'off').
%           plotParams.dotsize: A double that sets the size of the circular
%               dots, it they are on (default: plotParams.dotsize = 5).
%   (..., 'fitParams', fitParams) - provides information about fits to be
%       plotted. Fits are plotted on top of data. Arguments to the fields
%       of the structure are:
%           fitParams.tau: A number of fits (nFits) by 1 double array. Each
%               element contains the exponent of the power-law fit such
%               that p(x) = x^(-tau). Note: this is a required field to
%               plot a fit.
%           fitParams.x2fit: An nFits by 1 double vector that identifies
%               the x data to which the fit will be applied (default: all 
%               fits are applied to the first data set in x). Note, the
%               continuous or discrete nature of the fit will match the
%               data to which it is being applied. 
%           fitParams.color: An nFits by 3 double array that specifies the
%               color of each fit in standard RGB format (default: for
%               nData < 5 - red, green, blue, black, and for nData >= 5 -
%               fitParams.color = jet(nData)).
%           fitParams.linewidth: A double that sets the line width of the
%               fits (default: fitParams.linewidth = 1).
%           fitParams.linestyle: A string that sets the line style of the
%               fits (default: fitParams.linestyle = '--').
%           fitParams.dot: A string that sets whether to use filled
%               circular dots of color matching the line ('on' or 'off',
%               default: fitParams.dot = 'off').
%           fitParams.dotsize: A double that sets the size of the circular
%               dots, it they are on (default: fitParams.dotsize = 5).
%           fitParams.xmin: An nFits by 1 double vector that sets the
%               minimum x value for the fit (default: minimum of the
%               corresponding x data set by fitParams.x2fit).
%           fitParams.xmax: An nFits by 1 double vector that sets the
%               maximum x value for the fit (default: maximum of the
%               corresponding x data set by fitParams.x2fit).
%   (..., 'uniqueBins', uniqueBins) - sets the nature of the bins (string,
%       default: 'on'). uniqueBins = 'on' uses unique bins to plot the
%       probability of a given data value, while uniqueBins = 'off' uses
%       logarithmically spaced bins. Note, only discrete data can be
%       plotted with unique bins.
%   (..., 'binDensity', binDensity) - double that sets the number of
%       logarithmically spaced bins per order of magnitude (default:
%       binDensity = 50). If uniqueBins = 'on', then binDensity will have
%       no effect.
%   (..., 'plot', plotStatus) - string the determines if the plot will be
%       shown (default: 'on'). The plot can be suppressed if the user is
%       primarily using plplottool to reorganize data for later plotting.
%   (..., 'title',titleString) - string to be shown as the title to the
%       plot (default: '').
%
% Outputs:
%   Data (structure) - contains the organized plotted results that can be
%       used for other, more specialized plotting applications. Fields 
%       include:
%           Data.x: An nData by 1 cell array. Each element is a 2 by number
%               of data points double array. The top row is the x value and
%               the bottom row is the corresponding y value.
%           Data.fit: An nFits by 1 cell array. Each element is a 2 by
%               number of data points double array. The top row is the x
%               value and the bottom row is the corresponding y value.
%
% Examples:
%   x = pldist(10^4);
%     % generates perfectly non-truncated power-law distributed data with
%     % slope of 1.5
%   tau = plmle(x);
%     % computes tau by MLE for x
%   data = plplottool(x);
%     % plot the data
%   fitParams = struct; fitParams.tau = tau; fitParams.color = [1,0,0];
%   plotParams = struct; plotParams.dot = 'on';
%   data = plplottool(x,'plotParams',plotParams,'fitParams',fitParams);
%   
%   See demoplotting for numerous other examples
%
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: demoplotting

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% April 2016

%==============================================================================
% Copyright (c) 2016, The Trustees of Indiana University
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

function [data] = plplottool(x, varargin)
%% Organize inputs

% Set defaults and get basic parameters
if ~iscell(x)
    x = {x};
end
xmin = cellfun(@min, x);
xmax = cellfun(@max, x);
nData = length(x);
binDensity = 50;
uniqueBins = 'on';
plotStatus = 'on';
titleString = '';
plotParams = struct;
if nData < 5
    plotParams.color = [0,0,0;1,0,0;0,1,0;0,0,1];
else
    plotParams.color = jet(nData);
end
plotParams.linewidth = 1;
plotParams.linestyle = '-';
plotParams.dot = 'off';
plotParams.dotsize = 5;
fitParams = struct;
fitParams.tau = [];
fitParams.color = [1,0,0;0,1,0;0,0,1;0,0,0];
fitParams.linewidth = 1;
fitParams.linestyle = '--';
fitParams.dot = 'off';
fitParams.dotsize = 5;
fitParams.x2fit = ones([1000,1]);


% Parse command line for plot type
iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'uniqueBins',       uniqueBins = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
            case 'binDensity',       binDensity = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
            case 'fitParams',        newfitParams = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
            case 'plotParams',       newplotParams = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
            case 'plot',             plotStatus = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
            case 'title',            titleString = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(PLPLOTTOOL) Ignoring invalid argument #' num2str(iVarArg + 1)]);
    end
    iVarArg = iVarArg + 1;
end

% Put the new plot parameters in the structure
if exist('newplotParams','var') == 1
    if isfield(newplotParams,'color')
        plotParams.color = newplotParams.color;
    end
    if isfield(newplotParams,'linewidth')
        plotParams.linewidth = newplotParams.linewidth;
    end
    if isfield(newplotParams,'linestyle')
        plotParams.linestyle = newplotParams.linestyle;
    end
    if isfield(newplotParams,'dot')
        plotParams.dot = newplotParams.dot;
    end
    if isfield(newplotParams,'dotsize')
        plotParams.dotsize = newplotParams.dotsize;
    end
end

% Put the new fit parameters in the structure
if exist('newfitParams','var') == 1
    fitParams.tau = newfitParams.tau;
    if isfield(newfitParams,'color')
        fitParams.color = newfitParams.color;
    end
    if isfield(newfitParams,'linewidth')
        fitParams.linewidth = newfitParams.linewidth;
    end
    if isfield(newfitParams,'linestyle')
        fitParams.linestyle = newfitParams.linestyle;
    end
    if isfield(newfitParams,'dot')
        fitParams.dot = newfitParams.dot;
    end
    if isfield(newfitParams,'dotsize')
        fitParams.dotsize = newfitParams.dotsize;
    end
    if isfield(newfitParams,'x2fit')
        fitParams.x2fit = newfitParams.x2fit;
    end
    if isfield(newfitParams,'xmin')
        fitParams.xmin = newfitParams.xmin;
    end
    if isfield(newfitParams,'xmax')
        fitParams.xmax = newfitParams.xmax;
    end
end

%% Plot the data

if strcmp(plotStatus,'on')
    figure
    hold on
end

data = struct;
data.x = cell([nData,1]);
fitParams.round = cell([nData,1]);
AllxBounds = cell([nData,2]);

for iData = 1:nData
    
    x{iData} = reshape(x{iData},[1,numel(x{iData})]);
    
    if nnz(abs(x{iData} - round(x{iData})) > 3*eps) > 0
        
        % The data are continuous, so use logarithmically spaced bins
        xEdges = log10(xmin(iData)):(1/binDensity):(log10(xmax(iData)) + (1/binDensity));
        xCenters = xEdges + 0.5*(1/binDensity);
        xEdges = 10.^xEdges;
        xCenters = 10.^xCenters;
        
        % Record that this was continuous data
        fitParams.round{iData} = 'cont';
        
    else
        
        % The data are discrete, so use logarithmically spaced bins or
        % unique bins
        if strcmp(uniqueBins,'off')
            
            % Use logarithmically spaced bins
            xEdges = log10(xmin(iData)):(1/binDensity):(log10(xmax(iData)) + (1/binDensity));
            xCenters = xEdges + 0.5*(1/binDensity);
            xEdges = 10.^xEdges;
            xCenters = 10.^xCenters;
            
            % Record that this was continuous data
            fitParams.round{iData} = 'cont';
            
        elseif strcmp(uniqueBins,'on')
            
            % Round off any precisions errors
            x{iData} = round(x{iData});
            
            % Use unique bins
            xEdges = unique(x{iData});
            xCenters = xEdges;
            
            % Record that this was discrete data
            fitParams.round{iData} = 'disc';
            
        end
    end
    
    % Bin the data
    y = histc(x{iData},xEdges);
    
    % Convert to probability
    y = y./length(x{iData});
    
    % Record the edges and the centers for fitting
    AllxBounds{iData,1} = xEdges;
    AllxBounds{iData,2} = xCenters;
    
    % If the binning was logarithmic, we probably need to cut off the last
    % point and remove some empty bins
    xCenters(y == 0) = [];
    y(y == 0) = [];
    
    % Plot
    if strcmp(plotStatus,'on')
        if strcmp(plotParams.dot,'off')
            plot(xCenters,y,...
                'Color',plotParams.color(iData,:),...
                'LineWidth',plotParams.linewidth,...
                'LineStyle',plotParams.linestyle)
        elseif strcmp(plotParams.dot,'on')
            plot(xCenters,y,...
                'Color',plotParams.color(iData,:),...
                'LineWidth',plotParams.linewidth,...
                'LineStyle',plotParams.linestyle,...
                'Marker','o',...
                'MarkerSize',plotParams.dotsize,...
                'MarkerEdgeColor','none',...
                'MarkerFaceColor',plotParams.color(iData,:))
        end
    end
    
    % Put the data in the right place
    data.x{iData} = [xCenters;y];

    
    
end



%% Plot the fits

% Update the fit params
nFits = length(fitParams.tau);
if (nFits > 4) && (size(fitParams.color,1) == 4)
    fitParams.color = jet(nFits);
end
if ~isfield(fitParams,'xmin')
    fitParams.xmin = zeros([nFits,1]);
    for iFit = 1:nFits
        fitParams.xmin(iFit) = min(x{fitParams.x2fit(iFit)});
    end
end
if ~isfield(fitParams,'xmax')
    fitParams.xmax = zeros([nFits,1]);
    for iFit = 1:nFits
        fitParams.xmax(iFit) = max(x{fitParams.x2fit(iFit)});
    end
end

% Make the fits
data.fit = cell([nFits,1]);
for iFit = 1:nFits
    
    % Calculate the normalization factor, the x coordinates of the fit,
    % and the limits for continuous fits
    if strcmp(fitParams.round{fitParams.x2fit(iFit)},'disc') % Discrete
        
        Norm1 = nnz((x{fitParams.x2fit(iFit)} >= fitParams.xmin(iFit)) ...
            & (x{fitParams.x2fit(iFit)} <= fitParams.xmax(iFit))) / length(x{fitParams.x2fit(iFit)});
        xFit = fitParams.xmin(iFit):fitParams.xmax(iFit);
        yFit = xFit.^(-fitParams.tau(iFit));
        
    elseif strcmp(fitParams.round{fitParams.x2fit(iFit)},'cont') % Continuous
        
        xStart = find(AllxBounds{fitParams.x2fit(iFit),1} >= fitParams.xmin(iFit),1,'first');
        xEnd = find(AllxBounds{fitParams.x2fit(iFit),1} > fitParams.xmax(iFit),1,'first');
        Norm1 = nnz((x{fitParams.x2fit(iFit)} >= AllxBounds{fitParams.x2fit(iFit),1}(xStart)) ...
            & (x{fitParams.x2fit(iFit)} <= AllxBounds{fitParams.x2fit(iFit),1}(xEnd))) / length(x{fitParams.x2fit(iFit)});
        xFit = AllxBounds{fitParams.x2fit(iFit),2}(xStart:(xEnd - 1));
        uLim = AllxBounds{fitParams.x2fit(iFit),1}((xStart + 1):xEnd);
        lLim = AllxBounds{fitParams.x2fit(iFit),1}(xStart:(xEnd - 1));
        
        if fitParams.tau(iFit) ~= 1
            yFit = (1/(1 - fitParams.tau(iFit)))*((uLim.^(1 - fitParams.tau(iFit))) - (lLim.^(1 - fitParams.tau(iFit))));
        else
            yFit = log(uLim./lLim);
        end
        
    end
    
    % Limit the fit to the same data points as were used in the data plot
    yFit(~ismember(xFit,data.x{fitParams.x2fit(iFit)}(1,:))) = [];
    xFit(~ismember(xFit,data.x{fitParams.x2fit(iFit)}(1,:))) = [];
    
    % Normalize the fit
    yFit = yFit.*(Norm1/sum(yFit));
    
    % Plot
    if strcmp(plotStatus,'on')
        if strcmp(fitParams.dot,'off')
            plot(xFit,yFit,...
                'Color',fitParams.color(iFit,:),...
                'LineWidth',fitParams.linewidth,...
                'LineStyle',fitParams.linestyle)
        elseif strcmp(fitParams.dot,'on')
            plot(xFit,yFit,...
                'Color',fitParams.color(iFit,:),...
                'LineWidth',fitParams.linewidth,...
                'LineStyle',fitParams.linestyle,...
                'Marker','o',...
                'MarkerSize',fitParams.dotsize,...
                'MarkerEdgeColor','none',...
                'MarkerFaceColor',fitParams.color(iFit,:))
        end
    end
    
    % Put the fit in the right place
    data.fit{iFit} = [xFit;yFit];
    
    
end


%% Add other features

if strcmp(plotStatus,'on')
    % Add a legend
    LegText = cell([nData + nFits,1]);
    for iData = 1:nData
        LegText{iData} = ['Data ',num2str(iData)];
    end
    for iFit = 1:nFits
        LegText{iFit + nData} = ['Fit ',num2str(iFit)];
    end
    legend(LegText)
    
    % Add axis labels
    xlabel('x')
    ylabel('p(x)')
    
    % Add a title, if necessary
    if ~strcmp(titleString,'')
        title(titleString)
    end
    
    % Convert to log-log
    set(gca,'XScale','log')
    set(gca,'YScale','log')
    
end


end