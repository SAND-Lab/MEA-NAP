function [] = PlotNetMetOrganoid(ExpName)

% plot network metrics for organoid data
% author RCFeord September 2020

%% colours

% c1 = [0.027 0.306 0.659]; % dark blue
% c2 = [0.306 0.745 0.933]; % light blue 
% c3 = [0.471 0.674 0.188]; % green
% c4 = [0.929 0.694 0.122]; % yellow

c1 = [0.996 0.670 0.318]; 
c2 = [0.780 0.114 0.114];
c3 = [0.459 0.000 0.376]; 
c4 = [0.027 0.306 0.659]; % dark blue
%% groups and DIV

% Grps = {'CS30','EpiC','WTsli42','H9'};
Grps = Params.GrpNm;
% AgeDiv = {'85' '150';  '300' '399'; '400' '499'; '500' '700'};
AgeDiv = Params.DivNm;
% AgeDiv = {101 132 138 163 150 180 193 286 365 371 619};

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
NetMetricsC = {'ND','EW','NS','Ci','Eloc','BC','PC','Z'};

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
     Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
     load(Exp)
     for g = 1:length(Grps)
         if strcmp(cell2mat(Grps(g)),cell2mat(Info.Grp))
             eGrp = cell2mat(Grps(g));
         end       
     end
     for d = 1:length(AgeDiv)
         if (cell2mat(Info.DIV) >= str2num(AgeDiv{d,1})) && (cell2mat(Info.DIV) <= str2num(AgeDiv{d,2}))
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

%% plots

