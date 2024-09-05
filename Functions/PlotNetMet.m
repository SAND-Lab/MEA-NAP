function [] = PlotNetMet(ExpName, Params, experimentMatFileFolder, oneFigureHandle)
% Plot network metrics for MEA data
% 
% Parameters 
% ----------
% ExpName : cell array
%     cell array where each entry is the name of the recording to 
%     plot network metrics (file extension should NOT be included)
% Params : struct
%     structure object with key parameters for analysis, namely 
%     Params.output_spreadsheet_file_type : (str)
%         whether to output analysis results as excel spreadsheet (.xlsx), 
%         using 'excel' or comma-separated values (.csv) using 'csv'
%     Params.groupColors : (nGroup x 3 matrix)
%         RGB colors (scale from 0 to 1) to use for each group in plotting
% 
% Other dependicies 
%     this code goes through the folder
%     .../AnalysisPipeline/OutputDataXXXXXXX/ExperimentMatFiles
%     and reads through the data contained there, each mat file 
%     in there should contain the following variables
%     Ephys : (struct)
%     Info : (struct)
%     NetMet : (struct)
%     Params : (struct)
%     adjMS : (struct)
%     spikeTimes : (struct)
%     
% Returns
% -------
% 
% 
% Meaning of the variables: 
% 
% 
% cDiv1, cDiv2, ... : this is a 1 x 3 vector with the RGB values of the color to be used 
% 
% Implicit dependencies 
% NetMet (structure)
% 
% 
% author RCFeord July 2021
% edited by Tim Sit
% Update log 
% ---------------
% 2023-11-22: Cleaned up code comments (Tim Sit)
% Future features
% ----------------
% Some of the repeated plotting code will be simplified.
% Color scheme will be specified in advanced settings.

% specify output format (currently Params is loaded from the mat file, 
% so it will override the settings), may need to find a better way 
% to distinguish the two 
output_spreadsheet_file_type = Params.output_spreadsheet_file_type;

%% colours

% specify colours to use on the basis of the number of time points
nDIV = length(Params.DivNm);

divColorMap = flipud(viridis(nDIV)); 
if nDIV == 1
    cDiv1 = divColorMap(1, :);
else
    for ii = 1:nDIV
        eval(['cDiv' num2str(ii) '= divColorMap(' num2str(ii) ', :);']);
    end
end

%% groups and DIV for plotting 

if ~isempty(Params.customGrpOrder{:})
    Grps = Params.customGrpOrder;
else
    Grps = Params.GrpNm;
end 

AgeDiv = Params.DivNm;

%% Variable names

% list of metrics that are obtained at the network level
NetMetricsE = Params.networkLevelNetMetToPlot;

% list of metrics that are obtained at the electrode level
NetMetricsC = Params.unitLevelNetMetToPlot;

%% Import data from all experiments - whole experiment  

for g = 1:length(Grps)
    % create structure for each group
    VN1 = cell2mat(Grps(g));
    eval([VN1 '= [];']);
    
    % add substructure for each DIV range
    for d = 1:length(AgeDiv)
        VN2 = strcat('TP',num2str(d));
        
        % add variable name
        for e = 1:length(NetMetricsE)
            VN3 = cell2mat(NetMetricsE(e));
            eval([VN1 '.' VN2 '.' VN3 '= [];']);
            clear VN3
        end
        clear VN2
    end
    clear VN1
end

