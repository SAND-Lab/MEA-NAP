
%{


%}



%% Set parameters

HomeDir = 'D:\MATLAB\Part II Project scripts\NNMF analysis';
cd(HomeDir)
addpath('Functions','Functions\NCCToolboxV1');
% set parameters
Params.fs = 25000; % original sampling frequency, Hz
Params.duration_s = 720;
Params.downsamplefreq = 1; %Hz
Params.N = 10; % minimum number of spikes for network burst
Params.minChannel = 3;  % minimum number of channels for network burst
Params.burstBin = 10; %s
Params.SpikesCostParam = -0.06;
Params.SpikesMethod = 0;
Params.TruncRec = 0;
Params.TruncLength = 0;
Params.Randomisation = 1;
%% Create output folder

formatOut = 'ddmmmyyyy'; Params.Date = datestr(now,formatOut); clear formatOut
CreateOutputFoldersNNMF(HomeDir,Params.Date)

%% Import metadata from spreadsheet

xlsfilename = 'Dataset I.xlsx';
sheet = 1;
xlRange = 'A1:C164';

[num,txt,~] = xlsread(xlsfilename,sheet,xlRange);
ExpName = txt(:,1);
ExpGrp = txt(:,3);
ExpDIV = num(:,1);

[~,Params.GrpNm] = findgroups(ExpGrp);
[~,Params.DivNm] = findgroups(ExpDIV);

for ExN = 1:length(ExpName) 
    
    Info.FN = ExpName(ExN);
    Info.DIV = num2cell(ExpDIV(ExN));
    Info.Grp = ExpGrp(ExN);
    Info.duration_s = 720;
    Info.sampling_rate = 25000;
    
    cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
    save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info')
    cd(HomeDir)
    
end

%% Generate spike matrices

spikeDetectedData = 'D:\MATLAB\Part II Project scripts\NNMF analysis\Dataset I\spikeDetectedData';
addpath(spikeDetectedData)

minSpikeCount = 10;

for ExN = 1:length(ExpName)
    
    cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
    load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info')
    cd(HomeDir)
    disp(char(Info.FN))
    
    cd(spikeDetectedData)
    load(strcat(char(Info.FN),'.mat'),'cSpikes','channels')
    Info.channels = channels';
    clear channels
    cd(HomeDir)
    
    spikeMatrix = full(cSpikes);
    activeElectrodes = sum(cSpikes,1) > minSpikeCount;
%     spikeMatrix = cSpikes(:,activeElectrodes);
    clear cSpikes

% % burst detection
% [burstMatrix,burstTimes,burstChannels] = burstDetect(spikeMatrix, 'Bakkum', Params.fs, Params.N, Params.minChannel);
    
    % downsampled randomised spike matrix
    asdf2 = rastertoasdf2(spikeMatrix',1000,char(Info.Grp),'',char(Info.FN));
    randasdf2 = randomizeasdf2(asdf2,'wrap');
    randSpikeMatrix = asdf2toraster(randasdf2)';
    clear asdf2 randasdf2
    randSpikeMatrix = downSampleSum(randSpikeMatrix,Params.downsamplefreq*Info.duration_s);
        
    % downsampled original spike matrix
    spikeMatrix = downSampleSum(spikeMatrix,Params.downsamplefreq*Info.duration_s);
                
    cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
    save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','activeElectrodes','spikeMatrix','randSpikeMatrix')
    cd(HomeDir)
    clear Info activeElectrodes spikeMatrix randSpikeMatrix

end

%% Burst change plots and extract data for group comparisons
%{
cd(strcat('OutputData',Params.Date)); mkdir('Network bursts'); cd(HomeDir);

% burstGroupComparisons = ExpGrp;
% burstGroupComparisons(:,2) = num2cell(ExpDIV);

for ExN = 1:length(ExpName)

    cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
    load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info','burstChannels','burstTimes')
    cd(HomeDir)

    cd(strcat('OutputData',Params.Date)); cd('Network bursts');
    [burstChangeData,avgBurstRate] = burstChanges(burstTimes,burstChannels,Info,Params);
    save('burstChangeData.mat',"burstChangeData")
%     burstGroupComparisons{ExN,3} = avgBurstRate;
    cd(HomeDir)

%     cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
%     save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','burstChangeData')

end
%}

%%  Find optimal component number

nmfData = ExpGrp;
nmfData(:,2) = num2cell(ExpDIV);
nmf_warning = 'stats:nnmf:LowRank';
for  ExN = 1:length(ExpName)

    cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
    load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info','activeElectrodes','randSpikeMatrix','spikeMatrix')
    cd(HomeDir)
    
    nmfData{ExN,5} = prctile(spikeMatrix,95,'all');
    networkSize = sum(full(activeElectrodes));
    nmfData{ExN,6} = networkSize;
    
    % Just the important bits
    spikePercentile =  prctile(spikeMatrix,95,'all');
    networkSize = sum(full(activeElectrodes));
    
%     % Plot residuals for range of k values
%     residuals = zeros(1,10);
%     randResiduals = zeros(1,10);
%     k_vals = [1:10];
%     for k = k_vals
%         [~, ~, residual] = nnmf(spikeMatrix,k);
%         residuals(k) = residual;
%         [~, ~, randResidual] = nnmf(randSpikeMatrix,k);
%         randResiduals(k) = randResidual;
%     end
%     f = figure;
%     plot(k_vals,residuals,'r')
%     hold on
%     plot(k_vals,randResiduals,'b')
%     hold off
%     cd(strcat('OutputData',Params.Date)); cd('NNMF')
%     saveas(f,strcat(char(Info.FN),'_',Params.Date,'.png'));
%     cd(HomeDir)

    residual = 0; randResidual = 1; k = 1;
    while residual < randResidual && k <= size(spikeMatrix,2)
        [~, ~, residual] = nnmf(spikeMatrix,k);
        [~, msgid] = lastwarn;
        if strcmp(msgid,'nmf_warning')
            break
        end
        [~, ~, randResidual] = nnmf(randSpikeMatrix,k);
        [~, msgid] = lastwarn;
        if strcmp(msgid,'nmf_warning')
            randResidual = Inf;
        end
        k = k+1;
    end
    
    num_nnmf_copmonents = k - 1;

    
    nmfData{ExN,3} = k-1;
    nmfData{ExN,4} = residual;
    nmfData{ExN,7} = (k-1)/networkSize;
    nmfData{ExN,9} = (k-1)/networkSize^2;
end

%% Find mean component size

for  ExN = 1:length(ExpName)

    cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
    load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'spikeMatrix','Info')
    cd(HomeDir)
    
    num_nnmf_components = nmfData{ExN,3};
    if num_nnmf_components == 0
        nmfData{ExN,8} = NaN;
        continue
    end

    componentSize = [];
