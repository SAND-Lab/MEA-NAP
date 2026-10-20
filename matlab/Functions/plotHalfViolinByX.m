function plotHalfViolinByX(compiledData, eMeti, eMetl, X, lagIdx,  Params, figureHandle)
%HALFVIOLINPLOTBYX Make half-violin by X, where X is either group or DIV
%  eMeti : str 
%         name of the network metric, eg. 'ND' 
%  eMetl : str 
%         label of the network metric, eg. 'Node Degree'
%  X     : str 
%         either 'group' to make plot by group 
%             or 'DIV' to make plot by DIV


AgeDiv = Params.DivNm;

% specify colours to use on the basis of the number of time points
nDIV = length(Params.DivNm);
divColorMap = flipud(viridis(nDIV)); 

if isempty(Params.customGrpOrder)
    Grps = Params.GrpNm;
else
    if ~isempty(Params.customGrpOrder)
        Grps = Params.customGrpOrder;
    else
        Grps = Params.GrpNm;
    end 
end 

if strcmp(X, 'group')
   subPlotIterator = Grps;
   withinPlotIterator = AgeDiv;
   xt = 1:length(AgeDiv);
   xlabelText = 'Age';
elseif strcmp(X, 'DIV')
   subPlotIterator = AgeDiv; 
   withinPlotIterator = Grps;
   xt = 1:length(Grps);
   xlabelText = 'Group';
end


for subPlotIdx = 1:length(subPlotIterator)
    figureHandle(subPlotIdx) = subplot(1,length(subPlotIterator),subPlotIdx);
    
    for withinPlotIdx = 1:length(withinPlotIterator)
        
        if strcmp(X, 'group')
            eGrp = cell2mat(Grps(subPlotIdx));
            eDiv = strcat('TP',num2str(withinPlotIdx));
            withinPlotColor = divColorMap(withinPlotIdx, :);
            xtlabtext{withinPlotIdx} = num2str(AgeDiv(withinPlotIdx));
            titleTxt = eGrp;
        elseif strcmp(X, 'DIV')
            eGrp = cell2mat(Grps(withinPlotIdx));
            eDiv = strcat('TP',num2str(subPlotIdx));
            withinPlotColor = Params.groupColors(withinPlotIdx, :);
            xtlabtext{withinPlotIdx} = eGrp;
            titleTxt = ['Age ', num2str(AgeDiv(subPlotIdx))];
        end
        
        DatTemp = compiledData.(eGrp).(eDiv).(eMeti);

        % Make zero vector of DIV is empty 
        if isempty(DatTemp)
            DatTemp = zeros(1, length(Params.FuncConLagval));
        end 

        PlotDat = DatTemp(:, lagIdx);
        PlotDat(isnan(PlotDat)) = [];
        PlotDat(~isfinite(PlotDat)) = [];
        
        if isempty(PlotDat)
            continue
        else
            HalfViolinPlot(PlotDat, xt(withinPlotIdx), withinPlotColor, ...
                           Params.kdeHeight, Params.kdeWidthForOnePoint)
        end
        clear DatTemp ValMean ValStd UpperStd LowerStd
    end
    xticks(xt)
    xticklabels(xtlabtext)
    xlabel(xlabelText)
    ylabel(eMetl)
    title(titleTxt)
    aesthetics
    set(gca,'TickDir','out');
end
linkaxes(figureHandle,'xy')

figureHandle(1).XLim = [min(xt)-0.5 max(xt)+0.5];
set(findall(gcf,'-property','FontSize'),'FontSize',9)

% Set custom y axis 
if isfield(Params.networkLevelNetMetCustomBounds, eMeti) 

    boundVector = Params.networkLevelNetMetCustomBounds.(eMeti);

    if ~isnan(boundVector(1))
        yLowerBound = boundVector(1);
    else
        yLowerBound = figureHandle(1).YLim(1);
    end 

    if ~isnan(boundVector(2))
        yUpperBound = boundVector(2);
    else
        yUpperBound = figureHandle(1).YLim(2);
    end  

else 
    yLowerBound = figureHandle(1).YLim(1);
    yUpperBound = figureHandle(1).YLim(2);
end 

ylim([yLowerBound, yUpperBound])
set(findall(gcf,'-property','FontSize'),'FontSize',9)


end

