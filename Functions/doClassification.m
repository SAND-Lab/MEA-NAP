function classificationResults = doClassification(recordingLevelData, Params, subset_lag, plotSaveFolder, oneFigureHandle)
% Do classification of genotype based on network features 
%
% Parameters
% ----------
% recordingLevelData : table 
% Params : struct 
% figSaveFolder : str
% subset_lag : int
%     which lag to use to do classification
% Returns
% -------
%
%

Params.clf_num_kfold_repeat = 5;
Params.clf_num_kfold = 2;

% Parameters 
num_shuffle = 200;  % number of shuffles to do 
clf_num_kfold_repeat = Params.clf_num_kfold_repeat;  % number of repeats of kfold validation to do for classification \
clf_num_kfold = Params.clf_num_kfold ;
reg_num_kfold_repeat = 5;  % number of repeats of kfold validation to do for regression
nestedClassification = 0;
nestedClassificationGroup = 'eGrp';
% classificationTarget = Params.classificationTarget;

if length(unique(recordingLevelData.eGrp)) == 1
    classificationTarget = 'AgeDiv';
else 
    classificationTarget = 'eGrp';
end 
feature_preprocessing_steps = {'removeZeroVariance', 'zScore'};


% TODO: allow multiple classification and regression models
classification_models = Params.classification_models;
% regression_models = Params.regression_models;

%if Params.showOneFig 
%    Params.oneFigure = figure();
%end 

%% Feature subsetting and processing 
features_to_use = {'aN', 'Dens', 'CC', 'nMod', 'Q', 'PL', 'Eglob', 'SW', 'SWw', 'effRank', 'num_nnmf_components'};
subsetColumnIdx = find(ismember(recordingLevelData.Properties.VariableNames, features_to_use));
features = recordingLevelData(:, subsetColumnIdx);
feature_names = features.Properties.VariableNames;

X = table2array(features);
y = recordingLevelData.(classificationTarget);

% some data pre-processing 
X_processed = X;

% Drop non-finite values 
subsetIdx = find(sum(~isfinite(X_processed), 2) == 0);
X_processed = X_processed(subsetIdx, :);
y = y(subsetIdx);


%% Do classification 
num_classification_models = length(classification_models);
model_loss = zeros(clf_num_kfold_repeat, num_classification_models);

if iscell(y)
    model_predictions = cell(clf_num_kfold_repeat, num_classification_models, length(y));
else 
    model_predictions = zeros(clf_num_kfold_repeat, num_classification_models, length(y));
end 

for kfold_repeat_idx = 1:clf_num_kfold_repeat
    for classifier_idx = 1:length(classification_models)
    
        classifier_name = classification_models{classifier_idx};
        
        % TODO: probably can tidy up this to not have to repeat X_processed so
        % many times
        if strcmp(classifier_name, 'linearSVM')
            clf_model = fitcecoc(X_processed,y);
        elseif strcmp(classifier_name, 'kNN')
            clf_model = fitcknn(X_processed, y);
        elseif strcmp(classifier_name, 'decisionTree')
            clf_model = fitctree(X_processed, y);
        elseif strcmp(classifier_name, 'fforwardNN')
            clf_model = fitcnet(X_processed, y);
        elseif strcmp(classifier_name, 'LDA')
            clf_model = fitcdiscr(X_processed, y);
        else 
            fprinf('WARNING: no valid classifier specified')
        end 
        % TODO: do stratification via cv partition and setting 'stratifyOption', 1
        rng(Params.statsRandomSeed + kfold_repeat_idx);
        cross_val_model = crossval(clf_model, 'KFold', clf_num_kfold);
        classifier_cv_prediction = kfoldPredict(cross_val_model);

        model_predictions(kfold_repeat_idx, classifier_idx, :) = classifier_cv_prediction;
        model_loss(kfold_repeat_idx, classifier_idx) = cross_val_model.kfoldLoss;
    end 

end 

%% Output classification results 
classificationResults = struct();
classificationResults.model_loss = model_loss; 
classificationResults.model_predictions = model_predictions;
classificationResults.classification_models = classification_models;
classificationResults.clf_num_kfold = clf_num_kfold;

