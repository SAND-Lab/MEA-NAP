function covX = sparseCov(X)
%SPARSECOV Calculates covariance for sparse matrix 
% The Covariance formula is cov(x) = E[x * x'] - E[x] E[x]' 
% see https://stackoverflow.com/questions/32106370/corr-with-sparse-matrix-matlab

% this is faster, but approximate population moments E[x*x'] with 
% sample moements X' * X / n and mean(X)
% [n, k]  = size(X);
% Exxprim = full(X'*X)/n; 
% Ex   = full(mean(X))'; 
% covX = (Exxprim - Ex*Ex');

% STDEVX = sqrt(diag(COVX));
% CORRX = COVX ./ (STDEVX * STDEVX');

% This is more accuate, but less efficient.
% still faster than cov on non-sparse matrix 
% XX = bsxfun(@minus,X,full(mean(X)));
XX = X - full(mean(X));
covX = XX'*XX/(size(X,1)-1);

% the returned result is not identical to COV
% but from my data it the difference is small: -4.1972e-12
end