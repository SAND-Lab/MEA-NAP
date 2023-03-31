function NetMet = plotNodeCartography(adjMs, Params, NetMet, Info, HomeDir, fileNameFolder)
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


%}

lagval = Params.FuncConLagval;
edge_thresh = 0.0001;

%% Individual node cartography plots 

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
    adjM = adjM(inclusionIndex, inclusionIndex);
    coords = Params.coords(inclusionIndex, :);
    Params.netSubsetChannels = Params.channels(inclusionIndex);


    [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    [On,adjMord] = reorder_mod(adjM,Ci);

    % extract node cartography
    PC = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).PC;
    Z = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).Z;

    % TODO Check if oneFigure object exists here, if not create it again 
    % Params.oneFigure = figure();
    [NdCartDiv, PopNumNC] = NodeCartography(Z, PC, lagval, e, char(Info.FN), Params); 

    PopNumNCt(e,:) = PopNumNC;
    
    NCpn1 = PopNumNC(1)/aN;
    NCpn2 = PopNumNC(2)/aN;
    NCpn3 = PopNumNC(3)/aN;
    NCpn4 = PopNumNC(4)/aN;
    NCpn5 = PopNumNC(5)/aN;
    NCpn6 = PopNumNC(6)/aN;
    
    if aN >= Params.minNumberOfNodesToCalNetMet
        % node cartography in circular plot
        NdCartDivOrd = NdCartDiv(On);
        StandardisedNetworkPlotNodeCartography(adjM, coords, ... 
            edge_thresh, NdCartDivOrd, 'circular', char(Info.FN), '7', Params, lagval, e, lagFolder)

        % node cartography in grid plot 
        StandardisedNetworkPlotNodeCartography(adjM, coords, ... 
            edge_thresh, NdCartDiv, 'MEA', char(Info.FN), '7', Params, lagval, e, lagFolder)

        % add node cartography results to existing experiment file 
        nodeCartVarsToSave = {'NCpn1', 'NCpn2','NCpn3','NCpn4','NCpn5','NCpn6'};
        nodeCartVarsVals = {NCpn1, NCpn2, NCpn3, NCpn4, NCpn5, NCpn6};

        for varCounter = 1:length(nodeCartVarsToSave)
            lagValField = strcat('adjM', num2str(lagval(e)), 'mslag');
            varName = nodeCartVarsToSave{varCounter};
            NetMet.(lagValField).(varName) = nodeCartVarsVals{varCounter};
        end
    else 
        fprintf('Warning: not enough active nodes to plot node cartography \n')
    end

end 

%% Plot node catography proportions 
plotNodeCartographyProportions(NetMet, lagval, char(Info.FN), Params, lagFolder)


end 