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