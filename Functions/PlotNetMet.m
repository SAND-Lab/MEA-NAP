function [] = PlotNetMet(ExpName,Params,HomeDir)

% plot network metrics for MEA data
% author RCFeord July 2021

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
    cDiv1 = colOpt5;
else
    for ii = 1:nDIV
        eval(['cDiv' num2str(ii) '= ColOpt' num2str(round(1+(nColOpt/nDIV)*(ii-1))) ';']);
    end
end

% colours for different groups (WT,HET,KO)
cGrp1 = [0.996 0.670 0.318]; 
cGrp2 = [0.780 0.114 0.114];
cGrp3 = [0.459 0.000 0.376]; 
cGrp4 = [0.027 0.306 0.659]; 

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
NetMetricsE = {'Dens','Q','nMod','Eglob','aN','CC','PL','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 

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

%% export to excel

cd(HomeDir); cd(strcat('OutputData',Params.Date));

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
            writetable(struct2table(DatTemp), strcat('NetworkActivity_RecordingLevel_',eGrp,'.xlsx'),'FileType','spreadsheet','Sheet',strcat('Age',num2str(AgeDiv(d)),'Lag',num2str(Params.FuncConLagval(l)),'ms'));
        end
    end
end

clear DatTemp TempStr

% electrode specific
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
            writetable(struct2table(DatTemp), strcat('NetworkActivity_NodeLevel_',eGrp,'.xlsx'),'FileType','spreadsheet','Sheet',strcat('Age',num2str(AgeDiv(d)),'Lag',num2str(Params.FuncConLagval(l)),'ms'));
        end
    end
end

clear DatTemp TempStr

%% GraphMetricsByLag plots

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('5_GraphMetricsByLag')

eMet = {'aN','Dens','CC','nMod','Q','PL','Eglob','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient','number of modules','modularity score','path length','global efficiency','small worldness \sigma','small worldness \omega','proportion peripheral nodes','proportion non-hub connectors','proportion non-hub kinless nodes','proportion provincial hubs','proportion connector hubs','proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

for l = 1:length(Params.FuncConLagval)
    LagValLabels{l} = num2str(Params.FuncConLagval(l));
end

p = [100 100 1200 800]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

for n = 1:length(eMet)
    F1 = figure;
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
            % Tim Sit 2021-12-02, let me just handle the case where c and
            % Xf have different lengths for now 
            
            if length(c) == length(Xf)
                h1 = fill(Xf,Yf,c,'edgecolor','none');  % This is the original 
            elseif length(c) < length(Xf)
                h1 = fill(Xf(1:length(c)),Yf(1:length(c)),c,'edgecolor','none'); % This is the hacky fix
            end 
            
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
    if Params.figMat == 1
        saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.fig'));
    end
    if Params.figPng == 1
        saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.png'));
    end
    if Params.figEps == 1
        saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.eps'));
    end
    close(F1)
end

%% notBoxPlots - plots by group

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('3_RecordingsByGroup'); cd('NotBoxPlots')

eMet = {'aN','Dens','CC','nMod','Q','PL','Eglob','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient','number of modules','modularity score','path length','global efficiency','small worldness \sigma','small worldness \omega','proportion peripheral nodes','proportion non-hub connectors','proportion non-hub kinless nodes','proportion provincial hubs','proportion connector hubs','proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        F1 = figure;
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
        if Params.figMat == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.fig'));
        end
        if Params.figPng == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.png'));
        end
        if Params.figEps == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.eps'));
        end
        close(F1)
    end
    cd(HomeDir); cd(strcat('OutputData',Params.Date));
    cd('4_NetworkActivity'); cd('4B_GroupComparisons')
    cd('3_RecordingsByGroup'); cd('NotBoxPlots')
end

%% halfViolinPlots - plots by group

cd(HomeDir); cd(strcat('OutputData',Params.Date));
cd('4_NetworkActivity'); cd('4B_GroupComparisons')
cd('3_RecordingsByGroup'); cd('HalfViolinPlots')

eMet = {'aN','Dens','CC','nMod','Q','PL','Eglob','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'network size','density','clustering coefficient','number of modules','modularity score','path length','global efficiency','small worldness \sigma','small worldness \omega','proportion peripheral nodes','proportion non-hub connectors','proportion non-hub kinless nodes','proportion provincial hubs','proportion connector hubs','proportion kinless hubs','hub nodes 2','hub nodes 1'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        F1 = figure;
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
        if Params.figMat == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.fig'));
        end
        if Params.figPng == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.png'));
        end
        if Params.figEps == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.eps'));
        end
        close(F1)
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

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        F1 = figure;
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
                eval(['notBoxPlotRF(PlotDat,xt(g),cGrp' num2str(g) ',12)']);
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
        if Params.figMat == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.fig'));
        end
        if Params.figPng == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.png'));
        end
        if Params.figEps == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.eps'));
        end
        close(F1)
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

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        F1 = figure;
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
                    eval(['HalfViolinPlot(PlotDat,xt(g),cGrp' num2str(g) ',0.3)']);
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
        if Params.figMat == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.fig'));
        end
        if Params.figPng == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.png'));
        end
        if Params.figEps == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.eps'));
        end
        close(F1)
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
eMetl = {'node degree','edge weight','node strength','within-module degree z-score','local efficiency','participation coefficient','betweeness centrality'}; 

p = [100 100 1300 600]; 
set(0, 'DefaultFigurePosition', p)

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        F1 = figure;
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
        if Params.figMat == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.fig'));
        end
        if Params.figPng == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.png'));
        end
        if Params.figEps == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.eps'));
        end
        close(F1)
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

for l = 1:length(Params.FuncConLagval)
    mkdir(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    cd(strcat(num2str(Params.FuncConLagval(l)),'mslag'))
    for n = 1:length(eMet)
        F1 = figure;
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
                    eval(['HalfViolinPlot(PlotDat,xt(g),cGrp' num2str(g) ',0.3)']);
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
        if Params.figMat == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.fig'));
        end
        if Params.figPng == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.png'));
        end
        if Params.figEps == 1
            saveas(F1,strcat(num2str(n),'_',regexprep(char(eMetl(n)),'\',''),'.eps'));
        end
        close(F1)
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

for l = 1:length(Params.FuncConLagval)
    F1 = figure;
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
    if Params.figMat == 1
        saveas(F1,strcat('NodeCartography',num2str(Params.FuncConLagval(l)),'mslag.fig'));
    end
    if Params.figPng == 1
        saveas(F1,strcat('NodeCartography',num2str(Params.FuncConLagval(l)),'mslag.png'));
    end
    if Params.figEps == 1
        saveas(F1,strcat('NodeCartography',num2str(Params.FuncConLagval(l)),'mslag.eps'));
    end
    close(F1)
end

end