%% Get feature importance by shuffling each feature and recomputing performance 
num_shuffles = 10;
num_features = size(X_processed, 2);
num_observations = size(X_processed, 1);
num_models = length(classification_models);
leave_one_out_kfoldLoss = size(num_models, num_shuffles, num_features);

for classifier_idx = 1:num_models
    classifier_name = classification_models{classifier_idx};
    
    for feature_idx = 1:num_features 
        for shuffle_idx = 1:num_shuffles
            X_shuffled = X_processed;
            random_idx = randperm(num_observations);
            X_shuffled(:, feature_idx) = X_processed(random_idx, feature_idx);
            
            if strcmp(classifier_name, 'linearSVM')
            clf_model = fitcecoc(X_shuffled,y);
            elseif strcmp(classifier_name, 'kNN')
                clf_model = fitcknn(X_shuffled, y);
            elseif strcmp(classifier_name, 'decisionTree')
                clf_model = fitctree(X_shuffled, y);
            elseif strcmp(classifier_name, 'fforwardNN')
                clf_model = fitcnet(X_shuffled, y);
            elseif strcmp(classifier_name, 'LDA')
                clf_model = fitcdiscr(X_shuffled, y);
            else 
                fprinf('WARNING: no valid classifier specified')
            end 
            rng(Params.statsRandomSeed + shuffle_idx);
            cross_val_model = crossval(clf_model, 'KFold', clf_num_kfold);
            leave_one_out_kfoldLoss(classifier_idx, shuffle_idx, feature_idx) = cross_val_model.kfoldLoss;
        end
    end 
end 

%% Plot feature importance
if Params.showOneFig 
     % Make it so figure handle in oneFigure don't appear
     set(0, 'DefaultFigureVisible', 'off')
end 
p = [0, 0, 600, 600];
if Params.showOneFig
    if isgraphics(oneFigureHandle)
        set(oneFigureHandle, 'Position', p);
    else 
        oneFigureHandle = figure;
        set(oneFigureHandle, 'Position', p);
    end 
else
    figure
    set(gcf, 'Position', p);
end 

mean_model_loss = squeeze(mean(model_loss, 1));
mean_loo_loss = squeeze(mean(leave_one_out_kfoldLoss, 2));

for classifier_idx = 1:num_models
    loo_loss_per_feature = mean_loo_loss(classifier_idx, :) - mean_model_loss(classifier_idx);
    feature_idx = 1:length(loo_loss_per_feature);
    plot(feature_idx, loo_loss_per_feature, 'Linewidth', 2)
    hold on
end 

ylabel('Leave one out loss - original loss (Higher is better)')
xlabel('Features')
xticks(feature_idx)
xticklabels(feature_names);
[~, hobj, ~, ~] = legend(classification_models);
hl = findobj(hobj,'type','line');
set(hl,'LineWidth',2);
legend box off
set(gca, 'TickDir', 'Out');
set(gca, 'box', 'off');
set(gcf, 'color', 'white');

saveName = '3_classificationFeatureImportanceViaLeaveOneOut';
savePath = fullfile(plotSaveFolder, saveName);
if ~Params.showOneFig
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, oneFigureHandle);
end 
    
if ~Params.showOneFig
    close all
else 
    set(0, 'CurrentFigure', oneFigureHandle);
    clf reset
end 


%% Plot comparison of classification performance 
%
if ~Params.showOneFig
    F1 = figure;
end 

cmap = colormap(winter(num_classification_models));
jitter_level = 0.1;
dot_size = 80;

set(gcf, 'Position', [0, 0, num_classification_models*150, 600]);
for classifier_idx = 1:num_classification_models
    

    x_vals = normrnd(classifier_idx, jitter_level, [clf_num_kfold_repeat, 1]);
    scatter(x_vals, model_loss(:, classifier_idx), dot_size, cmap(classifier_idx, :), 'filled')
    hold on

end 

dummy_misclassification_rate = 1 - 1 / length(unique(y));
yline(dummy_misclassification_rate, 'LineWidth', 1.5);
text(num_classification_models - 0.5, dummy_misclassification_rate+0.02, ...
    'Random chance', 'color', [0.5, 0.5, 0.5])
ylim([0, 1])
ylabel('Misclassification rate')
xticks(1:num_classification_models)
xticklabels(classification_models)
xlabel('Classifier')
set(gcf, 'color', 'white')
set(gca, 'TickDir', 'Out');
set(gca, 'box', 'off');

