%% RANDOMIZEASDF2 - randomize asdf2 spike data to produce a null model
% Algorithm for randomizing spiking data in the asdf2 format using a
% specified method. This randomized data can be used as a null model
% version of the data in any given analysis.
%
% Syntax: [randasdf2] = randomizeasdf2(asdf2, method, varargin)
%
% Input:
%   asdf2 (structure array) - contains time raster and other information
%   method (string) - specifies the randomization method used. Choices:
%     'wrap' - cuts each spike train at random time (different for each
%         train) and swaps the resulting pieces. This method nearly
%         preserves the ISI distribution for each neuron, but completely
%         disrupts interneuron temporal relationships. 
%     'jitter' - randomly alters each spike time using a Gaussian
%         distribution centered on the original spike time. The user can
%         set the standard deviation of Gaussian distribution. This method
%         nearly preserves the ISI distribution for each neuron and all
%         neurons considered together. Also, it preserves interneuron
%         temporal relationships to a certain extent, dependent upon the
%         standard deviation of the jittering distribution. Importantly,
%         this method preserves the overall spike count (i.e. no spikes are
%         jittered into eachother). 
%     'Poisson' - converts each neuron's spike raster to a Poisson
%         spiking neuron with number of spikes and firing rate conserved.
%     'swap' - spike swaps each spike at least once. This preserves the
%         firing rate of each neuron and the instantaneous network wide
%         firing rate. Also, it preserves basic avalanche properties like
%         the size, duration, and shape of each avalanche.
%     'swap2' - spike swaps each spike, but does not preserve individual
%         neuron firing rates. This preserves the instantaneous network
%         firing rate (and therefore basic avalanche properties), but it
%         does not preserve individual neuron firing rates.
%
%
% Variable Inputs:
%   (..., 'stdtime', stdev) - the standard deviation of spike jittering in 
%     ms if the method is selected (scalar double) (default: 10 ms).
%   (..., 'stdbin', stdev) - the standard deviation of spike jittering in
%     bins if the method is selected (scalar double: integer) (default:
%     jittering stdev is set such that it is 10 ms).
%     
%
% Outputs:
%   randasdf2 (structure array) - contains time raster and other
%     information for the randomized spiking data. Also, a new field is
%     added describing the randomization that was used.
%
% Example:
%   randasdf2 = randomizeasdf2(asdf2,'jitter','stdtime',20);
%     % jitter the spike times in asdf2 using a Gaussian distribution with
%     % a standard deviation of 20 ms.
%   randasdf2 = randomizeasdf2(asdf2,'wrap');
%     % cut each neuron's spike train at a random point (different for each
%     % neuron) and swap the remaining pieces of the spike train.
%
% Other m-files required: none
% Subfunctions: none
% MAT-files required: none
%

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% March 2015; Last revision: 27-Mar-2015

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

function [randasdf2] = randomizeasdf2(asdf2, method, varargin)
%% Parse command line for parameters

stdev = 10;
stdevOp = 'time';


iVarArg = 1;
while iVarArg <= length(varargin)
    argOkay = true;
    if ischar(varargin{iVarArg}),
        switch varargin{iVarArg},
            case 'stdtime',    stdev = varargin{iVarArg+1};
            case 'stdbin',     stdev = varargin{iVarArg+1};    stdevOp = 'bin';
            otherwise, 
                argOkay = false;
        end
    end
    if ~argOkay
        disp(['(RANDOMIZEASDF2) Ignoring invalid argument #' num2str(iVarArg+1)]);
    end
    iVarArg = iVarArg + 1;
end

%% Process data

randasdf2 = asdf2;

if strcmp(method,'wrap')
    % The user selected the wrap method
    
    % Perform the wrapping
    for iChannel = 1:asdf2.nChannels % Leo: changed ".nchannels" to ".nChannels"
        CutTime = randi(asdf2.nBins); % Leo: changed ".nbins" to ".nBins", in line 131 as well
        randasdf2.raster{iChannel} = [asdf2.raster{iChannel}(asdf2.raster{iChannel} > CutTime) - CutTime,...
            asdf2.raster{iChannel}(asdf2.raster{iChannel} <= CutTime) + (asdf2.nBins - CutTime)];
    end
    
    % Leave a note in the randomized asdf2 raster
    randasdf2.randinfo = 'Wrapped Spike Trains';
    
