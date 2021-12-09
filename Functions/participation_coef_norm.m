function [PC_norm,PC_residual,PC,between_mod_k] = participation_coef_norm(W,Ci,n_iter,par_comp)
%PARTICIPATION_COEF_NORM
%
%   [PC_norm,PC_residual,PC,between_mod_k] = participation_coef_norm(W,Ci,n_iter,par_comp);
%
%   Participation Coefficient (Guimera and Amaral 2005,Nature,433:895-900) is a measure
%   of diversity of intermodular connections of individual nodes. This function use a network
%   randomization approach that preserve degree distribution (Maslov and Sneppen 2002,Science,296:910),
%   aimed reduce the influence of intra-modular connectivity, compared to original Participation Coefficient.
%
%   Reference: Pedersen M, Omidvarnia A, Shine J.M, Jackson G.J, Zalesky A. 2019. bioRxiv. DOI: 10.1101/747162.
%
%   Inputs:     W,                      binary and undirected connectivity matrix
%               Ci,                     community affiliation vector
%               n_iter (optional),      number of matrix randomizations (default = 100)
%               par_comp (optional),    0 = don't compute matrix randomizations in a parallel loop (default = 0)
%                                       1 = compute matrix randomizations in a parallel loop
%
%   Output:     PC_norm,                Normalized Participation Coefficient using randomizations
%               PC_residual,            Residual Participation Coefficient from linear regression
%               PC,                     Original Participation Coefficient
%               between_mod_k,          Between-module degree
%
%   This function needs 'null_model_und_sign' (undirected network) and 'randmio_dir' (directed network) available
%   in the Brain Connectivity Toolbox (BCT - https://sites.google.com/site/bctnet/measures/list)
%
%   2008-2019
%   Mika Rubinov, UNSW
%   Alex Fornito, University of Melbourne
%   Mangor Pedersen, The Florey Institute of Neuroscience and Mental Health/University of Melbourne
%
%   Modification History:
%   Jul 2008: Original (Mika Rubinov)
%   Mar 2011: Weighted-network bug fixes (Alex Fornito)
%   Feb 2019: Normalized version of Participation Coefficient (Mangor Pedersen)

%% Preamble
clc; theElapsedTime = tic; % clear the MATLAB command window, and initialize timing of function
 
if nargin < 3 % if n_iter input is missing, then compute function with 100 matrix randomizations
    n_iter = 100;
end
 
if nargin < 4 % if par_comp input is missing, then compute function without parallel computing
    par_comp = 0;
end
 
fprintf('\n\t - Running Normalized Participation Coefficient with %g randomizations... \n',n_iter);
 
%% First calculate the original Participation Coefficient
n = length(W); %number of vertices
Ko = sum(W,2); %(out)degree
Gc = (W~=0)*diag(Ci); %neighbor community affiliation
 
Kc2 = zeros(n,1);
within_mod_k = zeros(n,1);
for i=1:max(Ci)
    Kc2 = Kc2+(sum(W.*(Gc==i),2).^2); % squared intra-modular degree
    within_mod_k(Ci==i) = sum(W(Ci==i,Ci==i),2); % within-module degree
end

between_mod_k = Ko - within_mod_k; % [network-wide degree ?? within-module degree = between-module degree]
PC = ones(n,1)-Kc2./(Ko.^2); % calculate participation coefficeint.
PC(~Ko) = 0; % PC = 0 for nodes with no (out)neighbors

%% Now over to Normalized Participation Coefficient
Kc2_rnd = zeros(n,n_iter); % initialize randomized intra-modular degree array
 
if par_comp == 0 % no parallel computing
    reverseStr = '';
    for ii = 1:n_iter % number of randomizations
        if issymmetric(W) == 1 % check whether network is undirected (1) or directed (0)
            W_rnd = null_model_und_sign(W,5); % randomize each undirected network five times, preserving degree distribution of original matrix
        else
            W_rnd = randmio_dir(W,5); % randomize directed network five times, preserving degree distribution of original matrix
        end
         
        Gc_rnd = (W_rnd~=0)*diag(Ci); % neighbor community affiliation
        Kc2_rnd_loop = zeros(n,1); % initialize randomized intramodular degree vector - for current iteration only
 
        for iii = 1:max(Ci) % Below we estimate the squared difference between original and randomised intramodular degree, for each module
            Kc2_rnd_loop = Kc2_rnd_loop+(((sum(W.*(Gc==iii),2)./Ko)-(sum(W_rnd.*(Gc_rnd==iii),2)./Ko)).^2);
            
        end
         
        Kc2_rnd(:,ii) = sqrt(0.5.*Kc2_rnd_loop); % 0.5 * square root of intramodular degree between original and randomised network
         
        msg = sprintf('\n\t - Randomization %d of %d (%g percent done) ...\n',ii,n_iter,round((ii/n_iter)*100)); % on-sceen progress report (including %-completed)
        fprintf([reverseStr,msg]); reverseStr = repmat(sprintf('\b'),1,length(msg));
    end
else % parallel computing
    parfor ii = 1:n_iter % number of randomizations
       if issymmetric(W) == 1 % check whether network is undirected (1) or directed (0)
            W_rnd = null_model_und_sign(W,5); % randomize each undirected network five times, preserving degree distribution of original matrix
        else
            W_rnd = randmio_dir(W,5); % randomize directed network five times, preserving degree distribution of original matrix
        end
         
        Gc_rnd = (W_rnd~=0)*diag(Ci); % neighbor community affiliation
        Kc2_rnd_loop = zeros(n,1); % initialize randomized intramodular degree vector - for current iteration only
 
        for iii = 1:max(Ci) % Below we estimate the squared difference between original and randomised intramodular degree, for each module
            Kc2_rnd_loop = Kc2_rnd_loop+(((sum(W.*(Gc==iii),2)./Ko)-(sum(W_rnd.*(Gc_rnd==iii),2)./Ko)).^2);
 
        end
         
        Kc2_rnd(:,ii) = sqrt(0.5.*Kc2_rnd_loop); % 0.5 * square root of intramodular degree between original and randomised network
         
    end
end
 
PC_norm = ones(n,1)-median(Kc2_rnd,2); % calculate normalized participation coefficient
PC_norm(~Ko) = 0; % PC_norm = 0 for nodes with no (out)neighbors

p = polyfit(sum(Ci==Ci')',PC,1); % linear regression (IV=module size; DV=participation coefficient)
yfit = polyval(p,sum(Ci==Ci')'); % best fit of regression
PC_residual = PC-yfit; % residual participation coefficient
PC_residual(~Ko) = 0; % PC_regress = 0 for nodes with no (out)neighbors

% fprintf('\n\t - Elapsed time: %g minutes \n',toc(theElapsedTime)/60); % on-screen information how long the function took to complete (in minutes)
end