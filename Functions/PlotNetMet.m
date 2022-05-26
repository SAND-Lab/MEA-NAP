function [] = PlotNetMet(ExpName,Params,HomeDir)
%{
Plot network metrics for MEA data

INPUTS 
---------------
ExpName : (cell array)
    cell array where each entry is the name of the recording to 
    plot network metrics (file extension should NOT be included)
Params : (struct)
    structure object with key parameters for analysis, namely 
    Params.output_spreadsheet_file_type : (str)
        whether to output analysis results as excel spreadsheet (.xlsx), 
        using 'excel' or comma-separated values (.csv) using 'csv'
    Params.groupColors : (nGroup x 3 matrix)
        RGB colors (scale from 0 to 1) to use for each group in plotting
HomeDir : (str) 
    main directory of the analysis 
    ie. '/your/path/to/AnalysisPipeline'

Other dependicies 
    this code goes through the folder
    .../AnalysisPipeline/OutputDataXXXXXXX/ExperimentMatFiles
    and reads through the data contained there, each mat file 
    in there should contain the following variables
    Ephys : (struct)
    Info : (struct)
    NetMet : (struct)
    Params : (struct)
    adjMS : (struct)
    spikeTimes : (struct)
    
Returns
-------


Meaning of the variables: 


cDiv1, cDiv2, ... : this is a 1 x 3 vector with the RGB values of the color to be used 

Implicit dependencies 
NetMet (structure)


author RCFeord July 2021
edited by Tim Sit
%}

% specify output format (currently Params is loaded from the mat file, 
% so it will override the settings), may need to find a better way 
% to distinguish the two 
output_spreadsheet_file_type = Params.output_spreadsheet_file_type;




%% colours

% colour scheme for age groups DIV
ColOpt1 = [0.988 0.906 0.149];
ColOpt2 = [0.710 0.871 0.173];
ColOpt3 = [0.427 0.808 0.345];
ColOpt4 = [0.208 0.718 0.478];
ColOpt5 = [0.118 0.624 0.537];
ColOpt6 = [0.145 0.514 0.557];
ColOpt7 = [0.192 0.404 0.553];
ColOpt8 = [0.239 0.290 0.541];
ColOpt9 = [0.282 0.157 0.474];
ColOpt10 = [0.267 0.051 0.325];
nColOpt = 10;

% specify colours to use on the basis of the number of time points
nDIV = length(Params.DivNm);
if nDIV == 1
    cDiv1 = ColOpt5;
else
    for ii = 1:nDIV
        eval(['cDiv' num2str(ii) '= ColOpt' num2str(round(1+(nColOpt/nDIV)*(ii-1))) ';']);
    end
end

%% groups and DIV

Grps = Params.GrpNm;
AgeDiv = Params.DivNm;

if strcmp(char(Grps{1}),'HET')&&strcmp(char(Grps{2}),'KO')&&strcmp(char(Grps{3}),'WT')
   clear Grps
   Grps{1} = 'WT'; Grps{2} = 'HET'; Grps{3} = 'KO';
end

%% Variable names

% whole experiment metrics (1 value per experiment)

