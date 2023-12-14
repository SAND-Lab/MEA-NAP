function statsTable = doStats(nodeLevelData, recordingLevelData, Params)
%DOSTATS Summary of this function goes here
%   Detailed explanation goes here

uniqueLags = unique(recordingLevelData.Lag);


% Look at how the example logitudinal data from matlab looks like 
% this = load('longitudinalData.mat');

lagValueStore = []; % lag used
metricToTestStore = [];  % network / node level metric tested
statsMetricStore = {}; % what is the statistical metric (eg. p value, mean-squared error)
statsValueStore = []; % the value of the statistical metric
testStore = {};  % which statistical test is used


for lagIdx = 1:length(uniqueLags)
    lag = uniqueLags(lagIdx);
    subsetIndex = recordingLevelData.Lag == lag;
    recordingLevelDataSubset = recordingLevelData(subsetIndex, :);

    % do stats on recording level data 
    numUniqueDiv = length(unique(recordingLevelDataSubset.AgeDiv));
    numUniqueGrp = length(unique(recordingLevelDataSubset.eGrp));
    
    % Get the network metrics computed
    metricsComputed = recordingLevelDataSubset.Properties.VariableNames;
    metricsComputed(strcmp(metricsComputed, 'Lag')) = [];
    metricsComputed(strcmp(metricsComputed, 'AgeDiv')) = [];
    metricsComputed(strcmp(metricsComputed, 'recordingName')) = [];
    metricsComputed(strcmp(metricsComputed, 'eGrp')) = [];

    numRows = size(recordingLevelDataSubset, 1);
    
    % convert recording names to unique integer identifiers 
    recordingIDs = cellfun(@(x) strsplit(x, '_'), ...
        recordingLevelDataSubset.recordingName, 'UniformOutput', false);
    numUnderScore = count(recordingLevelDataSubset.recordingName{1}, '_');

    recordingIDs = cellfun(@(x) strjoin(x(1:numUnderScore), '_'), recordingIDs, 'UniformOutput', false);
    uniqueNames = unique(recordingIDs);
    subjectIDs = zeros(numRows, 1);

    for nameIdx = 1:length(uniqueNames)
        name = uniqueNames(nameIdx);
        subjectIDs(strcmp(recordingIDs, name)) = nameIdx;
    end 

    % convert DIV age from continuous variable to categorical IDs (for
    % ANOVA)

    ageIDs = zeros(numRows, 1);
    uniqueDIVs = unique(recordingLevelDataSubset.('AgeDiv'));

    for ageIdx = 1:length(uniqueDIVs)
        targetDIV = uniqueDIVs(ageIdx);
        ageIDs(recordingLevelDataSubset.('AgeDiv') == targetDIV) = ageIdx;
    end 

    % Convert group (usually genotype) variable to categorical IDs
    groupIDs = zeros(numRows, 1);
    uniqueGroups = unique(recordingLevelDataSubset.('eGrp'));
    for grpIdx = 1:length(uniqueGroups)
        targetGrp = uniqueGroups(grpIdx);
        groupIDs(contains(recordingLevelDataSubset.('eGrp'), targetGrp)) = grpIdx;
    end 


    for metricIdx = 1:length(metricsComputed)
        metricToTest = metricsComputed{metricIdx};
        if (numUniqueDiv > 1) && (numUniqueGrp > 1)
            % two way ANOVA (WIP / forget about it because of missing data)
            %
             % dependent_var =  recordingLevelDataSubset.(metricToTest);
             % subjectGroupingVar = subjectIDs;
             % bF1 = ageIDs; 
             % F2 = groupIDs;
             % FACTNAMES = {'age', 'group'};

             % remove any subjects with at least one NaN or Inf values 
             % validRows = find(isfinite(dependent_var));
             % validSubjects = unique(subjectGroupingVar(validRows));

             % stats = rm_anova2(dependent_var, subjectGroupingVar, F1,F2,FACTNAMES); 

             % linear mixed effects model 
             lmeValidRows = find(isfinite(recordingLevelDataSubset.(metricToTest)));
             recordingLevelDataSubsetValid = recordingLevelDataSubset(lmeValidRows, :);

             lmeNoInt = fitlme(recordingLevelDataSubsetValid, sprintf('%s ~ AgeDiv + eGrp + (1|recordingName)', metricToTest));
             lmeWInt = fitlme(recordingLevelDataSubsetValid, sprintf('%s ~ AgeDiv * eGrp + (1|recordingName)', metricToTest));
             
             % always input smaller model first 
             lmeComparison = compare(lmeNoInt, lmeWInt);
             lmeComparisonAlpha = 0.01;
            
             % if lmeComparison.pValue < lmeComparisonAlpha
             %    lme = lmeWInt;
             % else
             %    lme = lmeNoInt;
             % end
             
             lme = lmeNoInt;

             coefNames = lme.Coefficients.Name;
             numNames = length(coefNames);
             for nameIdx = 2:numNames % skip the first one (intercept)
                 lagValueStore = [lagValueStore; lag];
                 testStore{end+1} = sprintf('LME-noInteraction-%s', coefNames{nameIdx});
                 statsMetricStore{end+1} = 'P-value';
                 pVal = lme.Coefficients.pValue(nameIdx);
                 statsValueStore = [statsValueStore; pVal];
                 metricToTestStore{end+1} = metricToTest;
             end 
             
             % Do one-way ANOVA and pairwise test in each gruop 
             uniqueGrps = unique(recordingLevelDataSubsetValid.eGrp);
             for subsetGrpIdx = 1:numUniqueGrp
                 subsetGrp = uniqueGrps{subsetGrpIdx};
                 subsetGrpRecordingLevelData = recordingLevelDataSubsetValid(strcmp(recordingLevelDataSubsetValid.eGrp, subsetGrp), :);

                % Get recordings that share same set of DIV
                grpUniqueDIVs = unique(subsetGrpRecordingLevelData.AgeDiv);
                firstDIVdata = subsetGrpRecordingLevelData(subsetGrpRecordingLevelData.AgeDiv == grpUniqueDIVs(1), :);
                commonRecordings = unique(firstDIVdata.recordingName);
                for divIdx = 2:length(grpUniqueDIVs)
                    divData = subsetGrpRecordingLevelData(subsetGrpRecordingLevelData.AgeDiv == grpUniqueDIVs(divIdx), :);
                    commonRecordings = intersect(commonRecordings, divData.recordingName);
                end
                
                commonRecordingsGrpRecordingData = subsetGrpRecordingLevelData(...
                    contains(subsetGrpRecordingLevelData.recordingName, commonRecordings), :);
                % one way repeated measures ANOVA for DIV effect
                % using the RMAOV1.m package here: https://uk.mathworks.com/matlabcentral/fileexchange/5576-rmaov1
                % Input: (1) N x 3 data matrix, column 1 is the dependent
                % variable, column 2 is the independent variable, column 3 is
                % the subject ID, (2) alpha significance level (eg. 0.05)
                rmanova_X = zeros(size(commonRecordingsGrpRecordingData, 1), 3);
                rmanova_X(:, 1) = commonRecordingsGrpRecordingData.(metricToTest);
                
                % Make DIV group vector (cannot give continuous value /
                % just actual DIV values, needs to be integer groups
                % starting at 1)
                subsetGrpAgeID = zeros(size(commonRecordingsGrpRecordingData, 1), 1);
                uniqueAges = unique(commonRecordingsGrpRecordingData.AgeDiv);
                
                for recIdx = 1:length(subsetGrpAgeID)
                    subsetGrpAgeID(recIdx) = find(commonRecordingsGrpRecordingData.AgeDiv(recIdx) == uniqueAges);
                end 
                
                rmanova_X(:, 2) = subsetGrpAgeID;
                
                % get subset group subject ID 
                subsetGrpuniqueNames = unique(commonRecordingsGrpRecordingData.recordingName);
                subsetGrpsubjectIDs = zeros(size(commonRecordingsGrpRecordingData, 1), 1);

                for recIdx = 1:length(commonRecordingsGrpRecordingData.recordingName)
                    name = commonRecordingsGrpRecordingData.recordingName(recIdx);
                    subsetGrpsubjectIDs(recIdx) = find(strcmp(subsetGrpuniqueNames, name));
                end 
                rmanova_X(:, 3) = subsetGrpsubjectIDs;
                alpha = 0.05;
                [SSA, P1] = RMAOV1(rmanova_X, alpha);
                
                lagValueStore = [lagValueStore; lag];
                testStore{end+1} = [subsetGrp '-RM-1-ANOVA'];
                statsMetricStore{end+1} = 'P-value';
                statsValueStore = [statsValueStore; P1];
                metricToTestStore{end+1} = metricToTest;
                
                % paired t-test : assume all recordings have all the DIV
                % pairs
                divPairs = nchoosek(unique(subsetGrpRecordingLevelData.AgeDiv), 2);
                for divPairIdx = 1:size(divPairs, 1)
                    divA = divPairs(divPairIdx, 1);
                    divB = divPairs(divPairIdx, 2);
                    divAmetricVal = commonRecordingsGrpRecordingData(commonRecordingsGrpRecordingData.AgeDiv == divA, :).(metricToTest);
                    divBmetricVal = commonRecordingsGrpRecordingData(commonRecordingsGrpRecordingData.AgeDiv == divB, :).(metricToTest);
                    [h, p, ci, stats] = ttest(divAmetricVal, divBmetricVal);

                    lagValueStore = [lagValueStore; lag];
                    testStore{end+1} = sprintf('%s-DIV-%.f-%.f-paired-ttest', subsetGrp, divA, divB);
                    statsMetricStore{end+1} = 'P-value';
                    statsValueStore = [statsValueStore; p];
                    metricToTestStore{end+1} = metricToTest;

                end 
                
             end
             
             
             % For each DIV, do tests
             uniqueDIVs = unique(recordingLevelDataSubsetValid.AgeDiv);
             figureDisplay = 'off';
             for divIdx = 1:length(uniqueDIVs)
                divToSubset = uniqueDIVs(divIdx);
                divSubsetRecordingLevelData = recordingLevelDataSubsetValid(recordingLevelDataSubsetValid.AgeDiv == divToSubset, :);
                
                % One-way ANOVA across all groups
                [p,tbl] = anova1(divSubsetRecordingLevelData.(metricToTest), divSubsetRecordingLevelData.eGrp, figureDisplay');
                lagValueStore = [lagValueStore; lag];
                testStore{end+1} = sprintf('DIV-%.f-Grp-1-way-ANOVA', divToSubset);
                statsMetricStore{end+1} = 'P-value';
                statsValueStore = [statsValueStore; p];
                metricToTestStore{end+1} = metricToTest;
                
                % Do t-test between each pairs of groups
                grpPairs = nchoosek(uniqueGrps, 2);
                for pairIdx = 1:size(grpPairs)
                    grpA = grpPairs{pairIdx, 1};
                    grpB = grpPairs{pairIdx, 2};
                    grpAdata = divSubsetRecordingLevelData(strcmp(divSubsetRecordingLevelData.eGrp, grpA), :);
                    grpBdata = divSubsetRecordingLevelData(strcmp(divSubsetRecordingLevelData.eGrp, grpB), :);
                    [h, p] = ttest2(grpAdata.(metricToTest), grpBdata.(metricToTest));
                    lagValueStore = [lagValueStore; lag];
                    testStore{end+1} = sprintf('DIV-%.f-%s-vs-%s-ttest', divToSubset, grpA, grpB);
                    statsMetricStore{end+1} = 'P-value';
                    statsValueStore = [statsValueStore; p];
                    metricToTestStore{end+1} = metricToTest;
                end 
                
             end 
             
             

        elseif (numUniqueGrp == 1) && (numUniqueDiv == 1)
            % no stats avaiable
            statsTable = nan;
        else 
            if numUniqueDiv > 1
                % one way repeated measures ANOVA for DIV effect
                % using the RMAOV1.m package here: https://uk.mathworks.com/matlabcentral/fileexchange/5576-rmaov1
                % Input: (1) N x 3 data matrix, column 1 is the dependent
                % variable, column 2 is the independent variable, column 3 is
                % the subject ID, (2) alpha significance level (eg. 0.05)
                rmanova_X = zeros(numRows, 3);
                rmanova_X(:, 1) = recordingLevelDataSubset.(metricToTest);
                rmanova_X(:, 2) = ageIDs; % recordingLevelDataSubset.('AgeDiv');
                rmanova_X(:, 3) = subjectIDs;
                alpha = 0.05;
                [SSA, P1] = RMAOV1(rmanova_X, alpha);
                
                lagValueStore = [lagValueStore; lag];
                testStore{end+1} = 'RM-1-ANOVA';
                statsMetricStore{end+1} = 'P-value';
                statsValueStore = [statsValueStore; P1];
                metricToTestStore{end+1} = metricToTest;

                % linear mixed effects model 
                lmeValidRows = find(isfinite(recordingLevelDataSubset.(metricToTest)));
                recordingLevelDataSubsetValid = recordingLevelDataSubset(lmeValidRows, :);

                lme = fitlme(recordingLevelDataSubsetValid, ...
                    sprintf('%s ~ AgeDiv + (1|recordingName)', metricToTest));
                coefNames = lme.Coefficients.Name;
                numNames = length(coefNames);
                for nameIdx = 2:numNames % skip the first one (intercept)
                    lagValueStore = [lagValueStore; lag];
                    testStore{end+1} = sprintf('LME-%s', coefNames{nameIdx});
                    statsMetricStore{end+1} = 'P-value';
                    pVal = lme.Coefficients.pValue(nameIdx);
                    statsValueStore = [statsValueStore; pVal];
                    metricToTestStore{end+1} = metricToTest;
                end 
                
    
                % work in progress matlab version 
                % within = table(recordingLevelData.eGrp, 'VariableNames', {'eGrp'});
                % rm = fitrm(recordingLevelData, 'Dens ~ AgeDiv', 'WithinDesign', within);
                % ranovatbl = ranova(rm);
                
                % TODO: also fit linear mixed effects model

                % paired t-test : assume all recordings have all the DIV
                % pairs...
                divPairs = nchoosek(unique(recordingLevelDataSubset.AgeDiv), 2);

                for divPairIdx = 1:size(divPairs, 1)
                    divA = divPairs(divPairIdx, 1);
                    divB = divPairs(divPairIdx, 2);
                    divAmetricVal = recordingLevelDataSubset(recordingLevelDataSubset.AgeDiv == divA, :).(metricToTest);
                    divBmetricVal = recordingLevelDataSubset(recordingLevelDataSubset.AgeDiv == divB, :).(metricToTest);
                    [h, p, ci, stats] = ttest(divAmetricVal, divBmetricVal);

                    lagValueStore = [lagValueStore; lag];
                    testStore{end+1} = sprintf('DIV-%.f-%.f-paired-ttest', divA, divB);
                    statsMetricStore{end+1} = 'P-value';
                    statsValueStore = [statsValueStore; p];
                    metricToTestStore{end+1} = metricToTest;

                end 
                

    
            else
                % TODO: one way repeated measures ANOVA for Genotype effect 

                % linear mixed effects model 
                lmeValidRows = find(isfinite(recordingLevelDataSubset.(metricToTest)));
                recordingLevelDataSubsetValid = recordingLevelDataSubset(lmeValidRows, :);

                lme = fitlme(recordingLevelDataSubsetValid, ...
                    sprintf('%s ~ eGrp + (1|recordingName)', metricToTest));
                coefNames = lme.Coefficients.Name;
                numNames = length(coefNames);
                for nameIdx = 2:numNames % skip the first one (intercept)
                    lagValueStore = [lagValueStore; lag];
                    testStore{end+1} = sprintf('LME-%s', coefNames{nameIdx});
                    statsMetricStore{end+1} = 'P-value';
                    pVal = lme.Coefficients.pValue(nameIdx);
                    statsValueStore = [statsValueStore; pVal];
                    metricToTestStore{end+1} = metricToTest;
                end 

            end 
        end 
    end 
end 

statsTable = table(metricToTestStore', lagValueStore, ...
    testStore', statsMetricStore', statsValueStore);
statsTable.Properties.VariableNames = {'Metric', 'Lag', 'Test', 'Test-statistic', 'Value'};


end