elseif strcmp(method,'jitter')
    % The user selected the jittering method
    
    % Determine the jitter standard deviation in units of binsize
    if strcmp(stdevOp,'time')
        stdevbinsize = stdev / asdf2.binsize;
    elseif strcmp(stdevOp,'bin')
        stdevbinsize = stdev;
    end
    
    % Jitter the data
    for iChannel = 1:asdf2.nchannels
        
        % Get the number of spikes
        nSpikes = length(asdf2.raster{iChannel});
        
        % Make a random ordering of which spikes will be jittered when
        jitterorder = randperm(nSpikes);
        for iSpike = 1:nSpikes
            
            % Jitter the spike
            randasdf2.raster{iChannel}(jitterorder(iSpike)) = round(asdf2.raster{iChannel}(jitterorder(iSpike)) + stdevbinsize*randn);
            
            % Error check
            if randasdf2.raster{iChannel}(jitterorder(iSpike)) < 1 % Jittered off the front of the spike train
                randasdf2.raster{iChannel}(jitterorder(iSpike)) = asdf2.raster{iChannel}(jitterorder(iSpike));
            elseif randasdf2.raster{iChannel}(jitterorder(iSpike)) > asdf2.nbins % Jittered off the end of the spike train
                randasdf2.raster{iChannel}(jitterorder(iSpike)) = asdf2.raster{iChannel}(jitterorder(iSpike));
            elseif length(unique(randasdf2.raster{iChannel})) < nSpikes % Jittered into another spike
                randasdf2.raster{iChannel}(jitterorder(iSpike)) = asdf2.raster{iChannel}(jitterorder(iSpike));
            end
        end
        randasdf2.raster{iChannel} = sort(randasdf2.raster{iChannel});
    end
    
    % Leave a note in the randomized asdf2 raster
    randasdf2.randinfo = {'Jittered Spike Trains';stdev};
    
elseif strcmp(method,'Poisson')
    % The user selected the Poisson randomization method
    
    % Perform the randomization
    for iChannel = 1:asdf2.nchannels
        nSpikes = length(asdf2.raster{iChannel});
        NewSpikes = unique(randi(asdf2.nbins,[1,nSpikes]));
        while length(NewSpikes) < nSpikes
            NewSpikes = unique([NewSpikes,randi(asdf2.nbins,[1,nSpikes - length(NewSpikes)])]);
        end
        randasdf2.raster{iChannel} = NewSpikes;
    end
    
    % Leave a note in the randomized asdf2 raster
    randasdf2.randinfo = 'Poisson Randomized Spike Train';
    