% allocate numbers to relevant matrices
for i = 1:length(ExpName)
     %  Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
     Exp = char(ExpName(i));

     % if previously used showOneFig, then this prevents saved oneFigure 
     % handle from showing up when loading the matlab variable
     if Params.showOneFig 
         % Make it so figure handle in oneFigure don't appear
         set(0, 'DefaultFigureVisible', 'off')
     end 
     
     % Search for any .mat file with the Exp str (regardless of date)
     ExpFPathSearchName = dir(fullfile(experimentMatFileFolder, [Exp, '*.mat'])).name;
     ExpFPath = fullfile(experimentMatFileFolder, ExpFPathSearchName);
     expFileData = load(ExpFPath);  
     % filepath contains Info structure
     
     if ~isfield(expFileData, 'NetMet')
         fprintf(sprintf('%s has no NetMet field, file idx %.f', Exp, i))
     end 

     for g = 1:length(Grps)
         if strcmp(cell2mat(Grps(g)),cell2mat(expFileData.Info.Grp))
             eGrp = cell2mat(Grps(g));
         end       
     end
     for d = 1:length(AgeDiv)
         if cell2mat(expFileData.Info.DIV) == AgeDiv(d)
             eDiv = strcat('TP',num2str(d));
         end    
     end
     for e = 1:length(NetMetricsE)
            eMet = cell2mat(NetMetricsE(e));
            for l = 1:length(Params.FuncConLagval)
                % VNs = strcat('NetMet.adjM',num2str(Params.FuncConLagval(l)),'mslag.',eMet);
                
                lagIndependentMets = {'effRank', 'num_nnmf_components', 'nComponentsRelNS'}; 
                if contains(eMet, lagIndependentMets)
                    firstLagField = sprintf('adjM%.fmslag', Params.FuncConLagval(1));
                    DatTemp(l) = expFileData.NetMet.(firstLagField).(eMet);
                else
                    DatTemp(l) = expFileData.NetMet.(strcat('adjM', num2str(Params.FuncConLagval(l)), 'mslag')).(eMet);
                end 
                % eval(['DatTemp(l) =' VNs ';']);
                clear VNs
            end
            VNe = strcat(eGrp,'.',eDiv,'.',eMet);
            eval([VNe '= [' VNe '; DatTemp];']);
            clear DatTemp
     end
     clear Info NetMet adjMs
end

%% Import data from all experiments - electrode-specific data 

for g = 1:length(Grps)
    % create structure for each group
    VN1 = cell2mat(Grps(g));

    % add substructure for each DIV range
    for d = 1:length(AgeDiv)
        VN2 = strcat('TP',num2str(d));
        
        % add variable name
        for e = 1:length(NetMetricsC)
            VN3 = cell2mat(NetMetricsC(e));
            eval([VN1 '.' VN2 '.' VN3 '= [];']);
            clear VN3
        end
        clear VN2
    end
    clear VN1
end

% allocate numbers to relevant matrices
for i = 1:length(ExpName)
     % Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
     Exp = char(ExpName(i));
     % if previously used showOneFig, then this prevents saved oneFigure 
     % handle from showing up when loading the matlab variable
     if Params.showOneFig 
         % Make it so figure handle in oneFigure don't appear
         set(0, 'DefaultFigureVisible', 'off')
     end 
     
     % Load exp data to get which group and DIV it is from
     % also load the netMet variable
     % ExpFpath = fullfile(experimentMatFileFolder, Exp);
     % Search for any .mat file with the Exp str (regardless of date)
     ExpFPathSearchName = dir(fullfile(experimentMatFileFolder, [Exp, '*.mat'])).name;
     ExpFpath = fullfile(experimentMatFileFolder, ExpFPathSearchName);
     expFileData = load(ExpFpath);

     for g = 1:length(Grps)
         if strcmp(cell2mat(Grps(g)),cell2mat(expFileData.Info.Grp))
             eGrp = cell2mat(Grps(g));
         end       
     end
     for d = 1:length(AgeDiv)
         if cell2mat(expFileData.Info.DIV) == AgeDiv(d)
             eDiv = strcat('TP',num2str(d));
         end    
     end
     for e = 1:length(NetMetricsC)
            eMet = cell2mat(NetMetricsC(e));
            for l = 1:length(Params.FuncConLagval)
                VNs = strcat('expFileData.NetMet.adjM',num2str(Params.FuncConLagval(l)),'mslag.',eMet);
                % DatTemp(l) = expFileData.NetMet.(strcat('adjM', num2str(Params.FuncConLagval(l)), 'mslag')).(eMet);
                eval(['DatTemp' num2str(l) '= ' VNs ';']);
                eval(['mL(l) = length(DatTemp' num2str(l) ');']);
                clear VNs
            end
            for l = 1:length(Params.FuncConLagval)
                eval(['DatTempT = DatTemp' num2str(l) ';']);
                if length(DatTempT) < max(mL)
                    DatTempT((length(DatTempT)+1):max(mL)) = nan;
                end
                DatTemp(:,l) = DatTempT;
            end
            VNe = strcat(eGrp,'.',eDiv,'.',eMet);
            eval([VNe '= [' VNe '; DatTemp];']);
            clear DatTemp
     end
     clear Info NetMet adjMs
