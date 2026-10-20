function [values] = ave_control(A)
% FUNCTION:
%         Returns values of AVERAGE CONTROLLABILITY for each node in a
%         network, given the adjacency matrix for that network. Average
%         controllability measures the ease by which input at that node can
%         steer the system into many easily-reachable states.
%
% INPUT:
%         A is the structural (NOT FUNCTIONAL) network adjacency matrix, 
% 	      such that the simple linear model of dynamics outlined in the 
%	      reference is an accurate estimate of brain state fluctuations. 
%	      Assumes all values in the matrix are positive, and that the 
%	      matrix is symmetric.
%
% OUTPUT:
%         Vector of average controllability values for each node
%
% Bassett Lab, University of Pennsylvania, 2016. 
% Reference: Gu, Pasqualetti, Cieslak, Telesford, Yu, Kahn, Medaglia,
%            Vettel, Miller, Grafton & Bassett, Nature Communications
%            6:8414, 2015.

A = A./(1+svds(A,1));     % Matrix normalization 
[U, T] = schur(A,'real'); % Schur stability
midMat = (U.^2)';
v = diag(T);
P = repmat(diag(1 - v*v'),1,size(A,1));
values = sum(midMat./P)';