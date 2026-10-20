function plotGraphMetricsByLag(compiledData, eMeti, eMetl, Params)
%PLOTGRAPHMETRICSBYLAG Summary of this function goes here
%   Detailed explanation goes here

AgeDiv = Params.DivNm;

nDIV = length(Params.DivNm);
divColorMap = flipud(viridis(nDIV)); 
xt = 1:length(Params.FuncConLagval);


if isempty(Params.customGrpOrder)
    Grps = Params.GrpNm;
else
    Grps = Params.customGrpOrder;
end 

for l = 1:length(Params.FuncConLagval)
    LagValLabels{l} = num2str(Params.FuncConLagval(l));
end

for g = 1:length(Grps)
    h(g) = subplot(length(Grps),1,g);
    eGrp = cell2mat(Grps(g));
    for d = 1:length(AgeDiv)
        
        eDiv = strcat('TP',num2str(d));
        
        DatTemp = compiledData.(eGrp).(eDiv).(eMeti);

        if isempty(DatTemp)
            DatTemp = zeros(1, length(Params.FuncConLagval));
        end 

        ValMean = nanmean(DatTemp,1);

        if strcmp(Params.linePlotShadeMetric, 'sem')
            spreadVal = nanstd(DatTemp, 1) / sqrt(length(DatTemp));
        elseif strcmp(Params.linePlotShadeMetric, 'std')
            spreadVal = nanstd(DatTemp, 1);
        end 
        
        UpperStd = ValMean + spreadVal; % upper std or sem line
        LowerStd = ValMean - spreadVal; % lower std or sem line

        Xf =[xt,fliplr(xt)]; % create continuous x value array for plotting
        Yf =[UpperStd,fliplr(LowerStd)]; % create y values for out and then back

        h1 = fill(Xf, Yf, divColorMap(d, :), 'edgecolor','none'); 

        % Choose a number between 0 (invisible) and 1 (opaque) for facealpha.
        set(h1,'facealpha',0.3)
        hold on
        line(d) = plot(xt, ValMean, 'Color', divColorMap(d, :), 'LineWidth', 3);
        scatter(xt, ValMean, 'MarkerFaceColor', divColorMap(d, :));
        set(gca, 'box', 'off') % remove borders
        set(gcf,'color','w'); % white background
        set(gca, 'TickDir', 'out')
        xticks(xt)
        xticklabels(LagValLabels)
        xlabel('STTC lag (ms)')
        ylabel(eMetl)
        clear DatTemp ValMean UpperStd LowerStd
    end
    lgd = legend(line,string(num2str(AgeDiv)));
    lgd.Location = 'Northeastoutside';
    title(lgd, 'DIV')
    title(eGrp)
    aesthetics
    set(gca,'TickDir','out');
end
linkaxes(h,'xy')
h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
set(findall(gcf,'-property','FontSize'),'FontSize',8)

    
end