% names of metrics
ExpInfoE = {'Grp','DIV'}; % info for both age and genotype
% list of metrics 
NetMetricsE = {'Dens','Q','nMod','Eglob','aN','CC','PL','SW','SWw', ... 
    'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 

% single cell/node metrics (1 value per cell/node)

% names of metrics
ExpInfoC = {'Grp','DIV'}; % info for both age and genotype
% list of metrics 
NetMetricsC = {'ND','EW','NS','Eloc','BC','PC','Z'};

%% Import data from all experiments - whole experiment  

cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')

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
     Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');

     % if previously used showOneFig, then this prevents saved oneFigure 
     % handle from showing up when loading the matlab variable
     if Params.showOneFig 
         % Make it so figure handle in oneFigure don't appear
         set(0, 'DefaultFigureVisible', 'off')
     end 

     load(Exp)  % what does this file contain? 
     % filepath contains Info structure

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
            for l = 1:length(Params.FuncConLagval)
                VNs = strcat('NetMet.adjM',num2str(Params.FuncConLagval(l)),'mslag.',eMet);
                eval(['DatTemp(l) =' VNs ';']);
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
     Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
     % if previously used showOneFig, then this prevents saved oneFigure 
     % handle from showing up when loading the matlab variable
     if Params.showOneFig 
         % Make it so figure handle in oneFigure don't appear
         set(0, 'DefaultFigureVisible', 'off')
     end 
     load(Exp)
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
            for l = 1:length(Params.FuncConLagval)
                VNs = strcat('NetMet.adjM',num2str(Params.FuncConLagval(l)),'mslag.',eMet);
                eval(['DatTemp' num2str(l) '= ' VNs ';']);
                eval(['mL(l) = length(DatTemp' num2str(l) ');']);
                clear VNs
            end
            for l = 1:length(Params.FuncConLagval)
                eval(['DatTempT = DatTemp' num2str(l) ';']);
                if length(DatTempT) < max(mL)
                    DatTempT(length(DatTempT+1):max(mL)) = nan;
                end
                DatTemp(:,l) = DatTempT;
            end
            VNe = strcat(eGrp,'.',eDiv,'.',eMet);
            eval([VNe '= [' VNe '; DatTemp];']);
            clear DatTemp
     end
     clear Info NetMet adjMs
end

%% export to spreadsheet (excel or csv)
cd(HomeDir); cd(strcat('OutputData',Params.Date));

if strcmp(output_spreadsheet_file_type, 'csv')
    % make one main table for storing all data 
    main_table = {};  
    n_row = 1; 
end 


% network means
for g = 1:length(Grps)
    eGrp = cell2mat(Grps(g));
    for d = 1:length(AgeDiv)
        eDiv = strcat('TP',num2str(d));
        VNe = strcat(eGrp,'.',eDiv);
        % VNe = eGrp.(eDiv);
        VNet = strcat('TempStr.',eDiv);
        for l = 1:length(Params.FuncConLagval)
            for e = 1:length(NetMetricsE)
                % Only do the asignment if metricVal is not empty
                eval(['metricVal' '=' VNe '.' char(NetMetricsE(e)) ';'])
                if length(metricVal) ~= 0
                    eval([VNet '.' char(NetMetricsE(e)) '='  'metricVal(:,l);']);
                else 
                    eval([VNet '.' char(NetMetricsE(e)) '='  '0;']);
                end 
                % netMetricToGet = char(NetMetricsE(e));
                % VNet.(netMetricToGet) = VNe.(netMetricToGet)
            end
            eval(['DatTemp = ' VNet ';']); 
            if strcmp(output_spreadsheet_file_type, 'csv')
                %numEntries = length(DatTemp.(NetMetricsE{1}));
                DatTempFieldNames = fieldnames(DatTemp);
                numEntries = length(DatTemp.(DatTempFieldNames{1}));
                DatTemp.eGrp = repmat(convertCharsToStrings(eGrp), numEntries, 1);
                DatTemp.AgeDiv = repmat(AgeDiv(d), numEntries, 1);
                DatTemp.Lag = repmat(Params.FuncConLagval(l), numEntries, 1);
                table_obj = struct2table(DatTemp);
                for table_row = 1:numEntries
                    main_table{n_row} = table_obj(table_row, :);
                    n_row = n_row + 1;
                end 
            else
                table_obj = struct2table(DatTemp);
            end 

            if strcmp(output_spreadsheet_file_type, 'excel')
                table_savepath = strcat('NetworkActivity_RecordingLevel_',eGrp,'.xlsx');
                writetable(table_obj, table_savepath, ... 
                    'FileType','spreadsheet','Sheet', ... 
                    strcat('Age',num2str(AgeDiv(d)), ... 
                    'Lag',num2str(Params.FuncConLagval(l)),'ms'));
            end 
        end
    end
end

if strcmp(output_spreadsheet_file_type, 'csv')
    combined_table = vertcat(main_table{:});
    table_savepath = strcat('NetworkActivity_RecordingLevel.csv');
    writetable(combined_table, table_savepath);
end 


clear DatTemp TempStr

%% electrode specific
if strcmp(output_spreadsheet_file_type, 'csv')
    % make one main table for storing all data 
    electrode_main_table = {};  
    n_row = 1; 
end 


for g = 1:length(Grps)
    eGrp = cell2mat(Grps(g));
    for d = 1:length(AgeDiv)
        eDiv = strcat('TP',num2str(d));
        VNe = strcat(eGrp,'.',eDiv);
        VNet = strcat('TempStr.',eDiv);
        for l = 1:length(Params.FuncConLagval)
            for e = 1:length(NetMetricsC)
                % Only do the assignment if metricVal is not empty 
                eval(['metricVal' '=' VNe '.' char(NetMetricsC(e)) ';'])
                if length(metricVal) ~= 0
                    eval([VNet '.' char(NetMetricsC(e)) '=' 'metricVal(:,l);']);
                else 
                    eval([VNet '.' char(NetMetricsC(e)) '=' '0']);
                end 
            end
            eval(['DatTemp = ' VNet ';']);
            
           if strcmp(output_spreadsheet_file_type, 'csv')
                DatTempFieldNames = fieldnames(DatTemp);
                numEntries = length(DatTemp.(DatTempFieldNames{1}));
                DatTemp.eGrp = repmat(convertCharsToStrings(eGrp), numEntries, 1);
                DatTemp.AgeDiv = repmat(AgeDiv(d), numEntries, 1);
                DatTemp.Lag = repmat(Params.FuncConLagval(l), numEntries, 1);
                electrode_table_obj = struct2table(DatTemp);
                for table_row = 1:numEntries
                    electrode_main_table{n_row} = electrode_table_obj(table_row, :);
                    n_row = n_row + 1;
                end 
            else
                electrode_table_obj = struct2table(DatTemp);
            end 


            if strcmp(output_spreadsheet_file_type, 'excel')
                writetable(electrode_table_obj, ... 
                    strcat('NetworkActivity_NodeLevel_',eGrp,'.xlsx'),... 
                    'FileType','spreadsheet','Sheet',strcat('Age',num2str(AgeDiv(d)), ...
                    'Lag',num2str(Params.FuncConLagval(l)),'ms'));
            end 

        end
    end
end


if strcmp(output_spreadsheet_file_type, 'csv')
    electrode_combined_table = vertcat(electrode_main_table{:});
    electrode_table_savepath = strcat('NetworkActivity_NodeLevel.csv');
    writetable(electrode_combined_table, electrode_table_savepath);
end 

clear DatTemp TempStr

%% GraphMetricsByLag plots
% Tim 2022-01-08: This seems to be independent of the saved table object (?)
cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('5_GraphMetricsByLag')

eMet = {'aN','Dens','CC','nMod', ... 
        'Q','PL','Eglob','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5', ...
        'NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient','number of modules', ...
    'modularity score','path length','global efficiency', ... 
    'small worldness \sigma','small worldness \omega', ... 
    'proportion peripheral nodes','proportion non-hub connectors', ... 
    'proportion non-hub kinless nodes', ... 
    'proportion provincial hubs','proportion connector hubs', ... 
    'proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

assert(length(eMet) == length(eMetl), 'ERROR: eMet and eMetl have different lengths')

for l = 1:length(Params.FuncConLagval)
    LagValLabels{l} = num2str(Params.FuncConLagval(l));
end

p = [100 100 1200 800]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for n = 1:length(eMet)
    if ~isfield(Params, 'oneFigure')
        F1 = figure;
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
            
            % Tim: temp fix
            if isempty(DatTemp)
                DatTemp = zeros(1, length(Params.FuncConLagval));
            end 
            
            % What is c again? What is cDiv1?
            % TODO: what is expected dimensions of DatTemp 
            % I think in here it is DatTemp in (m, n)
            % where m is the number of recordings (for a single genoype????)
            % and n is the number of time lags
            % but currently DatTemp is just a 1 x n vector for me...
            
            ValMean = nanmean(DatTemp,1);
            ValStd = std(DatTemp,1);
            UpperStd = ValMean+ValStd; % upper std line
            LowerStd = ValMean-ValStd; % lower std line
            % What is cDIv1
            Xf =[xt,fliplr(xt)]; % create continuous x value array for plotting
            Yf =[UpperStd,fliplr(LowerStd)]; % create y values for out and then back
            % What is out and then back mean???
            
            % So xt is Functional connectivity lag values counter, but why
            % need to double it??? ie. why Xf goes from 1 2 3 3 2 1 ? But
            % my c only has 3 values?
            % TODO: What is Xf and Yf?
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
            clear DatTemp ValMean ValStd UpperStd LowerStd
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
        saveas(gcf,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt}));
    end 

    % Close figure or clear the one shared figures
    if ~isfield(Params, 'oneFigure')
        close(gcf)
    else
        set(0, 'CurrentFigure', Params.oneFigure);
        clf reset
    end 