end

clear DatTemp TempStr

%% GraphMetricsByLag plots

graphMetricByLagFolder = fullfile(Params.outputDataFolder, ... 
    strcat('OutputData',Params.Date), '4_NetworkActivity', ...
    '4B_GroupComparisons', '5_GraphMetricsByLag');

eMet = Params.networkLevelNetMetToPlot;
eMetl = Params.networkLevelNetMetLabels;

assert(length(eMet) == length(eMetl), 'ERROR: eMet and eMetl have different lengths')

for l = 1:length(Params.FuncConLagval)
    LagValLabels{l} = num2str(Params.FuncConLagval(l));
end

p = [100 100 1200 800]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

if Params.showOneFig
    if isgraphics(oneFigureHandle)
        set(oneFigureHandle, 'Position', p);
    else 
        oneFigureHandle = figure;
        set(oneFigureHandle, 'Position', p);
    end 
else
    figure
end 

for n = 1:length(eMet)
    if ~isfield(Params, 'oneFigure')
        F1 = figure;
    end 
    
    % Skip lag-independent eMets
    if ismember(eMet, Params.lagIndependentMets)
        continue
    end 

    eMeti = char(eMet(n));
    xt = 1:length(Params.FuncConLagval);
    for g = 1:length(Grps)
        h(g) = subplot(length(Grps),1,g);
        eGrp = cell2mat(Grps(g));
        for d = 1:length(AgeDiv)
            eval(['c = cDiv' num2str(d) ';']);
            eDiv = strcat('TP',num2str(d));
            VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
            eval(['DatTemp = ' VNe ';']);
            
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

            h1 = fill(Xf,Yf,c,'edgecolor','none'); 
            
            % Choose a number between 0 (invisible) and 1 (opaque) for facealpha.
            set(h1,'facealpha',0.3)
            hold on
            line(d) = plot(xt,ValMean,'Color',c,'LineWidth',3);
            set(gca, 'box', 'off') % remove borders
            set(gcf,'color','w'); % white background
            set(gca, 'TickDir', 'out')
            xticks(xt)
            xticklabels(LagValLabels)
            xlabel('STTC lag (ms)')
            ylabel(eMetl(n))
            clear DatTemp ValMean UpperStd LowerStd
        end
        lgd = legend(line,num2str(AgeDiv));
        lgd.Location = 'Northeastoutside';
        title(eGrp)
        aesthetics
        set(gca,'TickDir','out');
    end
    linkaxes(h,'xy')
    h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
    set(findall(gcf,'-property','FontSize'),'FontSize',8)

    % Export figure
    for nFigExt = 1:length(Params.figExt)
        figName = strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt});
        figPath = fullfile(graphMetricByLagFolder, figName);
        figPath = strrep(figPath, '>', 'greater than');
        figPath = strrep(figPath, '<', 'less than');
        saveas(gcf, figPath);
    end 

    % Close figure or clear the one shared figures
    if ~Params.showOneFig
        close(gcf)
    else
        set(0, 'CurrentFigure', oneFigureHandle);
        clf reset
    end 
end