eMet = {'Dens','Q','nMod','Eglob','aN','CC','PL','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'Density','Modularity score','Number of modules','Global efficiency','Network size','clustering coefficient','path length','small worldness (old)','small worldness (new)','Proportion peripheral nodes','Proportion non-hub connectors','Proportion non-hub kinless nodes','Proportion provincial hubs','Proportion connector hubs','Proportion kinless hubs','Hub nodes 3','Hub nodes 4'}; 

p = [100 100 600 400]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

g = 1; %WT
eGrp = cell2mat(Grps(g));
for n = 1:length(eMet)
    F1 = figure;
    eMeti = char(eMet(n));
    for d = 1:length(AgeDiv)
        
        eval(['c = c' num2str(d) ';']);
        eDiv = strcat('TP',num2str(d));
        
        VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
        eval(['DatTemp = ' VNe ';']);
        
        ValMean = nanmean(DatTemp,1);
        ValStd = std(DatTemp,1);
        X = [1 2 3 ]; % x-axis values
        UpperStd = ValMean+ValStd; % upper std line
        LowerStd = ValMean-ValStd; % lower std line
        Xf =[X,fliplr(X)]; % create continuous x value array for plotting
        Yf =[UpperStd,fliplr(LowerStd)]; % create y values for out and then back
        h = fill(Xf,Yf,c,'edgecolor','none');
        % Choose a number between 0 (invisible) and 1 (opaque) for facealpha.
        set(h,'facealpha',0.3)
        hold on
        plot(X,ValMean,'Color',c,'LineWidth',3)
        xticks([1 2 3])
        xticklabels({'10','15','25','30','40','45'})
        xlabel('STTC lag (ms)')
        ylabel(eMetl(n))
        xlim([0.8 3.2])
        clear DatTemp ValMean ValStd UpperStd LowerStd
    end
%     ylim([0 0.6])
    set(findall(gcf,'-property','FontSize'),'FontSize',15)
    saveas(F1,strcat(char(eMet(n)),'.png'));
    close(F1)
end

%% notBoxPlots

eMet = {'Dens','Q','nMod','Eglob','aN','CC','PL','SW','SWw','NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6','Hub3','Hub4'}; 
eMetl = {'Density','Modularity score','Number of modules','Global efficiency','Network size','clustering coefficient','path length','small worldness (old)','small worldness (new)','Proportion peripheral nodes','Proportion non-hub connectors','Proportion non-hub kinless nodes','Proportion provincial hubs','Proportion connector hubs','Proportion kinless hubs','Hub nodes 3','Hub nodes 4'}; 

p = [100 100 600 600]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

g = 1; %WT
eGrp = cell2mat(Grps(g));
y = [1 1.5 2 2.5];
for n = 1:length(eMet)
    F1 = figure;
    eMeti = char(eMet(n));
    for d = 1:length(AgeDiv)
        eval(['c = c' num2str(d) ';']);
        eDiv = strcat('TP',num2str(d));
        VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
        eval(['DatTemp = ' VNe ';']);
        PlotDat = DatTemp(:,3);
        eval(['notBoxPlotRF(PlotDat,y(d),c' num2str(d) ',12)']);
        xticks([1 1.5 2 2.5])
        xticklabels({'85-250', '251-299', '300-399'})
        xlabel('DIV')
        ylabel(eMetl(n))
        clear DatTemp ValMean ValStd UpperStd LowerStd
    end
%     ylim([-1 1])
     set(findall(gcf,'-property','FontSize'),'FontSize',15)
   saveas(F1,strcat(char(eMet(n)),'.png'));
    close(F1)
end


%% Node cartography

c1 = [0.8 0.902 0.310]; % light green
c2 = [0.580 0.706 0.278]; % medium green
c3 = [0.369 0.435 0.122]; % dark green
c4 = [0.2 0.729 0.949]; % light blue
c5 = [0.078 0.424 0.835]; % medium blue
c6 = [0.016 0.235 0.498]; % dark blue

eMet = {'NCpn1','NCpn2','NCpn3','NCpn4','NCpn5','NCpn6'}; 

p = [100 100 600 400]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

F1 = figure;
for n = 1:length(eMet)
    eMeti = char(eMet(n));
    for d = 1:length(AgeDiv)
        eDiv = strcat('TP',num2str(d));
        VNe = strcat(eGrp,'.',eDiv,'.',eMeti);
        eval(['DatTemp = ' VNe ';']);
        meanTP(d)= mean(DatTemp(:,3));
        stdTP(d)= std(DatTemp(:,3));
    end
    
    eval(['c = c' num2str(n) ';']);
    X = [1 2 3]; % x-axis values
    UpperStd = meanTP+stdTP; % upper std line
    LowerStd = meanTP-stdTP; % lower std line
    Xf =[X,fliplr(X)]; % create continuous x value array for plotting
    Yf =[UpperStd,fliplr(LowerStd)]; % create y values for out and then back
    h = fill(Xf,Yf,c,'edgecolor','none');
    % Choose a number between 0 (invisible) and 1 (opaque) for facealpha.
    set(h,'facealpha',0.3)
    hold on
    plot(X,meanTP,'Color',c,'LineWidth',3)
    xticks([1 2 3])
    xticklabels({'85-250', '251-299', '300-399'})
    xlabel('DIV')
    ylabel('node cartography')
    xlim([0.8 3.2])
    clear DatTemp meanTP meanSTD ValStd UpperStd LowerStd
end
saveas(F1,'NodeCartography.fig');
close(F1)





%% Import data from all experiments - individual cell

% create empty matrices for all variables
for e = 1:length(ExpInfoC)
    VN = cell2mat(ExpInfoC(e));
    eval([VN '= [];']);
    clear VN
end

lCat = length(NetMetricsC);
for n = 1:lCat
    VN = NetMetricsC(n);
    VN = cell2mat(VN);
    eval([VN '= [];']);
    clear VN
end

% import variables from all experiments
for i = 1:length(ExpList)
    Exp = ExpList(i).name;
    load(Exp)
    nCell = size(NetMet.NodeDeg,1);
    
    % experiment info
    for n = 1:length(ExpInfoC)
        VN = cell2mat(ExpInfoC(n));
        for c = 1:nCell
            eval([VN '=[' VN  '; Info.' VN '];']);
        end
        clear VN
    end
    
    % metrics
    lCat = length(NetMetricsC);
    for n = 1:lCat
        VN = NetMetricsC(n);
        VN = cell2mat(VN);
        SVN = strcat(['NetMet.' VN]);
        eval([VN '=[' VN  '; ' SVN '];']);
        clear VN SVN
    end
    
    clear Info NetMet
end

% break down data into variables for genotype and age specificity

lCat = length(NetMetricsC);
% create variables
for n = 1:lCat
    VNA = NetMetricsC(n);
    VNA = cell2mat(VNA);
    for j = 1:length(Grps)
        VNB = cell2mat(Grps(j));
        for l = 1:size(AgeDiv,1)
            VNC = strcat('TP',num2str(l));
            eval([VNB '.' VNC '.' VNA '= [];']);
        end
    end
end
% allocate numbers to relevant matrices
RefVar = NetMetricsC(1);
RefVar = cell2mat(RefVar);
eval(['tCellNum = length(' RefVar ');']);
for n = 1:lCat
    VNA = NetMetricsC(n);
    VNA = cell2mat(VNA);
    for i = 1:tCellNum
        for j = 1:length(Grps)
            VNB = cell2mat(Grps(j));
            Gntp = char(Grp(i,:));
            TF = strcmp(VNB,Gntp);
            if TF == 1
                for l = 1:size(AgeDiv,1)
                    VNC = strcat('TP',num2str(l));
                    DIVrange1 = AgeDiv{l,1};
                    DIVrange2 = AgeDiv{l,2};
                    DIVr(1) = str2num(DIVrange1);
                    DIVr(2) = str2num(DIVrange2);
                    DIVv = DIV(i,:);
                    if (DIVv >= DIVr(1)) && (DIVv <= DIVr(2))
                        eval([VNB '.' VNC '.' VNA '= [' VNB '.' VNC '.' VNA ';' VNA '(i)];']);
                    end
                    clear DIVrange1 DIVrange2 DIVr DIVv
                end
            end
            clear TF
        end
    end
end


clear VN VNA VNB VNC Genotype DIV

%% Plots
% this section plots a subset of the variables, but can be adapted to plot
% any variation/combination of metrics

% first row of plots
Vars1 = {'NetSize','pHubCell','Dens'};
Vars1yLab= {'Active network size','Percentage of hub nodes','Density'};
% second row of plots
Vars2 = {'NodeDegHubGr', 'CCHubGr', 'SWHubGr'};
Vars2yLab = {'Node degree', 'Clustering coefficient', 'Small world topology'};

rowL = max([length(Vars1) length(Vars2)]); % one row might be longer than other
% nAgeDiv = size(AgeDiv,1); % number of age bins
nAgeDiv = 1;

p = [100 100 1200 600]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

F1 = figure;

for i = 1:length(Vars1)
    subplot(2,rowL,i)
    VN = cell2mat(Vars1(i));
    VNyLab = cell2mat(Vars1yLab(i));
    
    for t = 1:nAgeDiv
       eval(['notBoxPlotRF(CS30.TP' num2str(t) '.' VN ',1+3*(t-1),c1,8)']);
        eval(['notBoxPlotRF(EpiC.TP' num2str(t) '.' VN ',1.75+5*(t-1),c2,8)']);
        eval(['notBoxPlotRF(WTsli42.TP' num2str(t) '.' VN ',2.5+5*(t-1),c3,8)']);
        eval(['notBoxPlotRF(H9.TP' num2str(t) '.' VN ',3.25+5*(t-1),c4,8)'])
    
%     eval(['fMin = min([min(WT.TP' num2str(t) '.' VN ') min(KO.TP' num2str(t) '.' VN ')]);']);
%     eval(['fMax = max([max(WT.TP' num2str(t) '.' VN ') max(KO.TP' num2str(t) '.' VN ')]);']);
%    eval(['fMin = min([min(WT.TP' num2str(t) '.' VN ') min(HET.TP' num2str(t) '.' VN ') min(KO.TP' num2str(t) '.' VN ')]);']);
%     eval(['fMax = max([max(WT.TP' num2str(t) '.' VN ') max(HET.TP' num2str(t) '.' VN ') max(KO.TP' num2str(t) '.' VN ')]);']);
  
    end
    
    % x-y axis limits
%     xlim([0 2+2*(t-1)+1])
%     if fMin>0
%         ylim([0 fMax+0.3*fMax])
%     else
%         ylim([fMin-0.3*fMin fMax+0.3*fMax])
%     end
    
    % plot labels
    ylabel(VNyLab)
    
end

for i = 1:length(Vars2)
    subplot(2,rowL,i+rowL)
    VN = cell2mat(Vars2(i));
    VNyLab = cell2mat(Vars2yLab(i));
    
    
    for t = 1:nAgeDiv
        eval(['HalfViolinPlot(CS30.TP' num2str(t) '.' VN ',1+5*(t-1),c1,0.3)']);
        eval(['HalfViolinPlot(EpiC.TP' num2str(t) '.' VN ',2+5*(t-1),c2,0.3)']);
        eval(['HalfViolinPlot(WTsli42.TP' num2str(t) '.' VN ',3+5*(t-1),c3,0.3)']);
        eval(['HalfViolinPlot(H9.TP' num2str(t) '.' VN ',4+5*(t-1),c4,0.3)']);
%        
%         eval(['fMin = min([min(WT.TP' num2str(t) '.' VN ') min(HET.TP' num2str(t) '.' VN ') min(KO.TP' num2str(t) '.' VN ')]);']);
%         eval(['fMax = max([max(WT.TP' num2str(t) '.' VN ') max(HET.TP' num2str(t) '.' VN ') max(KO.TP' num2str(t) '.' VN ')]);']);
%         eval(['fMin = min([min(WT.TP' num2str(t) '.' VN ') min(KO.TP' num2str(t) '.' VN ')]);']);
%         eval(['fMax = max([max(WT.TP' num2str(t) '.' VN ') max(KO.TP' num2str(t) '.' VN ')]);']);
    end
    
    % x-y axis limits
%     xlim([0 3+2*(t-1)+1])
%     if fMin>0
%         ylim([0 fMax+0.3*fMax])
%     else
%         ylim([fMin-0.3*fMin fMax+0.3*fMax])
%     end
    
    % plot labels
    ylabel(VNyLab)
end

% saveas(F1,'MetricsStats.fig');
% close(F1)

%% Whole experiment plots

Vars = {'NetSize','pHubCell','Dens','Assort','PL','Q','nMod','Eglob'}; 
VarsLab = {'network size','percentage of hub cells','density','assortativity','mean path length','modularity score','number of modules','global efficiency'};

nAgeDiv = size(AgeDiv,1); % number of age bins

p = [100 100 450 350]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

for i = 1:length(Vars)
    F1 = figure;
  
    VN = cell2mat(Vars(i));
    VNyLab = cell2mat(VarsLab(i));
    
    for t = 1:nAgeDiv
        for n = 1:size(Grps,2)
            VNG = cell2mat(Grps(n));
            VNGb = strcat(VNG,'.TP',num2str(t),'.',VN);
            eval(['VNG' num2str(n) ' = VNGb;']);
            clear VNG VNGb
        end
        eval(['notBoxPlotRF(' VNG1 ',1+6*(t-1),c1,8)']);
        eval(['notBoxPlotRF(' VNG2 ',2+6*(t-1),c2,8)']);
        eval(['notBoxPlotRF(' VNG3 ',3+6*(t-1),c3,8)']);
        eval(['notBoxPlotRF(' VNG4 ',4+6*(t-1),c4,8)']);
    end
    
    eval(['fMin = min([min(' VNG1 ') min(' VNG2 ') min(' VNG3 ') min(' VNG4 ')]);']);
    eval(['fMax = max([max(' VNG1 ') max(' VNG2 ') max(' VNG3 ') max(' VNG4 ')]);']);
    
    % x-y axis limits
    xlim([0 4+2*(t-1)+1])
    if fMin>0
        ylim([0 fMax+0.3*fMax])
    else
        ylim([fMin-0.3*fMin fMax+0.3*fMax])
    end
    
    % plot labels
    ylabel(VNyLab)
    xticks([1 2 3 4])
    xticklabels(Grps)

end

%% Single node plots

Vars = {'NodeDeg','EdgeWeight','CC','SW','Eloc','BC','PC'};
VarsLab = {'node degree','edge weight','normalised clustering coefficient','small world topology','local efficiency','betweenness centrality','particiaption coefficient'};

DatSubGr = {'HubGr'};
VarsSubGr = {};
for i = 1:length(Vars)
    for t = 1:length(DatSubGr)
        VN = strcat(cell2mat(Vars(i)), cell2mat(DatSubGr(t)));
        VarsSubGr = [VarsSubGr VN];
    end
end
clear VN

nAgeDiv = size(AgeDiv,1); % number of age bins

p = [100 100 900 350]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

for i = 1:length(Vars)
    F1 = figure;
    
    subplot(1,2,1)
    VN = cell2mat(Vars(i));
    VNyLab = cell2mat(VarsLab(i));
    
    for t = 1:nAgeDiv
        for n = 1:size(Grps,2)
            VNG = cell2mat(Grps(n));
            VNGb = strcat(VNG,'.TP',num2str(t),'.',VN);
            eval(['VNG' num2str(n) ' = VNGb;']);
            clear VNG VNGb
        end
        eval(['HalfViolinPlot(' VNG1 ',1+6*(t-1),c1,0.3)']);
        eval(['HalfViolinPlot(' VNG2 ',2+6*(t-1),c2,0.3)']);
        eval(['HalfViolinPlot(' VNG3 ',3+6*(t-1),c3,0.3)']);
        eval(['HalfViolinPlot(' VNG4 ',4+6*(t-1),c4,0.3)']);
    end
    
    eval(['fMin = min([min(' VNG1 ') min(' VNG2 ') min(' VNG3 ') min(' VNG4 ')]);']);
    eval(['fMax = max([max(' VNG1 ') max(' VNG2 ') max(' VNG3 ') max(' VNG4 ')]);']);
    
    % x-y axis limits
    xlim([0 4+2*(t-1)+1])
    if fMin>0
        ylim([0 fMax+0.3*fMax])
    else
        ylim([fMin-0.3*fMin fMax+0.3*fMax])
    end
    
    % plot labels
    ylabel(VNyLab)
    xticks([1 2 3 4])
    xticklabels(Grps)
    title('all data')
    
    subplot(1,2,2)
    VN = cell2mat(VarsSubGr(i));
    VNyLab = cell2mat(VarsLab(i));
    
    for t = 1:nAgeDiv
        for n = 1:size(Grps,2)
            VNG = cell2mat(Grps(n));
            VNGb = strcat(VNG,'.TP',num2str(t),'.',VN);
            eval(['VNG' num2str(n) ' = VNGb;']);
            clear VNG VNGb
        end
        eval(['HalfViolinPlot(' VNG1 ',1+6*(t-1),c1,0.3)']);
        eval(['HalfViolinPlot(' VNG2 ',2+6*(t-1),c2,0.3)']);
        eval(['HalfViolinPlot(' VNG3 ',3+6*(t-1),c3,0.3)']);
        eval(['HalfViolinPlot(' VNG4 ',4+6*(t-1),c4,0.3)']);
    end
    
    % x-y axis limits
    xlim([0 4+2*(t-1)+1])
    if fMin>0
        ylim([0 fMax+0.3*fMax])
    else
        ylim([fMin-0.3*fMin fMax+0.3*fMax])
    end
    
    % plot labels
    ylabel(VNyLab)
    xticks([1 2 3 4])
    xticklabels(Grps)
    title('hub nodes')
end


%% H9 DIV evolution

Vars = {'NodeDeg','EdgeWeight','CC','SW','Eloc','BC','PC'};
VarsLab = {'node degree','edge weight','normalised clustering coefficient','small world topology','local efficiency','betweenness centrality','particiaption coefficient'};

DatSubGr = {'HubGr'};
VarsSubGr = {};
for i = 1:length(Vars)
    for t = 1:length(DatSubGr)
        VN = strcat(cell2mat(Vars(i)), cell2mat(DatSubGr(t)));
        VarsSubGr = [VarsSubGr VN];
    end
end
clear VN

nAgeDiv = size(AgeDiv,1); % number of age bins

p = [100 100 900 350]; % this can be ammended accordingly 
set(0, 'DefaultFigurePosition', p)

for i = 1:length(Vars)
    F1 = figure;
    
%     subplot(1,2,1)
    VN = cell2mat(Vars(i));
    VNyLab = cell2mat(VarsLab(i));
    
    for t = 1:nAgeDiv
        for n = 4
            VNG = cell2mat(Grps(n));
            VNGb = strcat(VNG,'.TP',num2str(t),'.',VN);
            eval(['VNG' num2str(t) ' = VNGb;']);
            clear VNG VNGb
        end 
    end
    
    eval(['HalfViolinPlot(' VNG1 ',1,[0.8 0.8 0.8],0.3)']);
    eval(['HalfViolinPlot(' VNG2 ',2,[0.6 0.6 0.6],0.3)']);
    eval(['HalfViolinPlot(' VNG3 ',3,[0.4 0.4 0.4],0.3)']);
    eval(['HalfViolinPlot(' VNG4 ',4,[0.2 0.2 0.2],0.3)']);
    eval(['HalfViolinPlot(' VNG6 ',5,[0 0 0],0.3)']);

    eval(['fMin = min([min(' VNG1 ') min(' VNG2 ') min(' VNG3 ') min(' VNG4 ') min(' VNG6 ')]);']);
    eval(['fMax = max([max(' VNG1 ') max(' VNG2 ') max(' VNG3 ') min(' VNG4 ') min(' VNG6 ')]);']);
    
    % x-y axis limits
    xlim([0 6])
    if fMin>0
        ylim([0 fMax+0.3*fMax])
    else
        ylim([fMin-0.3*fMin fMax+0.3*fMax])
    end
    
    % plot labels
    ylabel(VNyLab)
    xlabel('DIV')
    xticks([1 2 3 4 5])
    xticklabels({'85-130','135-180','200-299','300-399','500-600'})
    title('all data')
    
%     subplot(1,2,2)
%     VN = cell2mat(VarsSubGr(i));
%     VNyLab = cell2mat(VarsLab(i));
%     
%     for t = 1:nAgeDiv
%         for n = 4
%             VNG = cell2mat(Grps(n));
%             VNGb = strcat(VNG,'.TP',num2str(t),'.',VN);
%             eval(['VNG' num2str(t) ' = VNGb;']);
%             clear VNG VNGb
%         end 
%     end
%     eval(['HalfViolinPlot(' VNG1 ',1,[0.8 0.8 0.8],0.3)']);
%     eval(['HalfViolinPlot(' VNG2 ',2,[0.4 0.4 0.4],0.3)']);
%     eval(['HalfViolinPlot(' VNG3 ',3,[0 0 0],0.3)']);
%     % x-y axis limits
%     xlim([0 4])
%     if fMin>0
%         ylim([0 fMax+0.3*fMax])
%     else
%         ylim([fMin-0.3*fMin fMax+0.3*fMax])
%     end
%     
%     % plot labels
%     ylabel(VNyLab)
%     xlabel('DIV')
%     xticks([1 2 3])
%     xticklabels({'<200','200-400','>400'})
%     title('hub nodes')
end

end
