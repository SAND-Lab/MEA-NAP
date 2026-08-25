%% BETHELATTICE - generates Bethe Lattice data
% Generates data from a Bethe Lattice (otherwise known as a branching
% process). Only short duration avalanches are recorded with lattice site
% IDs (neuron IDs) due to the large number of possible sites in large
% processes. Each site in the lattice branches to two new unique sites.
% There are no recurrent connections. Activity propagates through the
% lattice at the speed of one time bin per connection.
%
% Syntax:   [asdf2,fullsizes,fulldurs,fullshapes] = bethelattice(pTrans, nTrials, StopLayer, StopLayerFinal)
%
% Inputs:
%   pTrans (double) - a value from 0 to 1 that determines the likelihood
%       that activity propogates from an active site to one of its
%       descendents. 
%   nTrials (integer) - the number of network runs to generate.
%   StopLayer (integer) - the maximum duration avalanche for which the
%       identity of the active sites will be recorded. Due to the
%       exponential growth in the number of sites in succeeding layers,
%       this number should be kept to less than 15.
%   StopLayerFinal (integer) - the maximum duration avalanche that will be
%       generated. Avalanches with durations longer than StopLayer will
%       only have their size, duration, and shape recorded. 
%
% Output:
%   asdf2 (structure array) - time raster information in the standard
%       format. Only avalanches with duration less than StopLayer are
%       recorded in asdf2. One time bin silent periods separate avalanches.
%   fullsizes (array) - a list of the avalanche sizes, including avalanches
%       with durations longer than StopLayer. fullsizes(i) is the size of
%       the ith avalanche.
%   fulldurs (array) - a list of the avalanche durations, including
%       avalanches with durations longer than StopLayer. fulldurs(i) is the
%       duration of the ith avalanche.
%   fullshapes (cell array) - a list of the avalanche shapes, including
%       avalanches with durations longer than StopLayer. fullshapes{i} is
%       an array of length fulldurs(i) where each element is the number of
%       active sites at that time.
%
% Example: 
%   [asdf2,fullsizes,fulldurs,fullshapes] = bldatagen(0.5, 100, 8, 10^6)
%     % Runs the Bethe Lattice for 100 trials. Only avalanches with
%     duration less than 8 will be fully recorded. Avalanches with duration
%     longer than 8 will only be recorded in terms of their size, duration,
%     and shape. Avalanches longer than 10^6 will be terminated, but
%     recorded. Each site receiving a connection from an active size will
%     have a likelihood of 0.5 to become active. 
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%

% Author: Nick Timme
% Email: nicholas.m.timme@gmail.com
% November 2015; Last revision: 29-December-2015

%==============================================================================
% Copyright (c) 2015, The Trustees of Indiana University
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

function [asdf2,fullsizes,fulldurs,fullshapes] = bethelattice(pTrans, nTrials, StopLayer, StopLayerFinal)
%% Run the lattice

MaxLayer = 1;
MaxNeuron = 1;
AllSpkRecord = cell([nTrials,1]);
Durs = zeros([nTrials,1]);
fullshapes = cell([nTrials,1]);
fullsizes = zeros([nTrials,1]);
fulldurs = zeros([nTrials,1]);
for iTrial = 1:nTrials
    
    iTrial
    
    % Initialize the active list, the layer number, and the spike record
    iLayer = 1;
    ActiveListOld = 1;
    SpkRecord = [1,1];
    
    while (~isempty(ActiveListOld)) && (iLayer < StopLayer)
        
        iLayer = iLayer + 1;
        Hits = (rand([2*length(ActiveListOld),1]) < pTrans);
        HitList = find(Hits);
        EOList = mod(HitList,2);
        EOList(EOList == 0) = 2;
        ActiveListNew = zeros([length(HitList),1]);
        for iHit = 1:length(HitList)
            Anc = ActiveListOld(ceil(HitList(iHit)/2));
            ActiveListNew(iHit) = 2*(Anc - 1) + EOList(iHit);
        end
        
        SpkRecord = [SpkRecord;[iLayer*ones([length(HitList),1]),ActiveListNew]];
        ActiveListOld = ActiveListNew;
        
    end
    
    % If the avalanche stopped at the first StopLayer, then record it.
    if isempty(ActiveListOld)
        AllSpkRecord{iTrial} = SpkRecord;
        
        % Update the maximum neuron and maximum layer
        if max(SpkRecord(:,1)) > MaxLayer
            MaxLayer = max(SpkRecord(:,1));
            MaxNeuron = max(SpkRecord(SpkRecord(:,1) == MaxLayer,:));
        elseif max(SpkRecord(:,1)) == MaxLayer
            if max(SpkRecord(SpkRecord(:,1) == MaxLayer,:)) > MaxNeuron
                MaxNeuron = max(SpkRecord(SpkRecord(:,1) == MaxLayer,:));
            end
        end
        
        % Record this trial duration
        Durs(iTrial) = max(SpkRecord(:,1));
        
    end
    
    
    % Keep the trial going if necessary, but don't record the individual
    % neurons
    
    TempSize = size(SpkRecord,1);
    TempShape = hist(SpkRecord(:,1),unique(SpkRecord(:,1)));
    while (~isempty(ActiveListOld)) && (iLayer < StopLayerFinal)
        
        iLayer = iLayer + 1;
        Hits = (rand([2*length(ActiveListOld),1]) < pTrans);
        TempSize = TempSize + nnz(Hits);
        if nnz(Hits) > 0
            TempShape = [TempShape,nnz(Hits)];
        end
        ActiveListOld = 1:nnz(Hits);
        
    end
    
    % Record the full size, duration, and shape
    fullsizes(iTrial) = TempSize;
    fulldurs(iTrial) = iLayer - 1;
    fullshapes{iTrial} = TempShape;
    
end


%% Convert to asdf2

% Make the layer vs. neuron conversion factor
LayerCor = zeros([1,MaxLayer]);
for iLayer = 2:MaxLayer
    LayerCor(iLayer) = LayerCor(iLayer - 1) + 2^(iLayer - 2);
end

% Figure out how many total neurons could have fired
nNeurons = LayerCor(MaxLayer) + 2^(MaxLayer - 1);

% Figure out the start time for each avalanche
StartTimes = ones([1,nTrials]);
for iTrial = 2:nTrials
    if Durs(iTrial - 1) > 0
        StartTimes(iTrial) = StartTimes(iTrial - 1) + Durs(iTrial - 1) + 1;
    else
        StartTimes(iTrial) = StartTimes(iTrial - 1);
    end
end

raster = cell([nNeurons,1]);
for iLayer = 1:MaxLayer
    for iNeuron = 1:(2^(iLayer - 1))
        NeurSpk = zeros([1,nTrials]);
        for iTrial = 1:nTrials
            NeurSpk(iTrial) = ismember([iLayer,iNeuron],AllSpkRecord{iTrial},'rows');
        end
        raster{LayerCor(iLayer) + iNeuron} = StartTimes(NeurSpk == 1) + iLayer;
    end
end


asdf2 = struct;

asdf2.raster = raster;
asdf2.binsize = 1;
asdf2.nbins = StartTimes(end) + Durs(end) + 1;
asdf2.nchannels = nNeurons;
asdf2.expsys = 'BetheLattice';
asdf2.datatype = 'Spikes';
asdf2.dataID = 'ModelX';