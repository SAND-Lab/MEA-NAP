function nmfResults = calNMF(activityMatrix, fs, downsamplefreq, duration_s, ...
    minSpikeCount, includeRandomMatrix, includeNMFcomponents, verboseLevel, suite2pMode)
% calNMF calculates metrics related to non-negative matrix factorisation (NNMF) of
% the spike matrix 
%
% Parameters
% ----------
%
% activityMatrix : matrix 
%     matrix of shape (numTimeSamples, numElectrodes)
% fs : int
%     sampling frequency (Hz) of spikeMatrix
% downsamplefreq : int 

% Info : structure 
% minSpikeCount : int 
%    minimum number of spike to count an electrode as active 
% includeRandomMatrix : bool 
% includeNMFcomponents : bool 
%    whether to save the extracted NMF components in nmfResults
%    useful for plotting, but takes up space
% Returns
% -------
% nmfResults : struct 
%   structure with the following fields 
%   num_nnmf_components : number of significant components from NMF
%   nComponentsRelNS : number of components relative to network size

if ~exist('verboseLevel', 'var')
    verboseLevel = 'Normal';
end 

if issparse(activityMatrix)
    activityMatrix = full(activityMatrix);
end

numUnits = size(activityMatrix, 2);

%% Initialise output 
nmfResults = struct();

%% Generate random matrix from original spike matrix

