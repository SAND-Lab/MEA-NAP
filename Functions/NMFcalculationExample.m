%% NMF calculation example 
clear all 

% load data 

load('/Users/timothysit/Downloads/MPT190403_6B_DIV35_cSpikes_L00627_RF1.mat')


% specify parameters to calculate NMF 
Params.NMFdownsampleFreq = 10;  % how much to downsample the spike matrix before doing NMF
includeRandomMatrix = 1; % whether to include random matrix in NMF calculation 
minSpikeCount = 10;  % minimum number of spikes for an electrode to be classified as active
Params.fs = 25000;  % sampling frequency of the recording
%duration_s = Info.duration_s; % duration of the recording in seconds
% ^ usually this should be in the Info file of ExperimentMat, but here 
% I assume you only have the spike file in hand
duration_s = size(cSpikes, 1) / Params.fs; 

spikeMatrix = full(cSpikes); % convert from sparse matrix to "normal" matrix

nmfCalResults = calNMF(spikeMatrix, Params.NMFdownsampleFreq, ...
    duration_s, minSpikeCount, includeRandomMatrix);