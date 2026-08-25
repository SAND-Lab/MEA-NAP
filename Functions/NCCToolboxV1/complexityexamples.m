%% Complexity Examples
% Generates simple chain model data to demonstrate the complexity measure
% and then plots the results. This demo does not utilize the complexity
% function included in this toolbox because that function is designed to
% work only with sampled data. This demonstration script uses a precisely
% defined model. The figure produced by this script matches the Neural
% Complexity figure in the manuscript, though the precise spike rasters
% will change because they are randomly generated.
%

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% July 2015; Last revision: 27-Jan-2016

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


%% Set Parameters

% Set the number of variables (please make it even and 4 <= nVar <= 12)
nVar = 12;

% Set the coupling strengths to use (0 to 1)
c = [0,0.8,1];
nc = length(c);

% Set the number of example states to draw for the example spike rasters
nSamples = 50;

% Note, figure parameters are set later in the script

%% Generate the Model Data

Comp = zeros([1,nc]);
ps = cell([1,nc]);
ICurves = cell([1,nc]);

for ic = 1:nc
    
    % Build the conditional probability multiplier
    condprob = [0.5 + 0.5*c(ic),0.5 - 0.5*c(ic);0.5 - 0.5*c(ic),0.5 + 0.5*c(ic)];
    
    % Build the joint probability tensors
    p = cell([nVar,1]);
    p{1} = [0.5;0.5];
    p{2} = condprob.*p{1}(:,[1,1]);
    for iVar = 3:nVar
        p{iVar} = repmat(reshape(condprob,[ones([1,iVar - 2]),2,2]),[2*ones([1,iVar - 2]),1,1]).*repmat(p{iVar - 1},[ones([1,iVar - 1]),2]);
    end
    
    pSteps = p;
    p = p{end};
    
    % Calculate the entropies, integration curve, and complexity
    
    H = cell([nVar,1]);
    
    for iVar = 1:nVar
        SubSets = nchoosek(1:nVar,iVar);
        Temp = zeros([size(SubSets,1),size(SubSets,2) + 1]);
        Temp(:,1:size(SubSets,2)) = SubSets;
        for iSubSet = 1:size(SubSets,1)
            Out = setdiff(1:nVar,SubSets(iSubSet,:));
            pTemp = p;
            for iOut = 1:length(Out)
                pTemp = sum(pTemp,Out(iOut));
            end
            pTemp = pTemp(:);
            HTemp = -pTemp .* log2(pTemp);
            HTemp(~isfinite(HTemp)) = 0;
            Temp(iSubSet,end) = sum(HTemp);
        end
        H{iVar} = Temp;
    end
    
    % Calculate the integration curves
    
    ICurve = zeros([1,nVar]);
    
    for iVar = 1:nVar
        NormFactor = 1/size(H{iVar},1);
        ITemp = 0;
        for iSubSet = 1:size(H{iVar},1)
            ITemp = ITemp - NormFactor*H{iVar}(iSubSet,end);
            for jVar = 1:nVar
                if ismember(jVar,H{iVar}(iSubSet,1:(end - 1)))
                    ITemp = ITemp + NormFactor*H{1}(iVar,end);
                end
            end
        end
        ICurve(iVar) = ITemp;
    end
    
    Comp(ic) = sum(((0:(nVar - 1))./(nVar - 1))*ICurve(nVar) - ICurve) / nVar;
    ps{ic} = p;
    ICurves{ic} = ICurve;
end

% Correct for rounding errors
Comp(Comp < (100*eps)) = 0;


% Make some spike rasters
Samples = zeros([nVar,nSamples,nc]);
for ic = 1:nc
    
    pConv = cumsum(ps{ic}(:));
    iSample = 1;
    while iSample <= nSamples
        
        State = nnz(rand > pConv) + 1;
        Subs = cell(1,nVar);
        [Subs{:}] = ind2sub(size(ps{ic}),State);
        if (rem(iSample,2) == 1) && (Subs{1} == 2)           
            Samples(:,iSample,ic) = cell2mat(Subs);
            iSample = iSample + 1;
        elseif (rem(iSample,2) == 0) && (Subs{1} == 1)
            Samples(:,iSample,ic) = cell2mat(Subs);
            iSample = iSample + 1;
        end
    end
end

% Get some necessary parameters for plotting
MaxIntCurve = 0;
for ic = 1:nc
    MaxIntCurve = max([MaxIntCurve,max(ICurves{ic})]);
end




%% Make the Figure

% Set parameters for the figure

% Set the side margins in inches
lmargin = 0.4;
rmargin = 0.1;

% Set the top and bottom margins in inches
tmargin = 0.3;
bmargin = 1.5;

% Set the horizontal distance between plots in inches
hspace = 0.45;

% Set the vertical distance between plots in inches
vspace = 0.5;

% Set the horizontal width of the information curve subfigures and the
% complexity bar graphs.
widthIC = 1.2;
widthCB = 0.75;

% Set Paper size
papersize = [6 5];

