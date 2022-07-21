function [values] = modal_control(A)
% FUNCTION:
%         Returns values of MODAL CONTROLLABILITY for each node in a
%         network, given the adjacency matrix for that network. Modal
%         controllability indicates the ability of that node to steer the
%         system into difficult-to-reach states, given input at that node.
%
% INPUT:
%         A is the structural (NOT FUNCTIONAL) network adjacency matrix, 
% 	  such that the simple linear model of dynamics outlined in the 
%	  reference is an accurate estimate of brain state fluctuations. 
%	  Assumes all values in the matrix are positive, and that the 
%	  matrix is symmetric.
%
% OUTPUT:
%         Vector of modal controllability values for each node
%
% Bassett Lab, University of Pennsylvania, 2016. 
% Reference: Gu, Pasqualetti, Cieslak, Telesford, Yu, Kahn, Medaglia,
%            Vettel, Miller, Grafton & Bassett, Nature Communications
%            6:8414, 2015.

A = A./(1+svds(A,1));       % Matrix normalization 
[U, T] = schur(A,'real');   % Schur stability
eigVals = diag(T);
N = size(A,1);
phi = zeros(N,1);
for i = 1 : N
    phi(i) = (U(i,:).^2) * (1 - eigVals.^2);
end
values = phi;