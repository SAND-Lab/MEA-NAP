function PlotEphysStats(ExpName, Params, HomeDir, oneFigureHandle)
% plot ephys statistics for MEA data
% Parameters 
% -----------
% ExpName : str
% Params : structure
%     The following fields are used
%     groupColors : (nGroup x 3 matrix)
%         the RGB colors to use for each group during plotting
%     
% HomeDir : str
% oneFigureHandle : NaN or figure object
% Returns
% -------
% None
%
% Author : RCFeord July 2021
% Updated by Tim Sit 
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

%% Custom bounds for y axis 

eMetCustomBounds = { ...
'number of active electrodes', [0, nan]; ...
'mean firing rate (Hz)', [0, nan]; ...
'median firing rate (Hz)', [0, nan]; ...
'network burst rate (per minute)', [0, nan]; ... 
'mean network burst length (s)', [0, nan]; ...
'mean ISI within network burst (ms)', [0, nan]; ...
'mean ISI outside network bursts (ms)', [0, nan]; ...
'coefficient of variation of inter network burst intervals', [0, nan]; ...
'fraction of bursts in network bursts', [0, 1]; ... 
'mean number of channels involved in network bursts', [0, nan]; ... 
};

metricsWCustomBounds = eMetCustomBounds(:, 1);

%% groups and DIV

if ~isempty(Params.customGrpOrder) 
    Grps = Params.customGrpOrder;
else
    Grps = Params.GrpNm;
end 

AgeDiv = Params.DivNm;



%% Variable names

if Params.suite2pMode == 0
   activityStatsFieldName = 'Ephys';  
   % this is for legacy purposes, future implementation should name the field 
   % as activityStats all the time
   % list of metrics 
   NetMetricsE = {'numActiveElec',...
                  'FRmean',...
                  'FRmedian',...
                  'NBurstRate', ...
                   'meanNumChansInvolvedInNbursts', ... 
                   'meanNBstLengthS',...
                   'meanISIWithinNbursts_ms', ...
                   'meanISIoutsideNbursts_ms', ...
                   'CVofINBI', ...
                   'fracInNburst', ...
                   'channelAveBurstRate', ...
                   'channelAveBurstDur', ...
                   'channelAveISIwithinBurst', ... 
                   'channelAveISIoutsideBurst', ...
                   'channelAveFracSpikesInBursts', ...
                   }; 

   eMetl = {'number of active electrodes', ...
            'mean firing rate (Hz)', ...
            'median firing rate (Hz)', ... 
            'network burst rate (per minute)', ...
            'mean number of channels involved in network bursts', ...
            'mean network burst length (s)',...
            'mean ISI within network burst (ms)', ... 
            'mean ISI outside network bursts (ms)', ...
            'coefficient of variation of inter network burst intervals', ... 
            'fraction of bursts in network bursts', ...
            'Single-electrode burst rate (per minute)', ...
            'Single-electrode average burst duration (ms)', ...
            'Single-electrode average ISI within burst (ms)', ... 
            'Single-electrode average ISI outside burst (ms)', ... 
            'Mean fraction of spikes in bursts per electrode', ...
            }; 
else 
   activityStatsFieldName = 'activityStats';
   NetMetricsE = {'numActiveElec','FRmean','FRmedian', ...
                 'recHeightMean', 'recPeakDurMean', 'recEventAreaMean'}; 
   eMetl = {'number of active units','mean firing rate (Hz)','median firing rate (Hz)', ...
           'mean peak height', 'mean peak duration (s)', 'mean event area'}; 
end


% whole experiment metrics (1 value per experiment)
% names of metrics
ExpInfoE = {'Grp','DIV'}; % info for both age and genotype


% single cell/node metrics (1 value per cell/node)

% names of metrics
ExpInfoC = {'Grp','DIV'}; % info for both age and genotype

% list of cell level metrics 
if Params.suite2pMode == 0
    NetMetricsC = {'FR', ...
                   'FRactive', ...
                   'channelBurstRate', ...
                   'channelWithinBurstFr', ...
                   'channelBurstDur', ...
                   'channelISIwithinBurst', ...
                   'channeISIoutsideBurst', ...
                   'channelFracSpikesInBursts', ...
                   };
    cMetl = {'mean_firing_rate_node', ...
             'mean_firing_rate_active_node', ....
             'Unit burst rate (per minute)', ...
             'Unit within-burst firing rate (Hz)', ...
             'Unit burst duration (ms)', ...
             'Unit ISI within burst (ms)', ...
             'Unit ISI outside burst (ms)', ...
             'Unit fraction of spikes in bursts', ...
             };