%% notBoxPlots - plots by group
if Params.includeNotBoxPlots 
    networkNotBoxPlotFolder = fullfile(Params.outputDataFolder, ...
        strcat('OutputData',Params.Date), '4_NetworkActivity', ...
        '4B_GroupComparisons', '3_RecordingsByGroup', 'NotBoxPlots');

    eMet = Params.networkLevelNetMetToPlot;
    eMetl = Params.networkLevelNetMetLabels;

    p = [100 100 1300 600]; 
    set(0, 'DefaultFigurePosition', p)

    if Params.showOneFig
        set(oneFigureHandle, 'Position', p);
    end 

    for l = 1:length(Params.FuncConLagval)

        networkNotBoxPlotFolderPlusLag = fullfile(networkNotBoxPlotFolder, ...
            strcat(num2str(Params.FuncConLagval(l)),'mslag'));
        if ~isfolder(networkNotBoxPlotFolderPlusLag)
            mkdir(networkNotBoxPlotFolderPlusLag)
        end 

        for n = 1:length(eMet)
            if ~isfield(Params, 'oneFigure')
                F1 = figure;
            end 
            eMeti = char(eMet(n));
            xt = 1:0.5:1+(length(AgeDiv)-1)*0.5;
            for g = 1:length(Grps)
                h(g) = subplot(1,length(Grps),g);
                eGrp = cell2mat(Grps(g));
                for d = 1:length(AgeDiv)
                    eDiv = strcat('TP',num2str(d));
                    VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
                    eval(['DatTemp = ' VNe ';']);

                    % Make zero vector of DIV is empty 
                    if isempty(DatTemp)
                        DatTemp = zeros(1, length(Params.FuncConLagval));
                    end 


                    PlotDat = DatTemp(:,l);
                    eval(['notBoxPlotRF(PlotDat,xt(d),cDiv' num2str(d) ',12)']);
                    clear DatTemp ValMean UpperStd LowerStd
                    xtlabtext{d} = num2str(AgeDiv(d));
                end
                xticks(xt)
                xticklabels(xtlabtext)
                xlabel('Age')
                ylabel(eMetl(n))
                title(eGrp)
                aesthetics
                set(gca,'TickDir','out');
            end
            linkaxes(h,'xy')
            h(1).XLim = [min(xt)-0.5 max(xt)+0.5];

            % Set custom y axis 
            if isfield(Params.networkLevelNetMetCustomBounds, eMeti) 

                boundVector = Params.networkLevelNetMetCustomBounds.(eMeti);

                if ~isnan(boundVector(1))
                    yLowerBound = boundVector(1);
                else
                    yLowerBound = h(1).YLim(1);
                end 

                if ~isnan(boundVector(2))
                    yUpperBound = boundVector(2);
                else
                    yUpperBound = h(1).YLim(2);
                end  

            else 
                yLowerBound = h(1).YLim(1);
                yUpperBound = h(1).YLim(2);
            end 

            ylim([yLowerBound, yUpperBound])

            set(findall(gcf,'-property','FontSize'),'FontSize',9)

            % Export figure
            for nFigExt = 1:length(Params.figExt)
                figName = strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt});
                figPath = fullfile(networkNotBoxPlotFolderPlusLag, figName);
                saveas(gcf, figPath);
            end 

            % Close figure or clear the one shared figures
            if ~Params.showOneFig
                close(gcf)
            else
                set(0, 'CurrentFigure', oneFigureHandle);
                clf reset
            end 
        end
    end

end

%% halfViolinPlots - plots by group

halfViolinPlotByGroupFolder = fullfile(Params.outputDataFolder, ... 
    strcat('OutputData',Params.Date), '4_NetworkActivity', ...
    '4B_GroupComparisons', '3_RecordingsByGroup', 'HalfViolinPlots');

eMet = Params.networkLevelNetMetToPlot;
eMetl = Params.networkLevelNetMetLabels;

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