% calculate the width and height based on dimensions above in inches
width = papersize(1) - lmargin - rmargin - 3*hspace - widthIC - widthCB;
height = (papersize(2) - tmargin - bmargin - 2*vspace)/3;

LeftCoord = [lmargin,lmargin + width + hspace,lmargin + width + 2*hspace + widthIC,lmargin + width + 3*hspace + widthIC + widthCB];
BottomCoord = (0:2)*(height + vspace) + bmargin;
BottomCoord = fliplr(BottomCoord);

% Convert to fraction of page sizes
LeftCoord = LeftCoord/papersize(1);
BottomCoord = BottomCoord/papersize(2);
width = width/papersize(1);
widthIC = widthIC/papersize(1);
widthCB = widthCB/papersize(1);
height = height/papersize(2);


% Make the figure
F1 = figure('PaperPosition',[0 0 papersize],'PaperSize',papersize);
set(gcf, 'PaperUnits', 'inches');

% Set the line widths
ThinLW = 1.2;
MedLW = 1.5;

% Set fontsizes
LegFS = 6;
TitleFS = 8;
AxLabelFS = 7;
UnitFS = 5;

% Set the colors
PColor = {[0,0,0],[1,0,0],[0,125/255,255/255],[238/255,130/255,238/255]};





% Make the Figure

for iFig = 1:nc
    
    % First, plot the raster
    f = subplot('Position',[LeftCoord(1),BottomCoord(iFig),width,height]);
    hold on
    
    [iBox,jBox] = find(squeeze(Samples(:,:,iFig)) == 1);
    for iSpike = 1:length(iBox)
        xFill = jBox(iSpike) + [-0.5,0.5,0.5,-0.5];
        yFill = iBox(iSpike) + [-0.5,-0.5,0.5,0.5];
        fill(xFill,yFill,PColor{1},'EdgeColor','none')
    end
    
    xlim([0.5,size(Samples,2) + 0.5]);
    ylim([0.5,size(Samples,1) + 0.5]);
    
    xlabel('Example State','FontSize',AxLabelFS)
    ylabel('Neuron','FontSize',AxLabelFS)
    
    set(gca,'FontSize',UnitFS)
    
    if iFig == 1
        title('Random Data','FontSize',TitleFS)
    elseif iFig == 2
        title('Complex Data','FontSize',TitleFS)
    elseif iFig == 3
        title('Ordered Data','FontSize',TitleFS)
    end
    
    
    
    
    
    % Second, plot the integration curves
    f = subplot('Position',[LeftCoord(2),BottomCoord(iFig),widthIC,height]);
    hold on
    
    xFill = 1:nVar;
    yFill = ICurves{iFig};
    
    plot(1:nVar,ICurves{iFig},'Color',PColor{2},'LineWidth',MedLW)
    plot([1,nVar],[0,ICurves{iFig}(end)],'Color',PColor{3},'LineWidth',ThinLW,'LineStyle','--')
    
    xlim([1,nVar])
    ylim([0,1.1*MaxIntCurve])
    
    xlabel('Neuron','FontSize',AxLabelFS)
    ylabel('Integration (bits)','FontSize',AxLabelFS)
    title('Integration','FontSize',TitleFS)
    
    set(gca,'FontSize',UnitFS)
    set(gca,'Layer','Top')
    
    x1 = 1 + 0.08*(nVar - 1);
    x2 = 1 + 0.23*(nVar - 1);
    x3 = 1 + 0.26*(nVar - 1);
    
    line([x1,x2],[0.9*1.1*MaxIntCurve,0.9*1.1*MaxIntCurve],'Color',PColor{2},'LineWidth',MedLW)
    text(x3,0.9*1.1*MaxIntCurve,'Integration','FontSize',LegFS)
    
    line([x1,x2],[0.78*1.1*MaxIntCurve,0.78*1.1*MaxIntCurve],'Color',PColor{3},'LineWidth',ThinLW,'LineStyle','--')
    text(x3,0.78*1.1*MaxIntCurve,'Lin. Approx.','FontSize',LegFS)
    
    
    
    
    
    
    % Third, plot the complexity bar graph
    f = subplot('Position',[LeftCoord(3),BottomCoord(iFig),widthCB,height]);
    hold on
    
    if Comp(iFig) ~= 0
        xFill = [0.5,1.5,1.5,0.5];
        yFill = [0,0,Comp(iFig),Comp(iFig)];
        fill(xFill,yFill,PColor{4},'EdgeColor','none')
    else
        xFill = [0.5,1.5,1.5,0.5];
        % If the complexity is zero, make a small sliver of color at zero
        % to show that the complexity is plotted
        yFill = [0,0,0.02*max(Comp),0.02*max(Comp)];
        fill(xFill,yFill,PColor{4},'EdgeColor','none')
    end
    
    xlim([0,2])
    ylim([0,1.1*max(Comp)]);
    
    set(gca,'XTick',[])
    set(gca,'XTickLabel',[])
    
    ylabel('Complexity (bits/neuron)','FontSize',AxLabelFS)
    title('Complexity','FontSize',TitleFS)
    
    set(gca,'FontSize',UnitFS)
    set(gca,'Layer','Top')
    
end
