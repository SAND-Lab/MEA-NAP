function [effectiveRank, normEigenV] = calEffRank(spikeMatrix, method) 
%{

Computes Effective Rank of a matrix 

Parameters
------------
spikeMatrix : matrix
    matix of dimensions nSamples x nChannels,   
    containing 0 = no spike, 1 = spike
method : str 
    'covariance' : do eigendecomposition on the covariance matrix 
    'correlation' : do eigendecomposition on the correlation matrix

based on: Roy and Vetterli (2007) 
http://ieeexplore.ieee.org/abstract/document/7098875
%}

% 1. compute covariance matrix 
if strcmp(method, 'covariance')
    if issparse(spikeMatrix)
        covM = sparseCov(spikeMatrix);
    else 
        covM = cov(spikeMatrix);
    end 
elseif strcmp(method, 'correlation')
    % Option B: use correlation matrix 
    covM = corr(spikeMatrix); 
    % PROBLEM: for electrodes where no spikes is detected, corre returns
    % NaN since the variance is 0 and you can't divide by 0 
    % current solution is to replace it with 0 but I am not sure if this is
    % justified 
    covM(isnan(covM)) = 0;
end 

% 2. get eigenvalues of the covariance matrix 
eigenV = eig(covM); 

% 3. interpret the N eigenvalues as a distribution of N integers 
normEigenV = eigenV ./ sum(eigenV);

% 4. compute Shannon entropy of the vector 
sEn = -sum(normEigenV .* log(normEigenV)); 
% note that we are using natural log here 

% 5. take the exponential of the Shannon entropy 
effectiveRank = exp(sEn); 

effectiveRank = real(effectiveRank); 
end 