else 
    NetMetricsC = {'FR', 'unitHeightMean', 'unitPeakDurMean', 'unitEventAreaMean'};
    cMetl = {'mean_firing_rate_node', 'peak height', 'peak duration', 'event area'};
end


%% Import data from all experiments - whole experiment  

experimentMatFolderPath = fullfile(Params.outputDataFolder, ...
        Params.outputDataFolderName, 'ExperimentMatFiles');

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
     Exp = strcat(char(ExpName(i)),'_',Params.outputDataFolderName,'.mat');
     ExpFilePath = fullfile(experimentMatFolderPath, Exp);
     % TODO: load to variable
     load(ExpFilePath)
     for g = 1:length(Grps)
         if strcmp(cell2mat(Grps(g)),cell2mat(Info.Grp))
             eGrp = cell2mat(Grps(g));
         end       
     end
     for d = 1:length(AgeDiv)
         if cell2mat(Info.DIV) == AgeDiv(d)
             eDiv = strcat('TP',num2str(d));
         end    
     end
     for e = 1:length(NetMetricsE)
         eMet = cell2mat(NetMetricsE(e));
         VNs = strcat([activityStatsFieldName '.' eMet]);
         eval(['DatTemp =' VNs ';']);
         clear VNs
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
     Exp = strcat(char(ExpName(i)),'_',Params.outputDataFolderName,'.mat');
     ExpFilePath = fullfile(experimentMatFolderPath, Exp);
     load(ExpFilePath)
     for g = 1:length(Grps)
         if strcmp(cell2mat(Grps(g)),cell2mat(Info.Grp))
             eGrp = cell2mat(Grps(g));
         end       
     end
     for d = 1:length(AgeDiv)
         if cell2mat(Info.DIV) == AgeDiv(d)
             eDiv = strcat('TP',num2str(d));
         end    
     end
     for e = 1:length(NetMetricsC)
         eMet = cell2mat(NetMetricsC(e));
         VNs = strcat([activityStatsFieldName '.' eMet]);
         eval(['DatTemp =' VNs ';']);
         clear VNs
         VNe = strcat(eGrp,'.',eDiv,'.',eMet);
         eval([VNe '= [' VNe '; DatTemp''];']);
         clear DatTemp
     end
     clear Info NetMet adjMs
end


%% notBoxPlots - plots by group

notBoxPlotByGroupFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
    '2_NeuronalActivity', '2B_GroupComparisons', '3_RecordingsByGroup', 'NotBoxPlots');

eMet = NetMetricsE; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

if Params.includeNotBoxPlots

    for n = 1:length(eMet)
        if Params.showOneFig
            if isgraphics(oneFigureHandle)
                set(oneFigureHandle, 'Position', p);
            else 
                oneFigureHandle = figure;
            end 
        else 
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
                PlotDat = DatTemp;
                PlotDat(isnan(PlotDat)) = [];
                PlotDat(~isfinite(PlotDat)) = [];
                if isempty(PlotDat)
                    continue
                else
                    eval(['notBoxPlotRF(PlotDat,xt(d),cDiv' num2str(d) ',7)']);
                end
                clear DatTemp ValMean ValStd UpperStd LowerStd
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
        set(findall(gcf,'-property','FontSize'),'FontSize',9)

        figName = strcat(num2str(n),'_',char(eMetl(n)), '_byGroup');
        figPath = fullfile(notBoxPlotByGroupFolder, figName);

        if Params.showOneFig
            pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
        else
            pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
        end 

        if Params.showOneFig
            clf(oneFigureHandle)
        else 
            close(F1);
        end 

    end
end 

%% halfViolinPlots - plots by group

halfViolinPlotByGroupFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
    '2_NeuronalActivity', '2B_GroupComparisons', '3_RecordingsByGroup', 'HalfViolinPlots');

eMet = NetMetricsE; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

