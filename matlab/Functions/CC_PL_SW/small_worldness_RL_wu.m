function [SW,w,CC,PLn] = small_worldness_RL_wu(A,R,L)
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