if Params.showOneFig
    set(oneFigureHandle, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    halfViolinPlotByGroupFolderPlusLag = fullfile(halfViolinPlotByGroupFolder, ...
        strcat(num2str(Params.FuncConLagval(l)),'mslag'));
    if ~isfolder(halfViolinPlotByGroupFolderPlusLag)
        mkdir(halfViolinPlotByGroupFolderPlusLag)
    end 

    for n = 1:length(eMet)
        if ~Params.showOneFig
            F1 = figure;
        end 
        eMeti = char(eMet(n));
        xt = 1:length(AgeDiv);
        for g = 1:length(Grps)
            h(g) = subplot(1,length(Grps),g);
            eGrp = cell2mat(Grps(g));
            for d = 1:length(AgeDiv)
                eDiv = strcat('TP',num2str(d));
                VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
                eval(['DatTemp = ' VNe ';']);
                
                % Make zero vector of DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                PlotDat(~isfinite(PlotDat)) = [];
                xtlabtext{d} = num2str(AgeDiv(d));
                if isempty(PlotDat)
                    continue
                else
                    eval(['HalfViolinPlot(PlotDat,xt(d),cDiv' num2str(d) ',Params.kdeHeight, Params.kdeWidthForOnePoint)']);
                end
                clear DatTemp ValMean ValStd UpperStd LowerStd
            end
            xticks(xt)
            xticklabels(xtlabtext)
            xlabel('Age')
            ylabel(eMetl(n))
            title(eGrp)
            aesthetics
            set(gca,'TickDir','out');
        end
        linkaxes(h,'xy')

        h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
        set(findall(gcf,'-property','FontSize'),'FontSize',9)

        % Set custom y axis 
        if isfield(Params.networkLevelNetMetCustomBounds, eMeti) 

            boundVector = Params.networkLevelNetMetCustomBounds.(eMeti);

            if ~isnan(boundVector(1))
                yLowerBound = boundVector(1);
            else
                yLowerBound = h(1).YLim(1);
            end 
            
            if ~isnan(boundVector(2))
                yUpperBound = boundVector(2);
            else
                yUpperBound = h(1).YLim(2);
            end  

        else 
            yLowerBound = h(1).YLim(1);
            yUpperBound = h(1).YLim(2);
        end 
        
        ylim([yLowerBound, yUpperBound])

        % Export figure
        for nFigExt = 1:length(Params.figExt)
            figName = strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''), Params.figExt{nFigExt});
            figPath = fullfile(halfViolinPlotByGroupFolderPlusLag, figName);
            figPath = strrep(figPath, '>', 'greater than');
            figPath = strrep(figPath, '<', 'less than');
            saveas(gcf, figPath);
        end 

        % Close figure or clear the one shared figures
        if ~Params.showOneFig
            close(gcf)
        else
            set(0, 'CurrentFigure', oneFigureHandle);
            clf reset
        end 
    end
end

%% notBoxPlots - plots by DIV
if Params.includeNotBoxPlots 
    notBoxPlotByDivFolder = fullfile(Params.outputDataFolder, ...
        strcat('OutputData',Params.Date), '4_NetworkActivity', '4B_GroupComparisons', ...
        '4_RecordingsByAge', 'NotBoxPlots');

    eMet = Params.networkLevelNetMetToPlot;
    eMetl = Params.networkLevelNetMetLabels;

    for n = 1:length(eMetl)
        eMetl(n) = strrep(eMetl(n), '/', 'div');  
        % edge case where there is a division symbol in the label
    end 

    p = [100 100 1300 600]; 
    set(0, 'DefaultFigurePosition', p)
    if Params.showOneFig
        set(oneFigureHandle, 'Position', p);
    end 

    for l = 1:length(Params.FuncConLagval)
        notBoxPlotByDivFolderPlusLag = fullfile(notBoxPlotByDivFolder, ...
            strcat(num2str(Params.FuncConLagval(l)),'mslag'));

        if ~isfolder(notBoxPlotByDivFolderPlusLag)
            mkdir(notBoxPlotByDivFolderPlusLag)
        end 

        for n = 1:length(eMet)
            if ~isfield(Params, 'oneFigure')
                F1 = figure;
            end 
            eMeti = char(eMet(n));
            xt = 1:0.5:1+(length(Grps)-1)*0.5;
            for d = 1:length(AgeDiv)
                h(d) = subplot(1,length(AgeDiv),d);
                eDiv = num2str(AgeDiv(d));
                for g = 1:length(Grps)
                    eGrp = cell2mat(Grps(g));
                    eDivTP = strcat('TP',num2str(d));
                    VNe = strcat(eGrp,'.',eDivTP,'.',eMeti);
                    eval(['DatTemp = ' VNe ';']);
                    % Make zero vector if DIV is empty 
                    if isempty(DatTemp)
                        DatTemp = zeros(1, length(Params.FuncConLagval));
                    end 
                    PlotDat = DatTemp(:,l);
                    notBoxPlotRF(PlotDat, xt(g), Params.groupColors(g, :), 12);
                    clear DatTemp ValMean ValStd UpperStd LowerStd
                    xtlabtext{g} = eGrp;
                end
                xticks(xt)
                xticklabels(xtlabtext)
                xlabel('Group')
                ylabel(eMetl(n))
                title(strcat('Age',eDiv))
                aesthetics
                set(gca,'TickDir','out');
            end
            linkaxes(h,'xy')
            h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
            set(findall(gcf,'-property','FontSize'),'FontSize',12)

            % Export figure
            for nFigExt = 1:length(Params.figExt)
                figName = strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt});
                figPath = fullfile(notBoxPlotByDivFolderPlusLag, figName);
                figPath = strrep(figPath, '>', 'greater than');
                figPath = strrep(figPath, '<', 'less than');
                saveas(gcf, figPath);
            end 

            % Close figure or clear the one shared figures
            if ~Params.showOneFig
                close(gcf)
            else
                set(0, 'CurrentFigure', oneFigureHandle);
                clf reset
            end 
        end

    end
