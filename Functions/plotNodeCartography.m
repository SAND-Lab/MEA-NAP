function NetMet = plotNodeCartography(adjMs, Params, NetMet, Info, HomeDir)
%{
Parameters
----------
adjMs : struct 
    structure where each field contains a cell, which represents the
    collection of adjacency matrices obtained from a particular time lag

Params : struct 
Info : struct
HomeDir : str
    path to the home directory

Returns 
-------


%}

lagval = Params.FuncConLagval;
edge_thresh = 0.0001;
cd(char(Info.FN))

%% Individual node cartography plots 

for e = 1:length(lagval)

    % change to lag val subfolder to save plots 
    cd(strcat(num2str(lagval(e)),'mslag'))
    
    % load adjM
    adjM = adjMs.(strcat('adjM', num2str(lagval(e)), 'mslag'));

    adjM(adjM<0) = 0;
    adjM(isnan(adjM)) = 0;

    % subset active nodes
    
    aNtemp = sum(adjM,1);
    iN = find(aNtemp==0);
    aNtemp(aNtemp==0) = [];
    aN = length(aNtemp);
    
    adjM(iN,:) = [];
    adjM(:,iN) = [];

    [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
    [On,adjMord] = reorder_mod(adjM,Ci);

    % extract node cartography
    PC = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).PC;
    Z = NetMet.(strcat('adjM', num2str(lagval(e)), 'mslag')).Z;
    [NdCartDiv, PopNumNC] = NodeCartography(Z, PC, lagval, e, char(Info.FN), Params); 

    PopNumNCt(e,:) = PopNumNC;
    
    NCpn1 = PopNumNC(1)/aN;
    NCpn2 = PopNumNC(2)/aN;
    NCpn3 = PopNumNC(3)/aN;
    NCpn4 = PopNumNC(4)/aN;
    NCpn5 = PopNumNC(5)/aN;
    NCpn6 = PopNumNC(6)/aN;

    % node cartography
    NdCartDivOrd = NdCartDiv(On);
    StandardisedNetworkPlotNodeCartography(adjMord, Params.coords, ... 
        edge_thresh, NdCartDivOrd, 'circular', char(Info.FN), '7', Params, lagval, e)

    % add node cartography results to existing experiment file 
    nodeCartVarsToSave = {'NCpn1', 'NCpn2','NCpn3','NCpn4','NCpn5','NCpn6'};
    nodeCartVarsVals = {NCpn1, NCpn2, NCpn3, NCpn4, NCpn5, NCpn6};
    
    for varCounter = 1:length(nodeCartVarsToSave)
        lagValField = strcat('adjM', num2str(lagval(e)), 'mslag');
        varName = nodeCartVarsToSave{varCounter};
        NetMet.(lagValField).(varName) = nodeCartVarsVals{varCounter};
    end
    
    cd(HomeDir); cd(strcat('OutputData',Params.Date)); 
    cd('4_NetworkActivity'); cd('4A_IndividualNetworkAnalysis'); 
    cd(char(Info.Grp)); cd(char(Info.FN))

end 

%% Plot node catography proportions 
plotNodeCartographyProportions(NetMet, lagval, char(Info.FN), Params)


end 