for n = 1:length(eMet)
    all_group_eMet_vals = [];
    
    if Params.showOneFig
        if isgraphics(oneFigureHandle)
            set(oneFigureHandle, 'Position', p);
        else 
            oneFigureHandle = figure;
        end 
    else 
        F1 = figure;
    end 
    
    eMeti = char(eMet(n));
    xt = 1:length(AgeDiv);
    xtlabtext = {};
    for g = 1:length(Grps)
        h(g) = subplot(1,length(Grps),g);
        eGrp = cell2mat(Grps(g));
        for d = 1:length(AgeDiv)
            eDiv = strcat('TP',num2str(d));
            VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
            eval(['DatTemp = ' VNe ';']);
            PlotDat = DatTemp;
            PlotDat(isnan(PlotDat)) = [];
            PlotDat(~isfinite(PlotDat)) = [];
            all_group_eMet_vals = [all_group_eMet_vals; PlotDat];
            
            if issparse(PlotDat)
               PlotDat = full(PlotDat); 
            end
            
            if isempty(PlotDat)
                continue
            else
                eval(['HalfViolinPlot(PlotDat,xt(d),cDiv' num2str(d) ', Params.kdeHeight, Params.kdeWidthForOnePoint)']);
            end
            clear DatTemp ValMean ValStd UpperStd LowerStd
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
    customBoundMatchVec = strcmp(eMetl(n), metricsWCustomBounds);
    if sum(customBoundMatchVec) == 1
        bound_idx = find(customBoundMatchVec);
        custom_bound_vec = eMetCustomBounds{bound_idx, 2};

        if isnan(custom_bound_vec(1))
            custom_bound_vec(1) = min(all_group_eMet_vals);
        end 
   
        if isnan(custom_bound_vec(2))
            if isempty(all_group_eMet_vals)
                if strcmp(Params.verboseLevel, 'High')
                    fprintf('WARNING: all_group_eMet_vals is empty, setting arbitrary bounds \n')
                end 
                custom_bound_vec(2) = 1;  % temp fix in rare case where all_group_eMet_vals is empty
            else
                custom_bound_vec(2) = max(all_group_eMet_vals);
            end 
            
        end 
        
        if custom_bound_vec(1) == custom_bound_vec(2)
            if strcmp(Params.verboseLevel, 'High')
                fprintf('WARNING: custom bound first value and second value are equal, adding one to deal with this \n')
            end
            custom_bound_vec(2) = custom_bound_vec(2) + 1;
        end 
        
        h(1).YLim = custom_bound_vec;
    end 

    set(findall(gcf,'-property','FontSize'),'FontSize',9)
    
    figName = strcat(num2str(n),'_',char(eMetl(n)), '_byGroup');
    figPath = fullfile(halfViolinPlotByGroupFolder, figName);
    
    if Params.showOneFig
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
    else
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
    end
    
    
    if Params.showOneFig
        clf(oneFigureHandle)
    else 
        close(F1);
    end 

end

%% notBoxPlots - plots by DIV

notBoxPlotByDivFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
    '2_NeuronalActivity', '2B_GroupComparisons', '4_RecordingsByAge', 'NotBoxPlots');

eMet = NetMetricsE; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

if Params.includeNotBoxPlots

    for n = 1:length(eMet)

        all_group_eMet_vals = [];

        if Params.showOneFig
            if isgraphics(oneFigureHandle)
                set(oneFigureHandle, 'Position', p);
            else 
                oneFigureHandle = figure;
            end 
        else 
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
                PlotDat = DatTemp;
                PlotDat(isnan(PlotDat)) = [];
                PlotDat(~isfinite(PlotDat)) = [];
                all_group_eMet_vals = [all_group_eMet_vals; PlotDat];

                if isempty(PlotDat)
                    continue
                else
                    notBoxPlotRF(PlotDat,xt(g), Params.groupColors(g, :) , 7);
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

        customBoundMatchVec = strcmp(eMetl(n), metricsWCustomBounds);
        if sum(customBoundMatchVec) == 1
            bound_idx = find(customBoundMatchVec);
            custom_bound_vec = eMetCustomBounds{bound_idx, 2};

            if isnan(custom_bound_vec(1))
                custom_bound_vec(1) = min(all_group_eMet_vals);
            end 

            if isnan(custom_bound_vec(2))
                if isempty(all_group_eMet_vals)
                    if strcmp(Params.verboseLevel, 'High')
                        fprintf('WARNING: all_group_eMet_vals is empty, setting arbitrary bounds \n')
                    end 
                    custom_bound_vec(2) = 1;
                else
                    custom_bound_vec(2) = max(all_group_eMet_vals);
                end 
            end 

            if custom_bound_vec(1) == custom_bound_vec(2)
                if strcmp(Params.verboseLevel, 'High')
                    fprintf('WARNING: custom bound first value and second value are equal, adding one to deal with this \n')
                end
                custom_bound_vec(2) = custom_bound_vec(2) + 1;
            end 

            h(1).YLim = custom_bound_vec;
        end 

        aesthetics
        set(gca,'TickDir','out');
        set(findall(gcf,'-property','FontSize'),'FontSize',9)

        figName = strcat(num2str(n),'_',char(eMetl(n)));
        figPath = fullfile(notBoxPlotByDivFolder, figName);

        if Params.showOneFig
            pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
        else
            pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
        end


        if Params.showOneFig
            clf(oneFigureHandle)
        else 
            close(F1);
        end 

    end
    