end

%% notBoxPlots - plots by group

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('3_RecordingsByGroup'); cd('NotBoxPlots')

eMet = {'aN','Dens','CC','nMod','Q','PL','Eglob','SW','SWw', ... 
    'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient', ... 
    'number of modules','modularity score','path length', ... 
    'global efficiency','small worldness \sigma','small worldness \omega', ... 
    'proportion peripheral nodes','proportion non-hub connectors', ... 
    'proportion non-hub kinless nodes','proportion provincial hubs', ... 
    'proportion connector hubs','proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
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
                
                % Tim: temp fix to make zero vector of DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                
                
                PlotDat = DatTemp(:,l);
                eval(['notBoxPlotRF(PlotDat,xt(d),cDiv' num2str(d) ',12)']);
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

        % Export figure
        for nFigExt = 1:length(Params.figExt)
            saveas(gcf,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt}));
        end 

        % Close figure or clear the one shared figures
        if ~isfield(Params, 'oneFigure')
            close(gcf)
        else
            set(0, 'CurrentFigure', Params.oneFigure);
            clf reset
        end 
    end
    cd(HomeDir); cd(strcat('OutputData',Params.Date));
    cd('4_NetworkActivity'); cd('4B_GroupComparisons')
    cd('3_RecordingsByGroup'); cd('NotBoxPlots')