end 

%% halfViolinPlots - plots by DIV

halfViolinPlotByDivFolder = fullfile(Params.outputDataFolder, strcat('OutputData',Params.Date), ...
    '4_NetworkActivity', '4B_GroupComparisons', '4_RecordingsByAge', 'HalfViolinPlots');

eMet = Params.networkLevelNetMetToPlot;
eMetl = Params.networkLevelNetMetLabels;

for n = 1:length(eMetl)
    eMetl(n) = strrep(eMetl(n), '/', 'div');  % edge case where there is a division symbol in the label
end 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)
if Params.showOneFig
    set(oneFigureHandle, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    halfViolinPlotByDivFolderPlusLag = fullfile(halfViolinPlotByDivFolder, ...
        strcat(num2str(Params.FuncConLagval(l)),'mslag'));
    if ~isfolder(halfViolinPlotByDivFolderPlusLag)
        mkdir(halfViolinPlotByDivFolderPlusLag)
    end 
    for n = 1:length(eMet)
        if ~Params.showOneFig
            F1 = figure;
        end 
        eMeti = char(eMet(n));
        xt = 1:length(Grps);
        for d = 1:length(AgeDiv)
            h(d) = subplot(1,length(AgeDiv),d);
            eDiv = num2str(AgeDiv(d));
            for g = 1:length(Grps)
                eGrp = cell2mat(Grps(g));
                eDivTP = strcat('TP',num2str(d));
                VNe = strcat(eGrp,'.',eDivTP,'.',eMeti);
                eval(['DatTemp = ' VNe ';']);
                % Tim: temp fix to make zero vector if DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                PlotDat(~isfinite(PlotDat)) = [];
                if (1 - isempty(PlotDat))
                    HalfViolinPlot(PlotDat, xt(g), Params.groupColors(g, :), Params.kdeHeight, Params.kdeWidthForOnePoint);
                end
                hold on
                % clear DatTemp ValMean ValStd UpperStd LowerStd
                xtlabtext{g} = eGrp;
            end
            xticks(xt)
            xticklabels(xtlabtext)
            xlabel('Group')
            ylabel(eMetl(n))
            title(strcat('Age',eDiv))
            aesthetics
            set(gca,'TickDir','out');
        end
        linkaxes(h,'xy')

        if isfield(Params.networkLevelNetMetCustomBounds, eMeti) 

            boundVector = Params.networkLevelNetMetCustomBounds.(eMeti);

            if ~isnan(boundVector(1))
                yLowerBound = boundVector(1);
            else
                yLowerBound = h(1).YLim(1);
            end 
            
            if ~isnan(boundVector(2))
                yUpperBound = boundVector(2);
            else
                yUpperBound = h(1).YLim(2);
            end  

        else 
            yLowerBound = h(1).YLim(1);
            yUpperBound = h(1).YLim(2);
        end 

        ylim([yLowerBound, yUpperBound]);
        
        xLowerBound = min(xt) - 0.5;
        xUpperBound = max(xt) + 0.5;
        set(gca, 'YLim', [yLowerBound, yUpperBound])
        % h(1).YLim = [yLowerBound, yUpperBound];
        h(1).XLim = [xLowerBound xUpperBound];
        set(findall(gcf,'-property','FontSize'),'FontSize',12)

        % Export figure
        for nFigExt = 1:length(Params.figExt)
            figName = strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt});
            figPath = fullfile(halfViolinPlotByDivFolderPlusLag, figName);
            figPath = strrep(figPath, '>', 'greater than');
            figPath = strrep(figPath, '<', 'less than');
            saveas(gcf, figPath);
        end 

        % Close figure or clear the one shared figures
        if ~Params.showOneFig
            close(gcf)
        else
            set(0, 'CurrentFigure', oneFigureHandle);
            clf reset
        end 
    end