end 

%% halfViolinPlots - plots by DIV

halfViolinPlotByDivFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
    '2_NeuronalActivity', '2B_GroupComparisons', '4_RecordingsByAge', 'HalfViolinPlots');

eMet = NetMetricsE; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

for n = 1:length(eMet)
    
    if Params.showOneFig
        if isgraphics(oneFigureHandle)
            set(oneFigureHandle, 'Position', p);
        else 
            oneFigureHandle = figure;
        end 
    else 
        F1 = figure;
    end 
    
    eMeti = char(eMet(n));
    all_group_eMet_vals = [];
    xt = 1:length(Grps);
    for d = 1:length(AgeDiv)
        h(d) = subplot(1,length(AgeDiv),d);
        eDiv = num2str(AgeDiv(d));
        for g = 1:length(Grps)
            eGrp = cell2mat(Grps(g));
            eDivTP = strcat('TP',num2str(d));
            VNe = strcat(eGrp,'.',eDivTP,'.',eMeti);
            eval(['DatTemp = ' VNe ';']);
            PlotDat = DatTemp;
            PlotDat(isnan(PlotDat)) = [];
            PlotDat(~isfinite(PlotDat)) = [];
            all_group_eMet_vals = [all_group_eMet_vals; PlotDat];
            
            if issparse(PlotDat)
               PlotDat = full(PlotDat); 
            end
            
            if isempty(PlotDat)
                continue
            else
                HalfViolinPlot(PlotDat, xt(g), Params.groupColors(g, :), 0.3, Params.kdeWidthForOnePoint);
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

    customBoundMatchVec = strcmp(eMetl(n), metricsWCustomBounds);
    if sum(customBoundMatchVec) == 1
        bound_idx = find(customBoundMatchVec);
        custom_bound_vec = eMetCustomBounds{bound_idx, 2};

        if isnan(custom_bound_vec(1))
            custom_bound_vec(1) = min(all_group_eMet_vals);
        end 
   
        if isnan(custom_bound_vec(2))
            if isempty(all_group_eMet_vals)
                if strcmp(Params.verboseLevel, 'High')
                    fprintf('WARNING: all_group_eMet_vals is empty, setting arbitrary bounds \n')
                end 
                custom_bound_vec(2) = 1;
            else 
                custom_bound_vec(2) = max(all_group_eMet_vals);
            end 
        end 
        
        if custom_bound_vec(1) == custom_bound_vec(2)
            if strcmp(Params.verboseLevel, 'High')
                fprintf('WARNING: custom bound first value and second value are equal, adding one to deal with this \n')
            end 
            custom_bound_vec(2) = custom_bound_vec(2) + 1;
        end 
        h(1).YLim = custom_bound_vec;
    end 

    aesthetics
    set(gca,'TickDir','out');
    set(findall(gcf,'-property','FontSize'),'FontSize',9)

    figName = strcat(num2str(n),'_',char(eMetl(n)), '_byAge');
    figPath = fullfile(halfViolinPlotByDivFolder, figName);
    
    if Params.showOneFig
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
    else
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
    end
    
    
    if Params.showOneFig
        clf(oneFigureHandle)
    else 
        close(F1);
    end 
end

%% halfViolinPlots - plots by group (NODE LEVEL)

halfViolinPlotNodeByGroupFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
    '2_NeuronalActivity', '2B_GroupComparisons', '1_NodeByGroup');

eMet = NetMetricsC; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

allPlotDat = [];
for n = 1:length(eMet)
    
    if Params.showOneFig
        if isgraphics(oneFigureHandle)
            set(oneFigureHandle, 'Position', p);
        else 
            oneFigureHandle = figure;
        end 
    else 
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
            PlotDat = DatTemp;
            PlotDat(isnan(PlotDat)) = [];
            PlotDat(~isfinite(PlotDat)) = [];
            if isempty(PlotDat)
                continue
            else
                eval(['HalfViolinPlot(PlotDat,xt(d),cDiv' num2str(d) ',0.3, Params.kdeWidthForOnePoint)']);
                allPlotDat = [allPlotDat; PlotDat]; 
            end
            clear DatTemp ValMean ValStd UpperStd LowerStd
            xtlabtext{d} = num2str(AgeDiv(d));
        end
        xticks(xt)
        xticklabels(xtlabtext)
        xlabel('Age')
        ylabel(cMetl(n))
        title(eGrp)
        aesthetics
        set(gca,'TickDir','out');
    end
    linkaxes(h,'xy')
    h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
    aesthetics
    set(gca,'TickDir','out');
    set(findall(gcf,'-property','FontSize'),'FontSize',9)
    % set hard lower bound to be zero for firing rate 
    if isempty(PlotDat)
        maxPlotDat = 1;
    else 
        maxPlotDat = nanmax(PlotDat);
        if maxPlotDat <= 0 
            maxPlotDat = 1;
        end 
    end 
        
    ylim([0, maxPlotDat])
    figName = strcat(num2str(n),'_',char(cMetl(n)), '_byGroup');
    figPath = fullfile(halfViolinPlotNodeByGroupFolder, figName);
    
    if Params.showOneFig
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
    else
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
    end
    
    if Params.showOneFig
        clf(oneFigureHandle)
    else 
        close(F1);
    end 
end

%% halfViolinPlots - plots by DIV : mean firing rate per electrode 
halfViolinPlotByNodeDivFolder = fullfile(Params.outputDataFolder, Params.outputDataFolderName, ...
    '2_NeuronalActivity', '2B_GroupComparisons', '2_NodeByAge');

eMet = NetMetricsC; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

all_eMet_vals = [];

for n = 1:length(eMet)
    
    if Params.showOneFig
        if isgraphics(oneFigureHandle)
            set(oneFigureHandle, 'Position', p);
        else 
            oneFigureHandle = figure;
        end 
    else 
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
            % TODO: fix this
            VNe = strcat(eGrp,'.',eDivTP,'.',eMeti);
            eval(['DatTemp = ' VNe ';']);
            PlotDat = DatTemp;
            PlotDat(isnan(PlotDat)) = [];
            PlotDat(~isfinite(PlotDat)) = [];
            % concateenate to a store to get ylim 
            all_eMet_vals = [all_eMet_vals; PlotDat];

            if isempty(PlotDat)
                continue
            else
                HalfViolinPlot(PlotDat, xt(g), Params.groupColors(g, :), 0.3, Params.kdeWidthForOnePoint);
            end
            clear DatTemp ValMean ValStd UpperStd LowerStd
            xtlabtext{g} = eGrp;
        end
        xticks(xt)
        xticklabels(xtlabtext)
        xlabel('Group')
        ylabel(cMetl(n))
        title(strcat('Age',eDiv))
        aesthetics
        set(gca,'TickDir','out');
    end
    linkaxes(h,'xy')
    h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
    h(1).YLim = [0, max(all_eMet_vals)];
    aesthetics
    set(gca,'TickDir','out');
    set(findall(gcf,'-property','FontSize'),'FontSize',9)

    % Export figure
    figName = strcat(num2str(n),'_',char(cMetl(n)));
    figPath = fullfile(halfViolinPlotByNodeDivFolder, figName);
    
    if Params.showOneFig
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, oneFigureHandle);
    else
        pipelineSaveFig(figPath, Params.figExt, Params.fullSVG, F1);
    end
    
    if Params.showOneFig
        clf(oneFigureHandle)
    else 
        close(F1);
    end 
end

end