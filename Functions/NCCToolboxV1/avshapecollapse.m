%% AVSHAPECOLLAPSE - performs avalanche shape collapse
% Automatically determines scaling parameter 1/(sigma nu z) by computing
% the variance between all possible shape collapses for a range of possible
% exponent values using a set of average temporal profiles. The process
% involves a multi-step refinement of the range of values which optimizes
% computation time without sacrificing accuracy.
%
% Syntax: [sigmaNuZInv, secondDrv, range, errors, figName] = 
%             avshapecollapse(avgProfiles, varargin)
%
% Input:
%   avgShapes (cell array) - array of mean temporal profiles (vector double)
%
% Variable Inputs:
%   (..., 'precision', precision) - sets the decimal precision for the
%     parameter search precision (power of ten scalar double) (default: 
%     10^-3)
%   (..., 'bounds', bounds) - sets the bounds on the initial range of
%     exponent values (vector double) (default: [0 4])
%   (..., 'interpPoints',ninterpPoints) - sets the number of interpolation
%     points used in calculating the shape collapse error (scalar double)
%     (default: 10^3)
%   (..., 'plot') - plots avalanche shape collapse
%   (..., 'save') - saves plot title. If used without the 'plot' argument,
%     the figure output is suppressed.
%   (..., 'plot title', plotTitle) - uses custom plot title (string)
%   (..., 'save title', saveTitle) - uses custom save title (string)
%
% Outputs:
%   sigmaNuZInv (scalar double) - 1/(sigma nu z) estimate
%   secondDrv (scalar double) - second derivative of the mean of all scaled
%     temporal profiles, used to assess the curvature of the scaling
%     function onto which the shapes are collapsed
%   range (cell array) - array containing all tested scaling exponents
%     (vector double)
%   errors (cell array) - array containing all variance-based error values
%     for each tested shape collapse
%   coeffs (double array) - fit coefficients for a quadratic fit of the
%     shape collapse
%   figName (string) - name of saved figure (empty by default)
%
% Examples:
%   raster = randi([0 1], [10 1000]);
%   asdf2 = rastertoasdf2(raster, 1);
%   Av = avprops(asdf2, 'duration', 'shape');
%   avgProfiles = avgshapes(Av.shape, Av.duration, 'cutoffs', 5, 50);
%     % computes average shapes for durations greater than 5 and for 
%       avalanches whose durations occur at least 50 times.
%   [sigmaNuZInv, secondDrv, range, errors] = avshapecollapse(avgProfiles)
%     % computes all statistics without visualizing results
%   sigmaNuZInv = avshapecollapse(avgProfiles, 'precision', 10^-4)
%     % computes 1/(sigma nu z) to 4 decimal points
%   [sigmaNuZInv,~,~,~,figName] = avshapecollapse(avgProfiles, 'plot', 'save')
%     % computes 1/(sigma nu z), plots and saves collapses with generic
%       titles, and returns generic save name
%   avshapecollapse(avgProfiles, 'save', 'save title', 'TestShapeCollapse');
%     % saves collapse with custom title without visualizing result
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%
% See also: AVPROPS, AVGSHAPES

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% June 2013; Last revision: 11-September-2015

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

function [sigmaNuZInv, secondDrv, range, errors, coeffs, figName] = avshapecollapse(avgShapes, varargin)
%% Parse command line for variable arguments
precision = 10^-3;
bounds = [0 4];
ninterpPoints = 10^3;
saveFlag = false;
plotFlag = false;
saveTitle = 'AvShapeCollapse';
plotTitle = 'Avalanche Shape Collapse';

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'precision'
                precision = varargin{iVarArg+1};
            case 'plot'
                plotFlag = true;
            case 'save'
                saveFlag = true;
            case 'bounds'
                bounds = varargin{iVarArg+1};
                iVarArg = iVarArg+1;
            case 'interpPoints'
                ninterpPoints = varargin{iVarArg+1};
                iVarArg = iVarArg+1;
            case 'plot title'
                plotTitle = varargin{iVarArg+1};
                iVarArg = iVarArg+1;
            case 'save title'
                saveTitle = varargin{iVarArg+1};
                iVarArg = iVarArg+1;
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(AVSHAPECOLLAPSE) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Scale durations by duration length (t/T)
nAvs = length(avgShapes);
scaledDurs = cell(nAvs,1);
avgShapeDurs = cell(nAvs,1);