%     mkdir(strcat(char(Info.FN),Params.Date))
%     cd(strcat(char(Info.FN),Params.Date))

    [W, H] = nnmf(spikeMatrix, num_nnmf_components,'algorithm','mult','replicates',10);

    F3 = figure;
    subplot(num_nnmf_components+1, 1, 1)
    imagesc(spikeMatrix');
    rasterPlotAesthetics
    title('Original data')

    for nnmf_c = 1:num_nnmf_components
        subplot(num_nnmf_components, 1, nnmf_c)
        nnmf_component_matrix = W(:, nnmf_c) * H(nnmf_c, :);

        imagesc(nnmf_component_matrix')
        xticks([1 60:60:duration_s])
        xticklabels({'0','1','2','3','4','5','6','7','8','9','10','11','12'})
        xlabel(t,'Time (min)','FontSize',11)
        title(strcat('Component ', num2str(nnmf_c)))
        
        nnmf_component_matrix(nnmf_component_matrix < 1) = 0;
        participatingElectrodes = sum(nnmf_component_matrix,1) ~= 0;
        nnmf_component_matrix = nnmf_component_matrix(:,sum(nnmf_component_matrix,1) ~= 0);
        componentSize = [componentSize size(nnmf_component_matrix,2)];

        components.(strcat("Component", "_",num2str(nnmf_c))) = nnmf_component_matrix;
        components.(strcat("Component_channels", "_",num2str(nnmf_c))) = participatingElectrodes;
        
        clear nnmf_component_matrix
    end
        
    nmfData{ExN,8} = mean(componentSize);

%     cd(HomeDir)
%     cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
%     save(strcat(char(Info.FN),'_',Params.Date,'.mat'),'Info','spikeMatrix','components')
%     cd(HomeDir)

    clear spikeMatrix W H

end

% cd(strcat('OutputData',Params.Date)); %cd('NNMF')
% 
% save('kValues.mat','kValues')
% kValuesTable = cell2table(kValues ...
%     ,"VariableNames" ...
%     ,["Genotype","Age","Component number","Residual","Max. firing rate","Network size","Component number normalised by number of nodes","Average component size","Component number normalised by number of connections"]);
% writetable(kValuesTable,"kValuesTable.csv")
cd(HomeDir)
%% Plotting component signals and heatmaps

% % Plot original data raster
% rasterPlot(spikeMatrix, Params.duration_s)
% 
% for  ExN = 1:length(ExpName)
% 
%     cd(strcat('OutputData',Params.Date)); cd('ExperimentMatFiles')
%     load(strcat(char(ExpName(ExN)),'_',Params.Date,'.mat'),'Info')
%     cd(HomeDir)
% 
%     cd(strcat('OutputData',Params.Date)); cd('NNMF')
%     cd(strcat(char(Info.FN),Params.Date))
%     load('Components.mat')
%     componentSignals(Info.channels,components,Params.duration_s)
%     componentHeatMaps(Info.channels',components)
% 
%     clear Info components
%     cd(HomeDir)
% 
% end