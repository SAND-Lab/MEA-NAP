%% Generate adjacency matrices and calculate normalized path length 

numNetworks = 10;
numNodes = 60;
numTimeSamples = 1000;

PL_old = nan(numNetworks, 1);
PL_new = nan(numNetworks, 1);
CC_old = nan(numNetworks, 1);
CC_new = nan(numNetworks, 1);
SW_old = nan(numNetworks, 1);
SW_new = nan(numNetworks, 1);

adjMstore = {};

for iNetwork = 1:numNetworks 
    fprintf(sprintf('Calculating network %.f \n', iNetwork))
    tic
    activity = rand(numTimeSamples, numNodes);
    adjM = corr(activity);
    adjM(adjM < 0) = 0;
    adjM = adjM .* ~eye(length(adjM));  % remove self connections

    ITER = 10000;
    Z = pdist(adjM);
    D = squareform(Z);
    % TODO: rename L to Lattice to avoid confusion with path length
    [LatticeNetwork,Rrp,ind_rp,eff,met] = latmio_und_v2(adjM,ITER,D,'SW');
    % [LatticeNetwork,Rrp,ind_rp,eff] = latmio_und(adjM, ITER, D);

    % Random rewiring model (d)
    ITER = 5000;
    [R, ~,met2] = randmio_und_v2(adjM, ITER,'SW');
    % [R, ~] = randmio_und(adjM, ITER);
    
    [SW_old_i, w_old_i, CC_old_i, PL_old_i] = small_worldness_RL_wu_old(adjM, R, LatticeNetwork);
    [SW_new_i, w_new_i, CC_new_i, PL_new_i] = small_worldness_RL_wu_new(adjM, R, LatticeNetwork);

    SW_old(iNetwork) = SW_old_i;
    CC_old(iNetwork) = CC_old_i;
    PL_old(iNetwork) = PL_old_i;

    SW_new(iNetwork) = SW_new_i;
    CC_new(iNetwork) = CC_new_i;
    PL_new(iNetwork) = PL_new_i;
    
    adjMstore{iNetwork} = adjM;

    toc
end 

%% Plot results 

figure;
SW_unity_val = linspace(min(SW_old(:)), max(SW_old(:)), 100);
plot(SW_unity_val, SW_unity_val);
hold on
scatter(SW_old(:), SW_new(:));
xlabel('old SW')
ylabel('new SW')


figure;
PL_unity_val = linspace(min(PL_old(:)), max(PL_old(:)), 100);
plot(PL_unity_val, PL_unity_val);
hold on
scatter(PL_old(:), PL_new(:));
xlabel('old PL')
ylabel('new PL')

figure;
CC_unity_val = linspace(min(CC_old(:)), max(CC_old(:)), 100);
plot(CC_unity_val, CC_unity_val);
hold on
scatter(CC_old(:), CC_new(:));
xlabel('old CC')
ylabel('new CC')

%% Same network but run the randomisation a few times 
% adjMstore = load('testAdjM2.mat');
% adjM = adjMstore.adjMstore{1};

NetMet = load('/Users/timothysit/Dropbox/tempData/HP_tc048_DIV14_18Jul2023.mat');
adjM = NetMet.adjMs.adjM50mslag;

numRandomisations = 10;
PL_store = zeros(numRandomisations, 1);

for randomisationIndex = 1:numRandomisations
    fprintf(sprintf(['Randomisation %.f \n'], randomisationIndex))
    tic
    ITER = 10000;
    Z = pdist(adjM);
    D = squareform(Z);
    [LatticeNetwork,Rrp,ind_rp,eff] = latmio_und(adjM, ITER, D);
    ITER = 5000;
    [R, ~] = randmio_und(adjM, ITER);
    [SW_new_i, w_new_i, CC_new_i, PL_new_i] = small_worldness_RL_wu_new(adjM, R, LatticeNetwork);
    PL_store(randomisationIndex) = PL_new_i;
    toc
end 

%% Old path length function 
function [SW,w,CC,PLn] = small_worldness_RL_wu_old(A,R,L)
%SMALL_WORLDNESS_RL_WU     Small-worldness
%
%   [w,CC,PLi] = small_worldness_RL_wu(A,R,L);
%
%   The value of small-worldness, w, is between -1 and 1. Values close to 
%   0 have small-world properties; values close to 1 have random 
%   properties; values close to -1 have lattice-like properties.
%
%
%   Input:      A,     actual network adjacency matrix.
%               R,     randomized null model adjacency matrix.
%               L,     lattice-like null model adjacency matrix.
%
%   Output:     w,      small-wordness value, between -1 and 1.
%               CC,     normalized clustering coefficient.
%               PLi,    normalized path length.
%
%
%
%   Reference: Telesford et al. (2011b)
%
%   Uses code from clustering_coef_wu, written by Mika Rubinov,  
%   UNSW/U Cambridge, 2007-2015. It also includes other functions from the 
%   Brain Connectivity Toolbox (BCT).
%   
%
%   Lance Burn, Cambridge, 2021
%
%
%   Modification history:
%   2021: original