end

   
%% halfViolinPlots - plots by group electrode specific data

nodeByGroupFolder = fullfile(Params.outputDataFolder, strcat('OutputData',Params.Date), ...
    '4_NetworkActivity', '4B_GroupComparisons', '1_NodeByGroup');

eMet = Params.unitLevelNetMetToPlot; 
eMetl = Params.unitLevelNetMetLabels; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)
if Params.showOneFig
    set(oneFigureHandle, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    nodeByGroupFolderPlusLag = fullfile(nodeByGroupFolder, ...
        strcat(num2str(Params.FuncConLagval(l)),'mslag'));
    if ~isfolder(nodeByGroupFolderPlusLag)
        mkdir(nodeByGroupFolderPlusLag)
    end 
    for n = 1:length(eMet)
        if ~Params.showOneFig
            F1 = figure;
        end 
        eMeti = char(eMet(n));
        xt = 1:length(AgeDiv);
        for g = 1:length(Grps)
            h(g) = subplot(1,length(Grps),g);
            eGrp = cell2mat(Grps(g));
            for d = 1:length(AgeDiv)
                eDiv = strcat('TP',num2str(d));
                VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
                eval(['DatTemp = ' VNe ';']);
                % Make zero vector if DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                PlotDat(~isfinite(PlotDat)) = [];
                if isempty(PlotDat)
                    continue
                else
                    eval(['HalfViolinPlot(PlotDat,xt(d),cDiv' num2str(d) ', Params.kdeHeight, Params.kdeWidthForOnePoint)']);
                    %  HalfViolinPlot(PlotDat, xt(d), Params.groupColors(d, :), Params.kdeHeight, Params.kdeWidthForOnePoint);
                end
                clear DatTemp ValMean UpperStd LowerStd
                xtlabtext{d} = num2str(AgeDiv(d));
            end
            xticks(xt)
            xticklabels(xtlabtext)
            xlabel('Age')
            ylabel(eMetl(n))
            title(eGrp)
            aesthetics
            set(gca,'TickDir','out');
        end
        linkaxes(h,'xy')
        h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
        
        % Set custom y axis 
        if isfield(Params.networkLevelNetMetCustomBounds, eMeti) 

            boundVector = Params.networkLevelNetMetCustomBounds.(eMeti);

            if ~isnan(boundVector(1))
                yLowerBound = boundVector(1);
            else
                yLowerBound = h(1).YLim(1);
            end 

            if ~isnan(boundVector(2))
                yUpperBound = boundVector(2);
            else
                yUpperBound = h(1).YLim(2);
            end  

        else 
            yLowerBound = h(1).YLim(1);
            yUpperBound = h(1).YLim(2);
        end 

        ylim([yLowerBound, yUpperBound])
        
        set(findall(gcf,'-property','FontSize'),'FontSize',9)

        % Export figure
        for nFigExt = 1:length(Params.figExt)
            figName = strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt});
            figPath = fullfile(nodeByGroupFolderPlusLag, figName);
            figPath = strrep(figPath, '>', 'greater than');
            figPath = strrep(figPath, '<', 'less than');
            saveas(gcf, figPath);
        end 

         % Close figure or clear the one shared figures
        if ~Params.showOneFig
            close(gcf)
        else
            set(0, 'CurrentFigure', oneFigureHandle);
            clf reset
        end 
    end