for iScaledDur = 1:length(scaledDurs)
    thisAvgShapeDur = length(avgShapes{iScaledDur});
    
    scaledDurs{iScaledDur} = (1:thisAvgShapeDur) / thisAvgShapeDur;
    
    avgShapeDurs{iScaledDur} = thisAvgShapeDur;
end

%% Continually refine exponent value range to find optimal 1/(sigma nu z)
nIterations = -log10(precision);
if nIterations ~= round(nIterations)
    error('precision must be a power of ten')
end

errors = cell(nIterations,1); 
range = cell(nIterations,1);

for iIteration = 1:nIterations
    range{iIteration} = bounds(1):10^(-iIteration):bounds(2);
    
    % scale shapes by T^{1 - 1/(sigma nu z)}
    nExponents = length(range{iIteration});
    
    % replicate average profile durations and range into matrices
    avgShapeDursMat = repmat(avgShapeDurs, 1, nExponents);
    rangeMat = repmat(num2cell(range{iIteration}), nAvs, 1);
    
    % compute scaling (vectorized): T^{1 - 1/(sigma nu z)}
    scaling = num2cell(cellfun(@(T, snzi) T.^(1 - snzi),...
        avgShapeDursMat, rangeMat));
    
    % scale shapes by scaling factor: s(t/T) * T^{1 - 1/(sigma nu z)}
    avgShapesMat = repmat(avgShapes, 1, nExponents);
    scaledShapes = cellfun(@times, avgShapesMat, scaling,...
        'UniformOutput', false);
    
    % interpolate shapes to match maximum duration length
    scaledShapes = cellfun(@(x) interp1(linspace(0,1,length(x)),x,linspace(0,1,ninterpPoints)),...
        scaledShapes, 'UniformOutput', false); 
    
    nScaledShapes = size(scaledShapes, 1);
    nTimeSteps = size(scaledShapes, 2);
    
    scaledShapes = cellfun(@cell2mat,...
        mat2cell(scaledShapes, nScaledShapes, ones(1, nTimeSteps)),...
        'UniformOutput', false);
    
    % compute error of all shape collapses
    errors{iIteration} = cellfun(@(x) mean(var(x))/((max(max(x)) - min(min(x)))^2), scaledShapes);
    
    % find exponent value that minimizes error
    bestIndx = find(errors{iIteration} == min(errors{iIteration}), 1);
    sigmaNuZInv = range{iIteration}(bestIndx);
    
    % generate new range of exponents to finer precision
    if iIteration < nIterations
        bounds = [(sigmaNuZInv - 10^(1-iIteration)) (sigmaNuZInv + 10^(1-iIteration))];
    end
end

%% Fit to 2nd degree polynomial and find second derivative
bestIndx = find(errors{end} == min(errors{end}), 1);
avgScaledShape = mean(scaledShapes{bestIndx}, 1);

coeffs = polyfit(linspace(0,1,ninterpPoints), avgScaledShape, 2);
secondDrv = coeffs(1) * 2;

%% Plot and save
if plotFlag || saveFlag
    Handle.figure = figure;
    Handle.legend = zeros(2,1);
    
    % plot all shapes
    for i = 1:length(scaledDurs)
        Handle.legend(1) = ...
            plot(linspace(0,1,ninterpPoints), scaledShapes{bestIndx}(i,:));
        hold on
    end
    
    % overlay polynomial fit
    Handle.legend(2) = plot(linspace(0,1,ninterpPoints), coeffs(1) * linspace(0,1,ninterpPoints).^2 + ...
        coeffs(2) * linspace(0,1,ninterpPoints) + coeffs(3), '-r', 'LineWidth', 3);
    
    % label axes
    xlabel('Scaled Avalanche Duration (t/T)', 'fontsize', 14)
    ylabel('Scaled Avalanche Shapes', 'fontsize', 14)
    
    % set title and legend
    title(plotTitle, 'fontsize', 14)
    legend(Handle.legend, 'scaled shape', 'polynomial fit')
    
    % hide figure if required
    if ~plotFlag
        figName = [saveTitle, '.fig'];
        saveas(figure, figName)
        set(figure, 'visible', 'off');
    else
        figName = [];
    end
end