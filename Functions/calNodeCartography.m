function NetMet = calNodeCartography(adjMs, Params, NetMet, Info, originalCoords, ...
    originalChannels, HomeDir, fileNameFolder, oneFigureHandle)
%
% Parameters
% ----------
% adjMs : struct 
%     structure where each field contains a cell, which represents the
%     collection of adjacency matrices obtained from a particular time lag
% 
% Params : struct 
% Info : struct
% HomeDir : str
%     path to the home directory
% 
% Returns 
% -------


lagval = Params.FuncConLagval;
edge_thresh = 0.0001;

%% Individual node cartography calculations 

for e = 1:length(lagval)

    % change to lag val subfolder to save plots
    lagFolder = fullfile(fileNameFolder, strcat(num2str(lagval(e)),'mslag'));
    if ~isfolder(lagFolder)
        mkdir(lagFolder)
    end 
    
    % load adjM
    adjM = adjMs.(strcat('adjM', num2str(lagval(e)), 'mslag'));

    adjM(adjM<0) = 0;
    adjM(isnan(adjM)) = 0;

    % subset active nodes
    
    aNtemp = sum(adjM,1);
    iN = find(aNtemp==0);
    aNtemp(aNtemp==0) = [];
    aN = length(aNtemp);
    
    % adjM(iN,:) = [];
    % adjM(:,iN) = [];

    % Tim 2022-10-14 fix
    nodeStrength = sum(adjM, 1);
    inclusionIndex = find(nodeStrength ~= 0);
    
    % Exclude Inactive Electrodes
    % adjM = adjM(inclusionIndex, inclusionIndex);
    % coords = originalCoords(inclusionIndex, :);
    % Params.netSubsetChannels = originalChannels(inclusionIndex);
    
    % Use all coords and channels (will make them black/white instead)
    % adjM = adjM(inclusionIndex, inclusionIndex);
    coords = originalCoords;
    Params.netSubsetChannels = originalChannels;
    
    if length(adjM) > 1
        [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    else 
        Ci = 0;
        Q = 0;
    end 

    % extract node cartography
    PC = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).PC;
    Z = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).Z;

   [NdCartDiv, PopNumNC] = NodeCartography(Z, PC, lagval, e, char(Info.FN), Params, lagFolder, oneFigureHandle); 
    
    % Include inactive nodes and assign them to group 7 
    NdCartDivFull = zeros(length(adjM), 1) + 7;
    NdCartDivFull(inclusionIndex) = NdCartDiv;
    NdCartDiv = NdCartDivFull;

    PopNumNCt(e,:) = PopNumNC;
    
    NCpn1 = PopNumNC(1)/aN;
    NCpn2 = PopNumNC(2)/aN;
    NCpn3 = PopNumNC(3)/aN;
    NCpn4 = PopNumNC(4)/aN;
    NCpn5 = PopNumNC(5)/aN;
    NCpn6 = PopNumNC(6)/aN;
    
    NCpn1count = PopNumNC(1);
    NCpn2count = PopNumNC(2);
    NCpn3count = PopNumNC(3);
    NCpn4count = PopNumNC(4);
    NCpn5count = PopNumNC(5);
    NCpn6count = PopNumNC(6);
    
    
    if aN >= Params.minNumberOfNodesToCalNetMet
        % add node cartography results to existing experiment file 
        nodeCartVarsToSave = {'NCpn1', 'NCpn2','NCpn3','NCpn4','NCpn5','NCpn6', ...
                              'NCpn1count', 'NCpn2count', 'NCpn3count', ...
                              'NCpn4count', 'NCpn5count', 'NCpn6count'};
        nodeCartVarsVals = {NCpn1, NCpn2, NCpn3, NCpn4, NCpn5, NCpn6, ...
                            NCpn1count, NCpn2count, NCpn3count, ...
                            NCpn4count, NCpn5count, NCpn6count};

        for varCounter = 1:length(nodeCartVarsToSave)
            lagValField = strcat('adjM', num2str(lagval(e)), 'mslag');
            varName = nodeCartVarsToSave{varCounter};
            NetMet.(lagValField).(varName) = nodeCartVarsVals{varCounter};
        end
    else 
        fprintf('Warning: not enough active nodes to plot node cartography \n')
        % add NaNs to the NCpn fields
        nodeCartVarsToSave = {'NCpn1', 'NCpn2','NCpn3','NCpn4','NCpn5','NCpn6', ...
                              'NCpn1count', 'NCpn2count', 'NCpn3count', ...
                              'NCpn4count', 'NCpn5count', 'NCpn6count'};
        for varCounter = 1:length(nodeCartVarsToSave)
            lagValField = strcat('adjM', num2str(lagval(e)), 'mslag');
            varName = nodeCartVarsToSave{varCounter};
            NetMet.(lagValField).(varName) = nan;
        end
    end

end 



end 