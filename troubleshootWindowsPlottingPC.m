% temp code 

lagval = [10, 15, 20, 25, 30, 50, 100];

e = 7;

lagValStr = strcat('adjM', num2str(lagval(e)), 'mslag');
adjM = adjMs.(lagValStr);
adjM(adjM<0) = 0;
adjM(isnan(adjM)) = 0;
aNtemp = sum(adjM,1);
iN = find(aNtemp==0);
aNtemp(aNtemp==0) = [];
aN = length(aNtemp);

clear aNtemp

adjM(iN,:) = [];
adjM(:,iN) = [];

%% node degree, edge weight, node strength

[ND,EW] = findNodeDegEdgeWeight(adjM,edge_thresh);

% Modularity
try
    [Ci,Q,~] = mod_consensus_cluster_iterate(adjM,0.4,50);
catch
    Ci = 0;
    Q = 0;
end
nMod = max(Ci);

[PC,~,~,~] = participation_coef_norm(adjM,Ci);

StandardisedNetworkPlotNodeColourMap(adjM, Params.coords, edge_thresh, ND, 'Node degree', PC, 'Participation coefficient', 'MEA', char(Info.FN), '4', Params, lagval,e)
  