saveName = '2_allclassifiersMisclassificationRatePerKFold';
savePath = fullfile(plotSaveFolder, saveName);
if ~Params.showOneFig
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, oneFigureHandle);
end 
    
if ~Params.showOneFig
    close all
else 
    set(0, 'CurrentFigure', oneFigureHandle);
    clf reset
end 

%% Plot confusion matrix of each classifier 

if ~isfield(Params, 'oneFigure')
    F1 = figure;
end 

set(gcf, 'Position', [0, 0, 300 * num_classification_models, 300]);
for classifier_idx = 1:num_classification_models
    subplot(1, num_classification_models, classifier_idx)
    % plot confusion matrix
    y_predicted = model_predictions(1, classifier_idx, :);
    cm = confusionchart(y, y_predicted(:));
    title(classification_models{classifier_idx})
end 

set(gcf, 'color', 'white')
saveName = '1_allclassifiersConfusionMatrix';
savePath = fullfile(plotSaveFolder, saveName);
if ~Params.showOneFig
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, oneFigureHandle);
end 
    
if ~Params.showOneFig
    close all
else 
    set(0, 'CurrentFigure', oneFigureHandle);
    clf reset
end 

%% Plot classification performance of each classifier against shuffles

SVMModel = fitcecoc(X_processed,y);
CVSVMModel = crossval(SVMModel, 'KFold',2);
%[~,scorePred] = kfoldPredict(CVSVMModel);
original_loss = CVSVMModel.kfoldLoss;

shuffle_loss = zeros(num_shuffle, 1);
for shuffle = 1:num_shuffle
    y_shuffled = y(randperm(length(y)));
    shuffled_SVMModel = fitcecoc(X_processed, y_shuffled);
    shuffled_CVSVMModel = crossval(shuffled_SVMModel, 'KFold',2);
    shuffle_loss(shuffle) = shuffled_CVSVMModel.kfoldLoss;
end 

%% Plot classification performance 
%{
if ~isfield(Params, 'oneFigure')
    F1 = figure;
end 

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
savePath = fullfile(plotSaveFolder, saveName);
if ~Params.showOneFig
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
    else 
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, oneFigureHandle);
end 
    
if ~Params.showOneFig
    close all
else 
    set(0, 'CurrentFigure', oneFigureHandle);
    clf reset