elseif strcmp(method,'swap')
    % The user selected the spike swap randomization method
    
    % Make a list of all the spikes in the recording
    nSpikes = 0;
    for iChannel = 1:asdf2.nchannels
        nSpikes = nSpikes + length(asdf2.raster{iChannel});
    end
    SpikeList = zeros([nSpikes,2]);
    iSpike = 1;
    for iChannel = 1:asdf2.nchannels
        SpikeList(iSpike:(iSpike + length(asdf2.raster{iChannel}) - 1),1) = iChannel;
        SpikeList(iSpike:(iSpike + length(asdf2.raster{iChannel}) - 1),2) = asdf2.raster{iChannel};
        iSpike = iSpike + length(asdf2.raster{iChannel});
    end
    
    % If we have less than two spikes, we can't swap
    if nSpikes < 2
        error('Raster must have more than 1 spike to perform swapping.')
    end
    
    % Randomize the spike neurons
    SpikeList(:,1) = SpikeList(randperm(nSpikes),1);
    
    % Repair cases where spikes were swapped together
    SpikeList = sortrows(SpikeList,[1,2]);
    % First, look to see if any spikes were swapped together
    BadSwap = find((diff(SpikeList(:,1)) == 0) & (diff(SpikeList(:,2)) == 0),1,'first');
    if ~isempty(BadSwap)
        % We found spikes swapped together
        BadFlag = 1;
    else
        % Yippy, no spikes swapped together!
        BadFlag = 0;
    end
    % Repair the bad swaps
    while BadFlag == 1
        iSpike = BadSwap;
        jSpike = 1;
        Temp = randperm(nSpikes);
        while jSpike <= nSpikes
            if ~ismember(SpikeList(iSpike,2),SpikeList(SpikeList(:,1) == SpikeList(Temp(jSpike),1),2)) && ...
                    ~ismember(SpikeList(Temp(jSpike),2),SpikeList(SpikeList(:,1) == SpikeList(iSpike,1),2))
                % We found an open pairing, so perform the swap
                SpikeList([iSpike,Temp(jSpike)],2) = SpikeList([Temp(jSpike),iSpike],2);
                SpikeList = sortrows(SpikeList,[1,2]);
                jSpike = nSpikes + 1;
                BadSwap = find((diff(SpikeList(:,1)) == 0) & (diff(SpikeList(:,2)) == 0),1,'first');
                if ~isempty(BadSwap)
                    % We found spikes swapped together
                    BadFlag = 1;
                else
                    % Yippy, no spikes swapped together!
                    BadFlag = 0;
                end
            else
                jSpike = jSpike + 1;
                if jSpike == nSpikes + 1
                    error('Could not repair a instance of spikes swapped together.')
                end
            end
        end
    end
    
    % Put the swapped spike times in the raster
    for iChannel = 1:asdf2.nchannels
        randasdf2.raster{iChannel} = unique(SpikeList(SpikeList(:,1) == iChannel,2))';
    end
    
    
    % Leave a note in the randomized asdf2 raster
    randasdf2.randinfo = 'Spike Swapped Spike Train';
    
elseif strcmp(method,'swap2')
    
    % Find the network activity
    NetAct = zeros([1,asdf2.nbins]);
    for iChannel = 1:asdf2.nchannels
        NetAct(asdf2.raster{iChannel}) = NetAct(asdf2.raster{iChannel}) + 1;
    end
    
    % Find the number of non-zero activity bins
    nNonZero = nnz(NetAct);
    
    % Preallocate space for the new spike IDs
    ActBins = find(NetAct > 0);
    NeuronIDs = cell([1,nNonZero]);
    SpikeCounts = zeros([1,asdf2.nchannels]);
    
    for iBin = 1:nNonZero
        
        % Randomly assign the spikes in this time bin to different neurons
        if NetAct(ActBins(iBin)) == 1
            NeurList = randi(asdf2.nchannels);
        else
            Temp = randperm(asdf2.nchannels);
            NeurList = Temp(1:NetAct(ActBins(iBin)));
        end
        
        % Record the neurons that were assigned spikes in this time bin
        NeuronIDs{iBin} = NeurList;
        
        % Update the total number of spikes for each neuron that was
        % assigned a spike
        for iNeuron = 1:NetAct(ActBins(iBin))
            SpikeCounts(NeurList(iNeuron)) = SpikeCounts(NeurList(iNeuron)) + 1;
        end
        
    end
    
    % Put the spikes in the randomized raster
    iNeurSpike = ones([1,asdf2.nchannels]);
    for iChannel = 1:asdf2.nchannels
        randasdf2.raster{iChannel} = zeros([1,SpikeCounts(iChannel)]);
    end
    for iBin = 1:nNonZero
        for iSpike = 1:length(NeuronIDs{iBin})
            randasdf2.raster{NeuronIDs{iBin}(iSpike)}(iNeurSpike(NeuronIDs{iBin}(iSpike))) = ActBins(iBin);
            iNeurSpike(NeuronIDs{iBin}(iSpike)) = iNeurSpike(NeuronIDs{iBin}(iSpike)) + 1;
        end
    end
    
    % Leave a note in the randomized asdf2 raster
    randasdf2.randinfo = 'Spike Swapped Spike Train (FR not preserved)';
    
else
    % The user did not select a correct method
    error('Incorrect spike randomization method selected.')
end





end