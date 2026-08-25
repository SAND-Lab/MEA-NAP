function classificationResults = classifyGroupPerDIV(recordingLevelData, Params, subset_lag)
% Runs group classification for each DIV separately 
% Parameters 
% ----------
% recordingLevelData : table 

subgroupTarget = 'DIV';
Params.classificationTarget = 'Grp';

subGroupTargetLevels = unique(recordingLevelData.(subgroupTarget));
numClassifier = length(Params.classification_models);
numSubGroup = length(subGroupTargetLevels);

if Params.doPairwiseClassification == 1
    uniqueTargets = unique(recordingLevelData.(Params.classificationTarget));
    targetPairs = nchoosek(uniqueTargets, 2);
    numPairs = size(targetPairs, 1);

    if Params.downsampleMajorityClass == 1
        model_loss_per_subgroup = zeros(Params.numDownSampleRuns, numPairs, ...
            numSubGroup, numClassifier, Params.clf_num_kfold_repeat);
    else
        model_loss_per_subgroup = zeros(numPairs, numSubGroup, numClassifier, Params.clf_num_kfold_repeat);
    end 

    numSampleOfEachPair = zeros(numPairs, numSubGroup, 2);
else 
    model_loss_per_subgroup = zeros(numSubGroup, numClassifier, Params.clf_num_kfold_repeat);
    model_loss_per_subgroup_shuffled = zeros(Params.numClfShuffleControls, numSubGroup, numClassifier, Params.clf_num_kfold_repeat);
end 

for subGroupIdx = 1:length(subGroupTargetLevels)
    
    subGroupLevel = subGroupTargetLevels(subGroupIdx);
    subset_idx = find(recordingLevelData.(subgroupTarget) == subGroupLevel);
    subGroupData = recordingLevelData(subset_idx, :);
    % subGroupFeatures = subGroupData(:, subsetColumnIdx);

    if Params.doPairwiseClassification == 1
        
        for pairIdx = 1:size(targetPairs, 1)
            pairToClassify = targetPairs(pairIdx, :);
            targetPairDataIdx = find( ...
                strcmp(subGroupData.(Params.classificationTarget), pairToClassify(1)) | ...
                strcmp(subGroupData.(Params.classificationTarget), pairToClassify(2))); 
            
            grp1idx = find(strcmp(subGroupData.(Params.classificationTarget), pairToClassify(1)));
            grp2idx = find(strcmp(subGroupData.(Params.classificationTarget), pairToClassify(2)));
            numGrp1 = length(grp1idx);
            numGrp2 = length(grp2idx);
            numSampleOfEachPair(pairIdx, subGroupIdx, 1) = numGrp1;
            numSampleOfEachPair(pairIdx, subGroupIdx, 2) = numGrp2;
            
            if Params.downsampleMajorityClass == 1
                for downsampleIdx = 1:Params.numDownSampleRuns
                    if numGrp1 > numGrp2
                        % subsample group 1 because there are more of them
                        % than group 2
                        grp1idxSubsample = grp1idx(randperm(numGrp1, numGrp2));
                        targetPairDataIdx = [grp1idxSubsample; grp2idx];
                    else 
                        grp2idxSubsample = grp2idx(randperm(numGrp2, numGrp1));
                        targetPairDataIdx = [grp2idxSubsample; grp1idx];
                    end 
                    targetPairData = subGroupData(targetPairDataIdx, :);

                    if Params.clfDoRFE == 1
                        % NOTE: This is very much work in progress
                        featureColumnsIdx = find(ismember(recordingLevelData.Properties.VariableNames, Params.clfFeaturesToUse));
                        nonFeaturesColumns = find(~ismember(recordingLevelData.Properties.VariableNames, Params.clfFeaturesToUse));
                        nFeatures = length(featureColumnsIdx);
                        classificationResultsAllFeatures = doClassification(targetPairData, Params, subset_lag);
                        modelLossAllFeatures = classificationResultsAllFeatures.model_loss(2);
                        modelLossPerFeatRemoved = zeros(nFeatures, Params.RFEmaxFeaturesToRemove);
                        
                        for featureRemovalStep = 1:Params.RFEmaxFeaturesToRemove
                            for featIdx = featureColumnsIdx
                                subsetColumns = [nonFeaturesColumns, featureColumnsIdx(featureColumnsIdx ~= featIdx)];
                                subsetTargetPairData = targetPairData(:, subsetColumns);
                                classificationResults = doClassification(subsetTargetPairData, Params, subset_lag);
                                % temp idx here to just get the KNN
                                modelLossPerFeatRemoved(featIdx, featureRemovalStep) = classificationResults.model_loss(2);
                            end 
                            classificationResults.nonFeaturesColumns;

                        end 

                        
                    else 
                        classificationResults = doClassification(targetPairData, Params, subset_lag);
                        model_loss_per_subgroup(downsampleIdx, pairIdx, subGroupIdx, :, :) = ...
                        classificationResults.model_loss;
                    end 
                end 
            else
                targetPairData = subGroupData(targetPairDataIdx, :);
                classificationResults = doClassification(targetPairData, Params, subset_lag);
                model_loss_per_subgroup(pairIdx, subGroupIdx, :, :) = classificationResults.model_loss;
            end 
        end 

    else
    
        classificationResults = doClassification(subGroupData, Params, subset_lag);
        model_loss_per_subgroup(subGroupIdx, :, :) = classificationResults.model_loss;
    end 
    % X = table2array(subGroupFeatures);
    % y = subGroupData.(classificationTarget);

end 

if Params.doPairwiseClassification == 1
    classificationResults.targetPairs = targetPairs;
    classificationResults.numSampleOfEachPair = numSampleOfEachPair; 
end 

if Params.downsampleMajorityClass == 1
    model_loss_per_subgroup = squeeze(mean(model_loss_per_subgroup, 1));
end 


classificationResults.subGroupLevels = subGroupTargetLevels;
classificationResults.model_loss_per_subgroup = model_loss_per_subgroup;
classificationResults.subgroupTarget = subgroupTarget;
classificationResults.classificationTarget = Params.classificationTarget;

end