end


%% halfViolinPlots - plots by DIV electrode specific data

halfViolinPlotByAgeFolder = fullfile(Params.outputDataFolder, strcat('OutputData',Params.Date), ...
    '4_NetworkActivity', '4B_GroupComparisons', '2_NodeByAge');

eMet = Params.unitLevelNetMetToPlot; 
eMetl = Params.unitLevelNetMetLabels; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)
if Params.showOneFig
    set(oneFigureHandle, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    halfViolinPlotByAgeFolderPlusLag = fullfile(halfViolinPlotByAgeFolder, ...
        strcat(num2str(Params.FuncConLagval(l)),'mslag'));
    
    if ~isfolder(halfViolinPlotByAgeFolderPlusLag)
        mkdir(halfViolinPlotByAgeFolderPlusLag)
    end 

    for n = 1:length(eMet)
        if ~isfield(Params, 'oneFigure')
            F1 = figure;
        end 
        eMeti = char(eMet(n));
        xt = 1:length(Grps);
        for d = 1:length(AgeDiv)
            h(d) = subplot(1,length(AgeDiv),d);
            eDiv = num2str(AgeDiv(d));
            for g = 1:length(Grps)
                eGrp = cell2mat(Grps(g));
                eDivTP = strcat('TP',num2str(d));
                VNe = strcat(eGrp,'.',eDivTP,'.',eMeti);
                eval(['DatTemp = ' VNe ';']);
                % Make zero vector if DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                PlotDat(~isfinite(PlotDat)) = [];
                if isempty(PlotDat)
                    continue
                else
                    HalfViolinPlot(PlotDat, xt(g), Params.groupColors(g, :), Params.kdeHeight, Params.kdeWidthForOnePoint);
                end
                clear DatTemp ValMean ValStd UpperStd LowerStd
                xtlabtext{g} = eGrp;
            end
            xticks(xt)
            xticklabels(xtlabtext)
            xlabel('Group')
            ylabel(eMetl(n))
            title(strcat('Age',eDiv))
            aesthetics
            set(gca,'TickDir','out');
        end
        linkaxes(h,'xy')
        h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
        
        % Set custom y axis 
        if isfield(Params.networkLevelNetMetCustomBounds, eMeti) 

            boundVector = Params.networkLevelNetMetCustomBounds.(eMeti);

            if ~isnan(boundVector(1))
                yLowerBound = boundVector(1);
            else
                yLowerBound = h(1).YLim(1);
            end 

            if ~isnan(boundVector(2))
                yUpperBound = boundVector(2);
            else
                yUpperBound = h(1).YLim(2);
            end  

        else 
            yLowerBound = h(1).YLim(1);
            yUpperBound = h(1).YLim(2);
        end 

        ylim([yLowerBound, yUpperBound])

        set(findall(gcf,'-property','FontSize'),'FontSize',12)
        
        % Export figure
        for nFigExt = 1:length(Params.figExt)
            figName = strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt});
            figPath = fullfile(halfViolinPlotByAgeFolderPlusLag, figName);
            figPath = strrep(figPath, '>', 'greater than');
            figPath = strrep(figPath, '<', 'less than');
            saveas(gcf, figPath);
        end 

        % Close figure or clear the one shared figures
        if ~Params.showOneFig
            close(gcf)
        else
            set(0, 'CurrentFigure', oneFigureHandle);
            clf reset
        end 
    end
end

end