end

%% halfViolinPlots - plots by group

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('3_RecordingsByGroup'); cd('HalfViolinPlots')

eMet = {'aN','Dens','CC','nMod','Q','PL','Eglob','SW','SWw','NCpn1', ... 
        'NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient','number of modules', ... 
    'modularity score','path length','global efficiency','small worldness \sigma', ... 
    'small worldness \omega','proportion peripheral nodes','proportion non-hub connectors', ... 
    'proportion non-hub kinless nodes','proportion provincial hubs','proportion connector hubs', ... 
    'proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        if ~isfield(Params, 'oneFigure')
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
                
                % Tim: temp fix to make zero vector of DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                
                
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                if isempty(PlotDat)
                    continue
                else
                    eval(['HalfViolinPlot(PlotDat,xt(d),cDiv' num2str(d) ',0.3)']);
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

        % Export figure
        for nFigExt = 1:length(Params.figExt)
            saveas(gcf,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt}));
        end 

        % Close figure or clear the one shared figures
        if ~isfield(Params, 'oneFigure')
            close(gcf)
        else
            set(0, 'CurrentFigure', Params.oneFigure);
            clf reset
        end 
    end
    cd(HomeDir); cd(strcat('OutputData',Params.Date));
    cd('4_NetworkActivity'); cd('4B_GroupComparisons')
    cd('3_RecordingsByGroup'); cd('HalfViolinPlots')
end

%% notBoxPlots - plots by DIV

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('4_RecordingsByAge'); cd('NotBoxPlots')

