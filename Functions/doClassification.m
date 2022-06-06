function classificationResults = doClassification(recordingLevelData, Params, figSaveFolder)
%{
Do classification of genotype based on network features 

Parameters
----------
recordingLevelData : table 
Params : struct 
figSaveFolder : str

Returns
-------

%}

%% Do LDA
subset_lag = 15;
subset_idx = find(recordingLevelData.('Lag') == subset_lag);
lagRecordingLevelData = recordingLevelData(subset_idx, :);


columnsToExclude = {'eGrp', 'AgeDiv', 'Lag'};
subsetColumnIdx = find(~ismember(lagRecordingLevelData.Properties.VariableNames, columnsToExclude));
lagRecordingLevelDataFeatures = lagRecordingLevelData(:,subsetColumnIdx);

X = table2array(lagRecordingLevelDataFeatures);
subset_feature_bool = var(X)~=0;
subset_feature_names = lagRecordingLevelDataFeatures.Properties.VariableNames(subset_feature_bool);
X_processed = X(:, subset_feature_bool);
X_processed = zscore(X_processed, 1);

y = lagRecordingLevelData.('AgeDiv');
Mdl = fitcdiscr(X_processed, y);
[W, LAMBDA] = eig(Mdl.BetweenSigma, Mdl.Sigma); %Must be in the right order! 
lambda = diag(LAMBDA);
[lambda, SortOrder] = sort(lambda, 'descend');
W = W(:, SortOrder);  % each column is an LDA component
Y = X_processed*W;

figure
% LDA plot
subplot(2, 2, 1)
unique_y = unique(y);
num_unique_y = length(unique_y);

sz = 100;

legend_labels = {};

colors = brewermap(num_unique_y, 'GnBu');

for n_y = 1:num_unique_y
    
    sample_matching_y = find(y == unique_y(n_y));
    scatter(Y(sample_matching_y, 1), Y(sample_matching_y, 2), sz, colors(n_y, :), 'filled')
    hold on

    legend_labels{n_y} = num2str(unique_y(n_y));

end 
xlabel('LDA 1');
ylabel('LDA 2')
leg = legend(legend_labels);
title(leg, 'DIV')

% Weights onto LDA1 
subplot(2, 2, 3)
bar(W(:, 1))
xticks(1:length(subset_feature_names))
xticklabels(subset_feature_names)
xlabel('Features')
ylabel('Weight')
title('Weights on LDA 1')

% Weights onto LDA2
subplot(2, 2, 2)
bar(W(:, 2))
xticks(1:length(subset_feature_names))
xticklabels(subset_feature_names)
xlabel('Features')
ylabel('Weight')
title('Weights on LDA 1')


set(gcf, 'color', 'w')

saveName = 'ldaAcorssDIV';

if Params.figMat == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.fig']));
end
if Params.figPng == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.png']));
end
if Params.figEps == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.eps']));
end


%% Do SVM classification 

% TODO: do stratification via cv partition and setting 'stratifyOption', 1
SVMModel = fitcecoc(X_processed,y);
CVSVMModel = crossval(SVMModel, 'KFold',2);
%[~,scorePred] = kfoldPredict(CVSVMModel);
original_loss = CVSVMModel.kfoldLoss;

num_shuffle = 200;
shuffle_loss = zeros(num_shuffle, 1);
for shuffle = 1:num_shuffle
    y_shuffled = y(randperm(length(y)));
    shuffled_SVMModel = fitcecoc(X_processed, y_shuffled);
    shuffled_CVSVMModel = crossval(shuffled_SVMModel, 'KFold',2);
    shuffle_loss(shuffle) = shuffled_CVSVMModel.kfoldLoss;
end 

% Plot classification performance 

figure;
subplot(2, 2, 1)
xline(original_loss, 'linewidth', 2);
hold on 
histogram(shuffle_loss, 20);

xlabel('Misclassification rate')
ylabel('Number of shuffles')
set(gcf, 'color', 'white');
legend('Original data', 'Shuffled data')

subplot(2, 2, 2)
num_bins = 10000; % can be arbitrarily big
[f,z] = hist(1 - shuffle_loss,num_bins);
% Make pdf by normalizing counts
% Divide by the total counts and the bin width to make area under curve 1.
fNorm = f/(sum(f)*(z(2)-z(1))); 
% cdf is no cumulative sum
fCDF = cumsum(fNorm);
percentile_score = fCDF / max(fCDF) * 100;  
plot(z, percentile_score); 
xlim([0, 1])
xline(1 - original_loss)
ylabel('Percentile')



saveName = 'svmClassificationLossVersusShuffle';

if Params.figMat == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.fig']));
end
if Params.figPng == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.png']));
end
if Params.figEps == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.eps']));
end

%% Do regression 

regressionModel = fitrtree(X_processed, y);
CVSVMModel = crossval(regressionModel, 'KFold',2);
%[~,scorePred] = kfoldPredict(CVSVMModel);
original_loss = CVSVMModel.kfoldLoss;

num_shuffle = 200;
shuffle_loss = zeros(num_shuffle, 1);
for shuffle = 1:num_shuffle
    y_shuffled = y(randperm(length(y)));
    shuffled_regressionModel = fitrtree(X_processed, y_shuffled);
    shuffled_CVSVMModel = crossval(shuffled_regressionModel, 'KFold',2);
    shuffle_loss(shuffle) = shuffled_CVSVMModel.kfoldLoss;
end 

figure;
xline(original_loss);
hold on 
histogram(shuffle_loss, 20);

xlabel('Mean squared error')
ylabel('Number of shuffles')
set(gcf, 'color', 'white');


saveName = 'regressionTreeMSEVersusShuffle';

if Params.figMat == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.fig']));
end
if Params.figPng == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.png']));
end
if Params.figEps == 1
    saveas(gcf,fullfile(figSaveFolder, [saveName '.eps']));
end

%% Plot some examples of the regression to make sure I know what I am doing
tot_samples = size(X_processed, 1);
sample_indices = 1:tot_samples;
test_prop = 0.5;
rand_indices = sample_indices(randperm(tot_samples));

test_idx_end = round(tot_samples*test_prop);
test_idx = rand_indices(1:test_idx_end);
train_idx = rand_indices(test_idx_end+1:end);

X_train = X_processed(train_idx, :);
X_test = X_processed(test_idx, :);

y_train = y(train_idx);
y_test = y(test_idx);

regressionModel = fitrtree(X_train, y_train);
y_train_predicted = predict(regressionModel, X_train);
y_test_predicted = predict(regressionModel, X_test);

unity_vals = linspace(10, 30, 100);

figure;
subplot(1, 2, 1)
scatter(y_train, y_train_predicted);
hold on 
plot(unity_vals, unity_vals);
xlim([10, 30])
ylim([10, 30])
title('')
subplot(1, 2, 2)
scatter(y_test, y_test_predicted);
hold on 
plot(unity_vals, unity_vals);
xlim([10, 30])
ylim([10, 30])

figure;
subplot(1, 2, 1)
plot(y_train);
hold on
plot(y_train_predicted)
subplot(1, 2, 2)
plot(y_test);
hold on
plot(y_test_predicted)


end 