K=sum(A~=0,2);            	
cyc3=diag((A.^(1/3))^3);           
K(cyc3==0)=inf;             %if no 3-cycles exist, make C=0 (via K=inf)
Cc=cyc3./(K.*(K-1));        %real clustering coefficient
C = mean(Cc);

K=sum(L~=0,2);            	
cyc3=diag((L.^(1/3))^3);           
K(cyc3==0)=inf;             %if no 3-cycles exist, make C=0 (via K=inf)
Ccl=cyc3./(K.*(K-1));       %lattice null model clustering coefficient
Cl = mean(Ccl);

K=sum(R~=0,2);            	
cyc3=diag((R.^(1/3))^3);           
K(cyc3==0)=inf;             %if no 3-cycles exist, make C=0 (via K=inf)
Ccr=cyc3./(K.*(K-1));       %lattice null model clustering coefficient
Cr = mean(Ccr);


Ln = weight_conversion(A, 'lengths');
D = distance_wei(Ln);
PL = charpath(D,0,0);       %real path length

Ln = weight_conversion(R, 'lengths');
D = distance_wei(Ln);
PLr = charpath(D,0,0);      %random null model path length

PLn = PL/PLr;
PLi = (PLr/PL);             %normalized path length (inverted)
CC = (C/Cl);                %normalized clustering coefficient
SW = (C/Cr)/(PL/PLr);
w = (PLi) - (CC);           %small world coefficient, w


end

%% New path length function 
function [SW,w,CC,PLn] = small_worldness_RL_wu_new(A,R,L)
%SMALL_WORLDNESS_RL_WU     Small-worldness
%
%   [w,CC,PLi] = small_worldness_RL_wu(A,R,L);
%
%   The value of small-worldness, w, is between -1 and 1. Values close to 
%   0 have small-world properties; values close to 1 have random 
%   properties; values close to -1 have lattice-like properties.
%
%
%   Input:      A,     actual network adjacency matrix.
%               R,     randomized null model adjacency matrix.
%               L,     lattice-like null model adjacency matrix.
%
%   Output:     w,      small-wordness value, between -1 and 1.
%               CC,     normalized clustering coefficient.
%               PLi,    normalized path length.
%
%
%
%   Reference: Telesford et al. (2011b)
%
%   Uses code from clustering_coef_wu, written by Mika Rubinov,  
%   UNSW/U Cambridge, 2007-2015. It also includes other functions from the 
%   Brain Connectivity Toolbox (BCT).
%   
%
%   Lance Burn, Cambridge, 2021
%
%
%   Modification history:
%   2021: original
% Hugo Smith, July 2023

%% Clustering
% Clustering coefficient: real network
K=sum(A~=0,2);            	
cyc3=diag((A.^(1/3))^3);           
K(cyc3==0)=inf;             %if no 3-cycles exist, make C=0 (via K=inf)
Cc=cyc3./(K.*(K-1));        %real clustering coefficient
C = mean(Cc);

% Clustering coefficient: lattice model
K=sum(L~=0,2);            	
cyc3=diag((L.^(1/3))^3);           
K(cyc3==0)=inf;             %if no 3-cycles exist, make C=0 (via K=inf)
Ccl=cyc3./(K.*(K-1));       %lattice null model clustering coefficient
Cl = mean(Ccl);

% Clustering coefficient: random model
K=sum(R~=0,2);            	
cyc3=diag((R.^(1/3))^3);           
K(cyc3==0)=inf;             %if no 3-cycles exist, make C=0 (via K=inf)
Ccr=cyc3./(K.*(K-1));       %lattice null model clustering coefficient
Cr = mean(Ccr);

% Normalised clustering coefficient
CC = (C - Cr) / (Cl - Cr); % Sprons & Zwi method


%% Path length
% Path length: real network
Ln = weight_conversion(A, 'lengths');
D = distance_wei(Ln);
PL = charpath(D,0,0);       %real path length

% Path length: lattice model
Ln = weight_conversion(L, 'lengths');
D = distance_wei(Ln);
PLl = charpath(D,0,0);

% Path length: random model
Ln = weight_conversion(R, 'lengths');
D = distance_wei(Ln);
PLr = charpath(D,0,0);      %random null model path length

% Normalised path length
PLn = (PL - PLr) / (PLl - PLr); % Sporns & Zwi method

%% Small wordness sigma
% https://pubmed.ncbi.nlm.nih.gov/18446219/
SW = (C / Cr) / (PL / PLr);

%% Small worldness omega
% https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3604768/
P_norm_v2 = PLr / PL;
C_norm_v2 = C / Cl;
w = P_norm_v2 - C_norm_v2;

end