eMet = {'aN','Dens','CC','nMod','Q','PL','Eglob','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient','number of modules','modularity score','path length','global efficiency','small worldness \sigma','small worldness \omega','proportion peripheral nodes','proportion non-hub connectors','proportion non-hub kinless nodes','proportion provincial hubs','proportion connector hubs','proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)
if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
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
                % Tim: temp fix to make zero vector of DIV is empty 
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
            saveas(gcf,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt}));
        end 

        % Close figure or clear the one shared figures
        if ~isfield(Params, 'oneFigure')
            close(gcf)
        else
            set(0, 'CurrentFigure', Params.oneFigure);
            clf reset
        end 
    end
    cd(HomeDir); cd(strcat('OutputData',Params.Date));
    cd('4_NetworkActivity'); cd('4B_GroupComparisons')
    cd('4_RecordingsByAge'); cd('NotBoxPlots')
end

%% halfViolinPlots - plots by DIV

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('4_RecordingsByAge'); cd('HalfViolinPlots')

eMet = {'aN','Dens','CC','nMod','Q','PL','Eglob','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient','number of modules','modularity score','path length','global efficiency','small worldness \sigma','small worldness \omega','proportion peripheral nodes','proportion non-hub connectors','proportion non-hub kinless nodes','proportion provincial hubs','proportion connector hubs','proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)
if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
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
                % Tim: temp fix to make zero vector of DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                if isempty(PlotDat)
                    continue
                else
                    HalfViolinPlot(PlotDat, xt(g), Params.groupColors(g, :), 0.3);
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
        set(findall(gcf,'-property','FontSize'),'FontSize',12)

        % Export figure
        for nFigExt = 1:length(Params.figExt)
            saveas(gcf,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt}));
        end 

        % Close figure or clear the one shared figures
        if ~isfield(Params, 'oneFigure')
            close(gcf)
        else
            set(0, 'CurrentFigure', Params.oneFigure);
            clf reset
        end 
    end
    cd(HomeDir); cd(strcat('OutputData',Params.Date));
    cd('4_NetworkActivity'); cd('4B_GroupComparisons')
    cd('4_RecordingsByAge'); cd('HalfViolinPlots')
end

   
%% halfViolinPlots - plots by group electrode specific data

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('1_NodeByGroup')

eMet = {'ND','EW','NS','Z','Eloc','PC','BC'}; 
eMetl = {'node degree','edge weight','node strength', ... 
    'within-module degree z-score','local efficiency', ... 
    'participation coefficient','betweeness centrality'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)
if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        if ~isfield(Params, 'oneFigure')
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
                % Tim: temp fix to make zero vector of DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                if isempty(PlotDat)
                    continue
                else
                    eval(['HalfViolinPlot(PlotDat,xt(d),cDiv' num2str(d) ',0.3)']);
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

        % Export figure
        for nFigExt = 1:length(Params.figExt)
            saveas(gcf,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt}));
        end 

         % Close figure or clear the one shared figures
        if ~isfield(Params, 'oneFigure')
            close(gcf)
        else
            set(0, 'CurrentFigure', Params.oneFigure);
            clf reset
        end 
    end
    cd(HomeDir); cd(strcat('OutputData',Params.Date));
    cd('4_NetworkActivity'); cd('4B_GroupComparisons')
    cd('1_NodeByGroup')
end


%% halfViolinPlots - plots by DIV electrode specific data

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('2_NodeByAge')

eMet = {'ND','EW','NS','Z','Eloc','PC','BC'}; 
eMetl = {'node degree','edge weight','node strength','within-module degree z-score','local efficiency','participation coefficient','betweeness centrality'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)
if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
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
                % Tim: temp fix to make zero vector of DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                PlotDat = DatTemp(:,l);
                PlotDat(isnan(PlotDat)) = [];
                if isempty(PlotDat)
                    continue
                else
                    HalfViolinPlot(PlotDat, xt(g), Params.groupColors(g, :), 0.3);
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
        set(findall(gcf,'-property','FontSize'),'FontSize',12)
        
        % Export figure
        for nFigExt = 1:length(Params.figExt)
            saveas(gcf,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),Params.figExt{nFigExt}));
        end 
            

        % Close figure or clear the one shared figures
        if ~isfield(Params, 'oneFigure')
            close(gcf)
        else
            set(0, 'CurrentFigure', Params.oneFigure);
            clf reset
        end 
    end
    cd(HomeDir); cd(strcat('OutputData',Params.Date));
    cd('4_NetworkActivity'); cd('4B_GroupComparisons')
    cd('2_NodeByAge')