end 
%}
%% Do regression (currently only for DIVs)
if strcmp(classificationTarget, 'AgeDiv')
    regression_model_predictions = zeros(clf_num_kfold_repeat, num_classification_models, length(y));
    num_regressor_models = length(Params.regression_models);
    regression_model_loss = zeros(reg_num_kfold_repeat, num_regressor_models);

    for kfold_repeat_idx = 1:clf_num_kfold_repeat
        for regressor_idx = 1:num_regressor_models
            regressor_name = Params.regression_models{regressor_idx};

            if strcmp(regressor_name, 'svmRegressor')
                regressionModel = fitrsvm(X_processed, y);
            elseif strcmp(regressor_name, 'regressionTree')
                regressionModel = fitrtree(X_processed, y);
            elseif strcmp(regressor_name, 'ridgeRegression')
                cv_regression_model = fitrlinear(X_processed, y, 'Learner', 'leastsquares', ...
                    'Regularization','ridge', 'KFold', 2);
            elseif strcmp(regressor_name, 'fforwardNN')
                regressionModel = fitrnet(X_processed, y);
            else 
                fprintf('WARNING: invalid regressor_name specified')
            end 

            if ~strcmp(regressor_name, 'ridgeRegression')
                cv_regression_model = crossval(regressionModel, 'KFold',2);
            end 

            regression_model_predictions(kfold_repeat_idx, regressor_idx, :) = kfoldPredict(cv_regression_model);

            regression_model_loss(kfold_repeat_idx, regressor_idx) = cv_regression_model.kfoldLoss;

        end 
    end 


    %% Plot regression model performance comparison 

    if ~isfield(Params, 'oneFigure')
        F1 = figure;
    end 

    cmap = colormap(winter(num_regressor_models));
    jitter_level = 0.1;
    dot_size = 80;

    set(gcf, 'Position', [0, 0, 150 * num_regressor_models, 600]);
    for regressor_idx = 1:num_regressor_models

        x_vals = normrnd(regressor_idx, jitter_level, [reg_num_kfold_repeat, 1]);
        scatter(x_vals, regression_model_loss(:, regressor_idx), dot_size, cmap(regressor_idx, :), 'filled')
        hold on

    end 

    mean_y = mean(y);
    dummy_regressor_mse = mean((y - mean_y).^2);
    yline(dummy_regressor_mse, 'LineWidth', 1.5);
    text(num_regressor_models - 0.5, dummy_regressor_mse*1.02, ...
        'Random chance', 'color', [0.5, 0.5, 0.5])

    ylabel('Mean squared error')
    xlabel('Regression models')
    xticks(1:num_regressor_models)
    xticklabels(Params.regression_models)
    ylim([0, inf])
    set(gcf, 'color', 'white')

    saveName = 'allRegressorMSEPerKFold';
    savePath = fullfile(plotSaveFolder, saveName);
    if ~Params.showOneFig
            pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
        else 
            pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, oneFigureHandle);
    end 

    if ~Params.showOneFig
        close all
    else 
        set(0, 'CurrentFigure', oneFigureHandle);
        clf reset
    end 

    %% Plot regression actual vs. predicted for different models (only applies to DIV)

    if ~isfield(Params, 'oneFigure')
        F1 = figure;
    end 

    set(gcf, 'Position', [0, 0, 300 * num_regressor_models, 300]);
    for regressor_idx = 1:num_regressor_models
        subplot(1, num_regressor_models, regressor_idx)
        % plot confusion matrix
        y_predicted = regression_model_predictions(1, regressor_idx, :);
        scatter(y, y_predicted(:), dot_size, 'filled');
        hold on
        title(Params.regression_models{regressor_idx})
        xlabel('Observed')
        ylabel('Predicted')
    end 


    xlim([min(y), max(y)])
    ylim([min(y), max(y)])

    set(gcf, 'color', 'white')
    saveName = 'allRegressorActualVsPredicted';
    savePath = fullfile(plotSaveFolder, saveName);


    if ~Params.showOneFig
            pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
        else 
            pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, oneFigureHandle);
    end 

    if ~Params.showOneFig
        close all
    else 
        set(0, 'CurrentFigure', oneFigureHandle);
        clf reset
    end 
end



%% Regression : compare to shuffles
%{
% TODO: add percentile plot here as well
%
regressionModel = fitrtree(X_processed, y);
CVSVMModel = crossval(regressionModel, 'KFold',2);
% [~,scorePred] = kfoldPredict(CVSVMModel);
original_loss = CVSVMModel.kfoldLoss;

shuffle_loss = zeros(num_shuffle, 1);
for shuffle = 1:num_shuffle
    y_shuffled = y(randperm(length(y)));
    shuffled_regressionModel = fitrtree(X_processed, y_shuffled);
    shuffled_CVSVMModel = crossval(shuffled_regressionModel, 'KFold',2);
    shuffle_loss(shuffle) = shuffled_CVSVMModel.kfoldLoss;
end 

if ~isfield(Params, 'oneFigure')
    F1 = figure;
end 

xline(original_loss);
hold on 
num_histogram_bins = 50;
histogram(shuffle_loss, num_histogram_bins);

xlabel('Mean squared error')
ylabel('Number of shuffles')
set(gcf, 'color', 'white');


saveName = 'regressionTreeMSEVersusShuffle';
savePath = fullfile(plotSaveFolder, saveName);

if ~Params.showOneFig
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, F1);
    else 
        pipelineSaveFig(savePath, Params.figExt, Params.fullSVG, oneFigureHandle);
end 
    
if ~Params.showOneFig
    close all
else 
    set(0, 'CurrentFigure', oneFigureHandle);
    clf reset
end 

%}





%% Plot some examples of the regression to make sure I know what I am doing

%{
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

if ~isfield(Params, 'oneFigure')
    F1 = figure;
end 

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

if ~isfield(Params, 'oneFigure')
    F1 = figure;
end 

subplot(1, 2, 1)
plot(y_train);
hold on
plot(y_train_predicted)
subplot(1, 2, 2)
plot(y_test);
hold on
plot(y_test_predicted)
%}

end 