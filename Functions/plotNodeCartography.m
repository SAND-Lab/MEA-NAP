function NetMet = plotNodeCartography(adjMs, Params, NetMet, Info, originalCoords, ...
    originalChannels, HomeDir, fileNameFolder, oneFigureHandle)
% Plot individual node cartography plots per recording. 
% Part of Step 4A of MEANAP.
% Parameters
% ----------
% adjMs : struct 
%     structure where each field contains a cell, which represents the
%     collection of adjacency matrices obtained from a particular time lag
% Params : struct 
%     Parameter structure
% Info : struct
%     File information structure 
%     with fields: FN (filename without .mat extension, as a string), 
%     DIV (days in vitro, as a integer) and Grp (group name, as a string)
% HomeDir : str
%     path to the home directory
% originalCoords : double 
%       matrix of size (numElectorde, 2) 
%       with the coordinates of each electrode in a 8 x 8 grid 
%       (ie. values are expected to be within 0 - 8)
% originalChannels: double 
%       vector of size (1, numElectrode)
%       the integer ID of each channel 
% fileNameFolder : str 
%       path to the folder to save the step 4A plot
% oneFigureHandle : matlab.ui.Figure
%       matlab figure handle to make the node cartography plot
% Returns 
% -------
% NetMet : struct 
% 

lagval = Params.FuncConLagval;

%% Individual node cartography plots 

for e = 1:length(lagval)

    % change to lag val subfolder to save plots
    lagFolder = fullfile(fileNameFolder, strcat(num2str(lagval(e)),'mslag'));
    if ~isfolder(lagFolder)
        mkdir(lagFolder)
    end 
    
    % load adjM and Ci 
    adjM = adjMs.(strcat('adjM', num2str(lagval(e)), 'mslag'));
    % Ci = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).Ci;

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

    [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
        
    % NOTE: This currently works only if adjM has the same size across
    % DIVs...
    if Params.ExpNameGroupUseCoord == 1
        [On,adjMord] = reorder_mod(adjM,Ci);  % On is the re-odering index
        NetMet.(sprintf('AnchoredReorderingIndex%.fmslag', lagval(e))) = On;
    else 
        On = NetMet.(sprintf('AnchoredReorderingIndex%.fmslag', lagval(e)));
        adjMord = adjM(On, On);
    end
    
    % Get edge threshold 
    edge_thresh = getEdgeThreshold(adjMord, Params);

    % extract node cartography
    PC = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).PC;
    Z = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).Z;

    [NdCartDiv, PopNumNC] = NodeCartography(Z, PC, lagval, e, char(Info.FN), Params, lagFolder, oneFigureHandle); 
    
    % Include inactive nodes and assign them to group 7 
    NdCartDivFull = zeros(length(adjM), 1) + 7;
    NdCartDivFull(inclusionIndex) = NdCartDiv;
    NdCartDiv = NdCartDivFull;
    
    % TODO: these steps need to be moved and saved (esp. NdCartDivFull) in 
    % earlier step 4 step to prevent having to re-analyze the data

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
        % node cartography in circular plot
        NdCartDivOrd = NdCartDiv(On);
        Params.channelsReordered = Params.netSubsetChannels(On);
        StandardisedNetworkPlotNodeCartography(adjMord, coords, ... 
            edge_thresh, NdCartDivOrd, 'circular', char(Info.FN), '9', Params, lagval, e, lagFolder, oneFigureHandle, '_modules')
        
        % node cartography in circular plot same order across DIV
        Params.channelsReordered = Params.netSubsetChannels;  % back to original order
        StandardisedNetworkPlotNodeCartography(adjM, coords, ... 
            edge_thresh, NdCartDiv, 'circular', char(Info.FN), '9', Params, lagval, e, lagFolder, oneFigureHandle, '')

        % node cartography in grid plot 
        StandardisedNetworkPlotNodeCartography(adjM, coords, ... 
            edge_thresh, NdCartDiv, 'MEA', char(Info.FN), '9', Params, lagval, e, lagFolder, oneFigureHandle, '_modules')

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

%% Plot node catography proportions 
plotNodeCartographyProportions(NetMet, lagval, char(Info.FN), Params, fileNameFolder, oneFigureHandle)


end 