%% Downsample both matrices 
%
% downsampled randomised spike matrix
if includeRandomMatrix
    
    %tic
    %asdf2 = rastertoasdf2(spikeMatrix',1000,'placeHolder','','placeHolder');  % does not really depend on Grp nor Info
    %randasdf2 = randomizeasdf2(asdf2,'wrap');
    %randSpikeMatrix = asdf2toraster(randasdf2)';
    %toc 
    %clear asdf2 randasdf2
    %randSpikeMatrix = downSampleSum(randSpikeMatrix, downsamplefreq * duration_s);
    
    if suite2pMode == 1
        numTimePoints = size(activityMatrix, 1);
        randSpikeMatrix = zeros(numTimePoints, numUnits) + nan;
        for unit = 1:numUnits 
            numShiftSample = randi(numTimePoints);
            randSpikeMatrix(:, unit) = circshift(activityMatrix(:, unit), numShiftSample);
        end
    else
        spikeTimes = spikeMatrixToSpikeTimes(activityMatrix, fs);
        randSpikeTimes = cell(numUnits, 1);
        for unit = 1:numUnits
            randSpikeTimes{unit} = randomiseSpikeTrain(spikeTimes{unit}, duration_s, 'wrap');
        end

        randSpikeMatrix = spikeTimesToSpikeMatrix(randSpikeTimes, duration_s, fs); 

        randSpikeMatrix = downSampleSum(randSpikeMatrix, round(downsamplefreq * duration_s));
    end

end 
% downsampled original spike matrix
if strcmp(verboseLevel, 'High')
    fprintf('Downsampling spike matrix... \n')
end 

downSampleSpikeMatrix = downSampleSum(activityMatrix, round(downsamplefreq * duration_s));
            
activeElectrodes = sum(activityMatrix,1) > minSpikeCount;
spikePercentile =  prctile(activityMatrix,95,'all');
networkSize = sum(full(activeElectrodes));

%% Do NNMF 
if strcmp(verboseLevel, 'High')
    fprintf('Doing non-negative matrix factorsiation with different components... \n')
end 
residual = 0; randResidual = 1; k = 1;
randResidualPerComponent = [];
while residual < randResidual && k <= size(downSampleSpikeMatrix,2)
    if strcmp(verboseLevel, 'High')
        fprintf(sprintf('Searching k = %.f \n', k))
    end 
    [nmfFactors, nmfWeights, residual] = nnmf(downSampleSpikeMatrix,k);
    [~, msgid] = lastwarn;

    if strcmp(msgid,'nmf_warning')
        break
    end

    if includeRandomMatrix
        [~, ~, randResidual] = nnmf(randSpikeMatrix,k);
        [~, msgid] = lastwarn;
        if strcmp(msgid,'nmf_warning')
            randResidual = Inf;
        end
        randResidualPerComponent = [randResidualPerComponent; randResidual];
    end 
    k = k+1;
end
    
num_nnmf_components = k - 1;

%% Calculate mea number of components
[W, H] = nnmf(downSampleSpikeMatrix, num_nnmf_components,'algorithm','mult','replicates',10);
componentSize = [];

for nnmf_c = 1:num_nnmf_components
    nnmf_component_matrix = W(:, nnmf_c) * H(nnmf_c, :);
    nnmf_component_matrix(nnmf_component_matrix < 1) = 0;
    participatingElectrodes = sum(nnmf_component_matrix,1) ~= 0;

    % TODO: calculate the mean / median number of electrodes participating
    % in each component

    nnmf_component_matrix = nnmf_component_matrix(:,sum(nnmf_component_matrix,1) ~= 0);
    componentSize = [componentSize size(nnmf_component_matrix,2)];

    % components.(strcat("Component", "_",num2str(nnmf_c))) = nnmf_component_matrix;
    % components.(strcat("Component_channels", "_",num2str(nnmf_c))) = participatingElectrodes;
end

%% Do NNMF on each possible component 
activeElectrodes = sum(activityMatrix,1) > minSpikeCount;
networkSize = sum(full(activeElectrodes));
downSampleSpikeMatrixActive = downSampleSpikeMatrix(:, activeElectrodes);
% numTimeBins = size(downSampleSpikeMatrixActive, 1);

v = ver;
hasParallelToolbox = any(strcmp(cellstr(char(v.Name)), 'Parallel Computing Toolbox'));

nnmf_residuals = zeros(networkSize, 1);
nnmf_var_explained = zeros(networkSize, 1);
% D_store = zeros(networkSize, 1); % for testing purposes

varExplainedThreshold = 0.95;
thresholdReached = 0;

for k = 1:networkSize
    
    [k_nmfFactors, k_nmfWeights, k_residual] = nnmf(downSampleSpikeMatrixActive,k, ... 
    'options', statset('UseParallel', hasParallelToolbox));
    
    nnmf_residuals(k) = k_residual;
    
     % variance explained 
    predictedMatrix = k_nmfFactors * k_nmfWeights;
    var_explained = 1 -  sum(sum((predictedMatrix - downSampleSpikeMatrixActive).^2)) ... 
        / sum(sum((downSampleSpikeMatrixActive - mean(mean(downSampleSpikeMatrixActive))).^2));
    nnmf_var_explained(k) = var_explained;
    
    if (var_explained > varExplainedThreshold) && (1 - thresholdReached)
        thresholdReached = 1;
        nmfFactorsVarThreshold = k_nmfFactors;
        nmfWeightsVarThreshold = k_nmfWeights;
    end
    
    % D = norm(downSampleSpikeMatrixActive - nmfFactors*nmfWeights,'fro') / sqrt(numTimeBins*networkSize);
    % D_store(k) = D;
end

% This deals with edge case where variance explained never reached
% threshold
if (thresholdReached == 0) && (networkSize > 0)
    nmfFactorsVarThreshold = k_nmfFactors;
    nmfWeightsVarThreshold = k_nmfWeights;
elseif networkSize == 0 
    nmfFactorsVarThreshold = nan;
    nmfWeightsVarThreshold = nan;
end 


%% Make output 

nmfResults.spikePercentile = spikePercentile;
nmfResults.num_nnmf_components = num_nnmf_components;
nmfResults.residual = residual;
nmfResults.nComponentsRelNS = num_nnmf_components/networkSize;
nmfResults.nComponentsnRelNSsquared = num_nnmf_components/networkSize^2;
nmfResults.meanComponentSize = mean(componentSize);
nmfResults.nnmf_residuals = nnmf_residuals;
nmfResults.nnmf_var_explained = nnmf_var_explained;
nmfResults.randResidualPerComponent = randResidualPerComponent;

if includeNMFcomponents
    nmfResults.downSampleSpikeMatrix = downSampleSpikeMatrix;
    nmfResults.nmfFactors = nmfFactors;  % numTimeStamp x numComponents
    nmfResults.nmfWeights = nmfWeights;  % numComponents x numNodes
    nmfResults.nmfFactorsVarThreshold = nmfFactorsVarThreshold;
    nmfResults.nmfWeightsVarThreshold = nmfWeightsVarThreshold;
end 



end 