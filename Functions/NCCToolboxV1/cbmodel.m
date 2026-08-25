%% CBMODEL - cortical branching model
% Generates cortical branching model data. The network consists of nodes
% arranged in a 2-D lattice on a torus. Each node only interacts with its
% four nearest neighbors. The nodes have no refractory period. Avalanches
% are produce using one of two methods. Method 1: avalanches are seeded at
% a random point in the lattice, allowed to run to completion, and then a
% new avalanches is seeded after a randomly chosen delay period. Method 2:
% a spontaneous activation probability seeds avalanches that may overlap.
%
% Syntax: [asdf2] = cbmodel(p, varargin)
%
% Input:
%   p (scalar double) - the transmission probability from an active node to
%     non-active node.
%
% Variable Inputs:
%   (..., 'method', method) - the avalanche seeding method. method = 'seed'
%     uses that avalanche seeding method. method = 'spont' uses the
%     spontaneous activit method. (string) (default: 'seed')
%   (..., 'nNodes', nNodes) - the number of nodes in the network. Note,
%     nNodes will be rounded up to make a square lattice. (scalar integer)
%     (default: 100)
%   (..., 't', t) - the number of the time steps the network will be
%     allowed to run. (scalar double) (default: 10^6)
%   (..., 'delaydecay', delaydecay) - the exponent of the inverse power law
%     used to determine the delay times between avalanche seedings. (scalar
%     double) (default: 2)
%   (..., 'spontp', spontp) - the spontaneous activation probability.
%     (scalar double) (default: 1/(nNodes^2))
%   (..., 'subsample', nSub) - the number of nodes in the network to record
%     via sub-sampling. (scalar integer) (default: nNodes)
%
% Outputs:
%   asdf2 (structure) - node activation data in standard asdf2 format
%
% Example:
%   asdf2 = cbmodel(0.25, 'nNodes' 200);
%     Generate model data using a transmission probability of 0.25 in a
%     square lattice of 200 nodes.
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%

% Author: Nicholas Timme
% Email: nicholas.m.timme@gmail.com
% June 2015; Last revision: 2-Jun-2015

%==============================================================================
% Copyright (c) 2013, The Trustees of Indiana University
% All rights reserved.
% 
% Redistribution and use in source and binary forms, with or without
% modification, are permitted provided that the following conditions are met:
% 
%   1. Redistributions of source code must retain the above copyright notice,
%      this list of conditions and the following disclaimer.
% 
%   2. Redistributions in binary form must reproduce the above copyright notice,
%      this list of conditions and the following disclaimer in the documentation
%      and/or other materials provided with the distribution.
% 
%   3. Neither the name of Indiana University nor the names of its contributors
%      may be used to endorse or promote products derived from this software
%      without specific prior written permission.
% 
% THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
% AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
% IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
% ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
% LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
% CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
% SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
% INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
% CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
% ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
% POSSIBILITY OF SUCH DAMAGE.


function [asdf2] = cbmodel(p, varargin)
%% Parse command line for parameters
method = 'seed';
nNodes = 100;
t = 10^6;
delaydecay = 2;
spontp = 1/(nNodes^2);
nSub = nNodes;

iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    switch varargin{iVarArg},
        case 'method',       method = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'nNodes',       nNodes = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 't',            t = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'delaydecay',   delaydecay = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'spontp',       spontp = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        case 'subsample',    nSub = varargin{iVarArg+1}; iVarArg = iVarArg + 1;
        otherwise,
            argOkay = false;
    end
    if ~argOkay
        disp(['(CBMODEL) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Prepare necessary variables

% Correct the number of nodes
nNodes = ceil(sqrt(nNodes))^2;
nSide = sqrt(nNodes);

% Make the connectivity matrix
ConMat = zeros([nNodes,nNodes]);
for iNode = 1:nNodes
    [i,j] = ind2sub([nSide,nSide],iNode);
    if i == 1
        ConMat(sub2ind([nSide,nSide],nSide,j),iNode) = 1;
        ConMat(sub2ind([nSide,nSide],i + 1,j),iNode) = 1;
    elseif i == nSide
        ConMat(sub2ind([nSide,nSide],i - 1,j),iNode) = 1;
        ConMat(sub2ind([nSide,nSide],1,j),iNode) = 1;
    else
        ConMat(sub2ind([nSide,nSide],i - 1,j),iNode) = 1;
        ConMat(sub2ind([nSide,nSide],i + 1,j),iNode) = 1;
    end
    if j == 1
        ConMat(sub2ind([nSide,nSide],i,nSide),iNode) = 1;
        ConMat(sub2ind([nSide,nSide],i,j + 1),iNode) = 1;
    elseif j == nSide
        ConMat(sub2ind([nSide,nSide],i,j - 1),iNode) = 1;
        ConMat(sub2ind([nSide,nSide],i,1),iNode) = 1;
    else
        ConMat(sub2ind([nSide,nSide],i,j - 1),iNode) = 1;
        ConMat(sub2ind([nSide,nSide],i,j + 1),iNode) = 1;
    end
end

% Make the raster
raster = false([nSub,t]);


%% Run the model

if nNodes == nSub
    
    % Make the probability conversion vector
    ProbConv = zeros([1,5]);
    for iNode = 1:4
        ProbConv(iNode + 1) = ProbConv(iNode) + p - (ProbConv(iNode)*p);
    end
    
    if strcmp(method,'seed') % Use the seeding method
        
        % Make the delay probability generator vector
        dp = (1:1000).^(-delaydecay);
        dp = cumsum(dp./sum(dp));
        
        iT = 2;
        delayFlag = 0;
        while iT <= t
            
            if ~any(raster(:,iT - 1))
                
                % If the last time step was silent, either seed a new avalanche or
                % wait for the delay
                if delayFlag == 0 % Seed a new avalanche
                    raster(randi(nNodes),iT) = true;
                    iT = iT + 1;
                elseif delayFlag == 1 % Jump forward by a delay period (note, we already had a delay of 1 time step)
                    iT = iT + nnz(dp < rand);
                    delayFlag = 0;
                end
                
                
            else
                
                % Otherwise, determine network activity based on past activity
                Probs = ProbConv((ConMat*raster(:,iT - 1)) + 1)';
                raster(:,iT) = (rand([nNodes,1]) < Probs);
                delayFlag = 1;
                iT = iT + 1;
            end
        end
    elseif strcmp(method,'spont')
        
        iT = 2;
        while iT <= t
            Probs = ProbConv((ConMat*raster(:,iT - 1)) + 1)';
            raster(:,iT) = (rand([nNodes,1]) < Probs);
            raster(rand([nNodes,1]) < spontp,iT) = true;
            iT = iT + 1;
        end
        
        
    else
        error('Improper method chosen.')
    end
    
elseif nNodes > nSub
    
    % Make a list of subsample nodes
    SubList = randperm(nNodes);
    SubList = sort(SubList(1:nSub));
    
    % Make the temporary whole network rasters
    WNPast = false([nNodes,1]);
    WNNow = false([nNodes,1]);
    
    if strcmp(method,'seed') % Use the seeding method
        
        % Make the probability conversion vector
        ProbConv = zeros([1,5]);
        for iNode = 1:4
            ProbConv(iNode + 1) = ProbConv(iNode) + p - (ProbConv(iNode)*p);
        end
        
        % Make the delay probability generator vector
        dp = (1:1000).^(-delaydecay);
        dp = cumsum(dp./sum(dp));
        
        iT = 2;
        delayFlag = 0;
        while iT <= t
            
            if ~any(WNPast)
                
                % If the last time step was silent, either seed a new avalanche or
                % wait for the delay
                if delayFlag == 0 % Seed a new avalanche
                    WNNow(randi(nNodes)) = true;
                    raster(:,iT) = WNNow(SubList);
                    WNPast = WNNow;
                    iT = iT + 1;
                elseif delayFlag == 1 % Jump forward by a delay period (note, we already had a delay of 1 time step)
                    iT = iT + nnz(dp < rand);
                    delayFlag = 0;
                end
                
                
            else
                
                % Otherwise, determine network activity based on past activity
                Probs = ProbConv((ConMat*WNPast) + 1)';
                WNNow = (rand([nNodes,1]) < Probs);
                raster(:,iT) = WNNow(SubList);
                WNPast = WNNow;
                delayFlag = 1;
                iT = iT + 1;
            end
        end
    elseif strcmp(method,'spont')
        
        % Make the probability conversion vector
        ProbConv = zeros([1,5]);
        ProbConv(1) = spontp;
        for iNode = 1:4
            ProbConv(iNode + 1) = ProbConv(iNode) + p - (ProbConv(iNode)*p);
        end
        
        iT = 2;
        
        size(ConMat)
        size(WNPast)
        while iT <= t
            iT
            Probs = ProbConv((ConMat*WNPast) + 1)';
            WNNow = (rand([nNodes,1]) < Probs);
            raster(:,iT) = WNNow(SubList);
            WNPast = WNNow;
            iT = iT + 1;
        end
        
        
    else
        error('Improper method chosen.')
    end
end

%% Put in asdf2 format

asdf2 = struct;
asdf2.binsize = 1;
asdf2.nbins = t;
asdf2.nchannels = nNodes;
asdf2.expsys = 'CBModel';
asdf2.datatype = 'Spikes';
asdf2.dataID = 'ModelX';
asdf2.raster = cell([nSub,1]);
for iNode = 1:nSub
    asdf2.raster{iNode} = find(raster(iNode,:));
end
