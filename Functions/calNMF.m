function nmfResults = calNMF(spikeMatrix, fs, downsamplefreq, duration_s, ...
    minSpikeCount, includeRandomMatrix, includeNMFcomponents)
% calNMF calculates metrics related to non-negative matrix factorisation (NNMF) of
% the spike matrix 
%
% Parameters
% ----------
%
% spikeMatrix : matrix 
%     matrix of shape (numTimeSamples, numElectrodes)
% Params : structure 
% Info : structure 
% minSpikeCount : int 
%    minimum number of spike to count an electrode as active 
% Returns
% -------
% nmfResults : struct 
%   structure with the following fields 
%   num_nnmf_components : number of significant components from NMF
%   nComponentsRelNS : number of components relative to network size

if issparse(spikeMatrix)
    spikeMatrix = full(spikeMatrix);
end

numUnits = size(spikeMatrix, 2);

%% Initialise output 
nmfResults = struct();

%% Generate random matrix from original spike matrix

%% Downsample both matrices 

% downsampled randomised spike matrix
if includeRandomMatrix
    
    %tic
    %asdf2 = rastertoasdf2(spikeMatrix',1000,'placeHolder','','placeHolder');  % does not really depend on Grp nor Info
    %randasdf2 = randomizeasdf2(asdf2,'wrap');
    %randSpikeMatrix = asdf2toraster(randasdf2)';
    %toc 
    %clear asdf2 randasdf2
    %randSpikeMatrix = downSampleSum(randSpikeMatrix, downsamplefreq * duration_s);
    spikeTimes = spikeMatrixToSpikeTimes(spikeMatrix, fs);
    randSpikeTimes = cell(numUnits, 1);
    for unit = 1:numUnits
        randSpikeTimes{unit} = randomiseSpikeTrain(spikeTimes{unit}, duration_s, 'wrap');
    end

    randSpikeMatrix = spikeTimesToSpikeMatrix(randSpikeTimes, duration_s, fs); 

    randSpikeMatrix = downSampleSum(randSpikeMatrix, downsamplefreq * duration_s);

end 
% downsampled original spike matrix
fprintf('Downsampling spike matrix... \n')
downSampleSpikeMatrix = downSampleSum(spikeMatrix, downsamplefreq * duration_s);
            
activeElectrodes = sum(spikeMatrix,1) > minSpikeCount;
spikePercentile =  prctile(spikeMatrix,95,'all');
networkSize = sum(full(activeElectrodes));

%% Do NNMF 
fprintf('Doing non-negative matrix factorsiation with different components... \n')
residual = 0; randResidual = 1; k = 1;
while residual < randResidual && k <= size(downSampleSpikeMatrix,2)
    fprintf(sprintf('Searching k = %.f \n', k))
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


%% Make output 

nmfResults.spikePercentile = spikePercentile;
nmfResults.num_nnmf_components = num_nnmf_components;
nmfResults.residual = residual;
nmfResults.nComponentsRelNS = (k-1)/networkSize;
nmfResults.nComponentsnRelNSsquared = (k-1)/networkSize^2;
nmfResults.meanComponentSize = mean(componentSize);

if includeNMFcomponents
    nmfResults.downSampleSpikeMatrix = downSampleSpikeMatrix;
    nmfResults.nmfFactors = nmfFactors;  % numTimeStamp x numComponents
    nmfResults.nmfWeights = nmfWeights;  % numComponents x numNodes
end 



end 