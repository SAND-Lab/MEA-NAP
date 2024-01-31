function LDAresults = doLDA(recordingLevelData, Params, subset_lag)
% Performs linear discriminant analysis (LDA) on network or neuronal
% activity features at a recording level (one row per recording)
% Parameters
% ----------
% recordingLevelData : table 
% Params : struct 
%
%
% Returns 
% -------
% LDAresults : struct
% 

if length(unique(recordingLevelData.eGrp)) == 1
    classificationMode = 'allDIV';
else 
    classificationMode = 'genotypePerDIV';
end

if strcmp(classificationMode, 'genotypePerDIV')

    subgroupTarget = 'AgeDiv';
    classificationTarget = 'eGrp';
    subGroupTargetLevels = unique(recordingLevelData.(subgroupTarget));
    features_to_use = {'aN', 'Dens', 'CC', 'nMod', 'Q', 'PL', 'Eglob', 'SW', 'SWw', 'effRank', 'num_nnmf_components'};
    subsetColumnIdx = find(ismember(recordingLevelData.Properties.VariableNames, features_to_use));
    LDAresults = struct();
    LDAresults.classificationMode = classificationMode;
    numSamples = size(recordingLevelData, 1);
    numFeatures = length(features_to_use);

    LDAresults.genotypePerDIV = cell(length(subGroupTargetLevels), 4);
    LDAresults.features = features_to_use;

    % loop through DIVs
    for subGroupIdx = 1:length(subGroupTargetLevels)
        
        subGroupLevel = subGroupTargetLevels(subGroupIdx);
        subset_idx = find(recordingLevelData.(subgroupTarget) == subGroupLevel);
        subGroupData = recordingLevelData(subset_idx, :);
        subGroupFeatures = subGroupData(:, subsetColumnIdx);

        X = table2array(subGroupFeatures);
        y = subGroupData.(classificationTarget);

        % some data pre-processing 
        X_processed = X;
        
        % Drop NaN 
        subsetIdx = find(sum(~isfinite(X_processed), 2) == 0);
        X_processed = X_processed(subsetIdx, :);
        y = y(subsetIdx);
        
        % do genotype classification
        Mdl = fitcdiscr(X_processed, y);
        [W, LAMBDA] = eig(Mdl.BetweenSigma, Mdl.Sigma); %Must be in the right order! 
        lambda = diag(LAMBDA);
        [lambda, SortOrder] = sort(lambda, 'descend');
        W = W(:, SortOrder);  % each column is an LDA component
        Y = X_processed*W;  % this is the projection I think 

        LDAresults.genotypePerDIV{subGroupIdx, 1} = subGroupLevel;
        LDAresults.genotypePerDIV{subGroupIdx, 2} = Y;
        LDAresults.genotypePerDIV{subGroupIdx, 3} = y;  % the actual genotype
        LDAresults.genotypePerDIV{subGroupIdx, 4} = W;

    end 

elseif strcmp(classificationMode, 'allDIV')

    classificationTarget = 'AgeDiv';
    subset_idx = find(recordingLevelData.('Lag') == subset_lag);
    lagRecordingLevelData = recordingLevelData(subset_idx, :);
    
    columnsToExclude = {'eGrp', 'AgeDiv', 'Lag', 'recordingName'};
    subsetColumnIdx = find(~ismember(lagRecordingLevelData.Properties.VariableNames, columnsToExclude));
    lagRecordingLevelDataFeatures = lagRecordingLevelData(:,subsetColumnIdx);
    
    y = lagRecordingLevelData.(classificationTarget);
    
    X = table2array(lagRecordingLevelDataFeatures);
    subset_feature_bool = var(X)~=0;
    subset_feature_names = lagRecordingLevelDataFeatures.Properties.VariableNames(subset_feature_bool);
    X_processed = X(:, subset_feature_bool);
    X_processed = zscore(X_processed, 1);
   
    % Linear dicriminant analysis
    Mdl = fitcdiscr(X_processed, y, 'discrimType', 'pseudoLinear');  % 'pseudoLinear' allows for zero within class variance
    [W, LAMBDA] = eig(Mdl.BetweenSigma, Mdl.Sigma); %Must be in the right order! 
    lambda = diag(LAMBDA);
    [lambda, SortOrder] = sort(lambda, 'descend');
    W = W(:, SortOrder);  % each column is an LDA component
    Y = X_processed*W;

end
    



end 