end

%% Node cartography

cd(HomeDir); cd(strcat('OutputData',Params.Date))
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('6_NodeCartographyByLag')

c1 = [0.8 0.902 0.310]; % light green
c2 = [0.580 0.706 0.278]; % medium green
c3 = [0.369 0.435 0.122]; % dark green
c4 = [0.2 0.729 0.949]; % light blue
c5 = [0.078 0.424 0.835]; % medium blue
c6 = [0.016 0.235 0.498]; % dark blue

eMet = {'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6'}; 

p = [100 100 1200 800]; % this can be ammended accordingly
set(0, 'DefaultFigurePosition', p)
if isfield(Params, 'oneFigure')
    set(Params.oneFigure, 'Position', p);
end 

for l = 1:length(Params.FuncConLagval)
    if ~isfield(Params, 'oneFigure')
        F1 = figure;
    end 
    xt = 1:length(AgeDiv);
    for g = 1:length(Grps)
        h(g) = subplot(length(Grps),1,g);
        eGrp = cell2mat(Grps(g));
        for n = 1:length(eMet)
            eMeti = char(eMet(n));
            for d = 1:length(AgeDiv)
                eDiv = strcat('TP',num2str(d));
                VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
                eval(['DatTemp = ' VNe ';']);
                % Tim: temp fix to make zero vector of DIV is empty 
                if isempty(DatTemp)
                    DatTemp = zeros(1, length(Params.FuncConLagval));
                end 
                meanTP(d)= nanmean(DatTemp(:,l));
                stdTP(d)= nanstd(DatTemp(:,l));
                xtlabtext{d} = num2str(AgeDiv(d));
            end
            eval(['c = c' num2str(n) ';']);
            UpperStd = meanTP+stdTP; % upper std line
            LowerStd = meanTP-stdTP; % lower std line
            Xf =[xt,fliplr(xt)]; % create continuous x value array for plotting
            Yf =[UpperStd,fliplr(LowerStd)]; % create y values for out and then back
            h1 = fill(Xf,Yf,c,'edgecolor','none');
            % Choose a number between 0 (invisible) and 1 (opaque) for facealpha.
            set(h1,'facealpha',0.3)
            hold on
            eval(['y' num2str(n) '= plot(xt,meanTP,''Color'',c,''LineWidth'',3);']);
            xticks(xt)
            xticklabels(xtlabtext)
            xlabel('Age')
            ylabel('node cartography')
            clear DatTemp meanTP meanSTD ValStd UpperStd LowerStd
        end
        linkaxes(h,'xy')
        h(1).XLim = [min(xt)-0.5 max(xt)+0.5];
        title(eGrp)
        aesthetics
        set(gca,'TickDir','out');
        legend([y1 y2, y3, y4, y5, y6],'proportion peripheral nodes','proportion non-hub connectors','proportion non-hub kinless nodes','proportion provincial hubs','proportion connector hubs','proportion kinless hubs','Location','eastoutside')
        legend Box off
    end

    % Export figure
    for nFigExt = 1:length(Params.figExt)
        saveas(gcf,strcat(['NodeCartography', num2str(Params.FuncConLagval(l)), ...
            'mslag', Params.figExt{nFigExt}]));
    end 


    % Close figure or clear the one shared figures
    if ~isfield(Params, 'oneFigure')
        close(gcf)
    else
        set(0, 'CurrentFigure', Params.oneFigure);
        clf reset
    end 
end

end