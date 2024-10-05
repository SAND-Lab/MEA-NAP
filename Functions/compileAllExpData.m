function allExpData = compileAllExpData(ExpName, experimentMatFileFolder, Params, metricLevel)
%COMPILENETWORKLEVELDATA Combines data from multiple NetMet structures
% INPUT 
% ------------
% ExpName : cell 
%    cell where each entry is the name (without extension) of a file to
%    compile the data for 
% experimentMatFileFolder : path 
%    path to folder with the ExpMat .mat files 
% Params : struct 
%    structure with the following fields 
%    Params.DivNm : vector
%    Params.networkLevelNetMetToPlot : cell 
% metricLevel : str 
%    either 'network' to compiile network-level features
%        or 'node' to compile node-level features

allExpData = struct();

if isempty(Params.customGrpOrder)
    Grps = Params.GrpNm;
else
    if ~isempty(Params.customGrpOrder)
        Grps = Params.customGrpOrder;
    else
        Grps = Params.GrpNm;
    end 
end 

AgeDiv = Params.DivNm;

%% Variable names

if strcmp(metricLevel, 'network')
    % list of metrics that are obtained at the network level
    NetMetVarNames = Params.networkLevelNetMetToPlot;
elseif strcmp(metricLevel, 'node') 
    % list of metrics that are obtained at the electrode level
    NetMetVarNames = Params.unitLevelNetMetToPlot;
    NetMetVarNames{end+1} = 'activeChannel';
end

%% Import data from all experiments - whole experiment  

for g = 1:length(Grps)
    % create structure for each group
    groupName = cell2mat(Grps(g));
    % eval([VN1 '= [];']);
    % networkLevelData.(groupName) = [];
    
    % add substructure for each DIV range
    for d = 1:length(AgeDiv)
        % VN2 = strcat('TP',num2str(d));
        timePointName = strcat('TP',num2str(d));
        
        % add variable name
        for e = 1:length(NetMetVarNames)
            % VN3 = cell2mat(NetMetricsE(e));
            netMetName = cell2mat(NetMetVarNames(e));
            allExpData.(groupName).(timePointName).(netMetName) = [];
            % eval([VN1 '.' VN2 '.' VN3 '= [];']);
            % clear VN3
        end
        % clear VN2
    end
    % clear VN1
end

% allocate numbers to relevant matrices
for i = 1:length(ExpName)
     %  Exp = strcat(char(ExpName(i)),'_',Params.Date,'.mat');
     Exp = char(ExpName(i));
     
     % Search for any .mat file with the Exp str (regardless of date)
     ExpFPathSearchName = dir(fullfile(experimentMatFileFolder, [Exp, '*.mat'])).name;
     ExpFPath = fullfile(experimentMatFileFolder, ExpFPathSearchName);
     expFileData = load(ExpFPath);  
     % filepath contains Info structure
     
     if ~isfield(expFileData, 'NetMet')
         fprintf(sprintf('%s has no NetMet field, file idx %.f', Exp, i))
     end 
     
     eGrp = expFileData.Info.Grp{1};

     for d = 1:length(AgeDiv)
         if cell2mat(expFileData.Info.DIV) == AgeDiv(d)
             eDiv = strcat('TP',num2str(d));
         end    
     end
     
     for e = 1:length(NetMetVarNames)
            eMet = cell2mat(NetMetVarNames(e));
            for lagIdx = 1:length(Params.FuncConLagval)
                % VNs = strcat('NetMet.adjM',num2str(Params.FuncConLagval(l)),'mslag.',eMet);
                if contains(eMet, Params.lagIndependentMets)
                    firstLagField = sprintf('adjM%.fmslag', Params.FuncConLagval(1));
                    DatTemp(lagIdx) = expFileData.NetMet.(firstLagField).(eMet);
                else
                    if strcmp(metricLevel, 'network')
                        DatTemp(lagIdx) = expFileData.NetMet.(strcat('adjM', num2str(Params.FuncConLagval(lagIdx)), 'mslag')).(eMet);
                    else 
                        tempLagField = ['lag' num2str(lagIdx)];
                        DatTempStruct.(tempLagField) = expFileData.NetMet.(strcat('adjM', num2str(Params.FuncConLagval(lagIdx)), 'mslag')).(eMet);
                        maxLength(lagIdx) = length(DatTempStruct.(tempLagField));
                    end
                end 
            end 
            
            if strcmp(metricLevel, 'node')
                % For node level data, fill empty values with NaNs
                % (hopefully no need to this most of the time...)
                for lagIdx = 1:length(Params.FuncConLagval)
                    tempLagField = ['lag' num2str(lagIdx)];
                    DatTempT = DatTempStruct.(tempLagField);
                    if length(DatTempT) < max(maxLength)
                        DatTempT((length(DatTempT)+1):max(maxLength)) = nan;
                    end
                    DatTemp(:,lagIdx) = DatTempT;
                    numNodeInExp = size(DatTemp, 1);
                end
            end 

            allExpData.(eGrp).(eDiv).(eMet) = [ ...
            allExpData.(eGrp).(eDiv).(eMet); DatTemp];
            clear DatTemp
     end
     
     % Also include recording name 
     if strcmp(metricLevel, 'node') 
         if ~isfield(allExpData.(eGrp).(eDiv), 'recordingNamePerElectrode')
             allExpData.(eGrp).(eDiv).recordingNamePerElectrode = {};
         end
         allExpData.(eGrp).(eDiv).recordingNamePerElectrode = [ ...
             allExpData.(eGrp).(eDiv).recordingNamePerElectrode; ...
             repmat({Exp}, numNodeInExp, 1) ...
         ];
     elseif strcmp(metricLevel, 'network') 
         if ~isfield(allExpData.(eGrp).(eDiv), 'recordingName')
             allExpData.(eGrp).(eDiv).recordingName = {};
         end
         allExpData.(eGrp).(eDiv).recordingName = [ ...
             allExpData.(eGrp).(eDiv).recordingName; ...
             {Exp}
         ];
     end 
     
     clear Info NetMet adjMs
end

end

