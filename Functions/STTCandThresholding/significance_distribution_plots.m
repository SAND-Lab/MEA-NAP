function F1 = significance_distribution_plots(dist1,repVal,adjM,genotype)
% H Smith, Cambridge, 2021
% INPUTS:
%   dist1 = Cell where dist1{i} is double size(adjM) where element value
%       at dist1{i} is threshold value at repVal(i)
%   repVal = 1 x n vector where element number corresponds to number of
%       data scrambling repeats have been used to create matrix in dist1
%   adjM = original adjacency matrix
%   genotype:
%       1 = Wild-type
%       0 = Knockout

% REQUIRED FUNCTIONS
%   distinguishable_colors

p = [20 20 1250 850];
set(0, 'DefaultFigurePosition', p)
F1 = figure;
tiledlayout(3,5)
% Colours
if genotype == 1 % Wild-type
    c = [0.471 0.674 0.188]; % green
    set(F1,'defaultAxesColorOrder',[[0 0.5 0];[0 0 0]]);
elseif genotype == 0 % Knockout
    c = [0.027 0.306 0.659]; % dark blue
    set(F1,'defaultAxesColorOrder',[c;[0 0 0]]);
end

a = repVal;
num_nodes = length(adjM);

%% Changing threshold
% Collect means & variances
vS = cell(1,length(a));
mS = zeros(1,length(a)); % Preallocate means vector
for i = 1:length(a) % Repeat for each repNum
    tT = dist1{i}; % Threshold values
    tT(~triu(rot90(ones(size(tT))))) = NaN; % Remove 1/2 data
    mS(i) = nanmean(tT(:)); % Find mean
    
    vS{i} = zeros(size(adjM)); % Store of variances
    for j = 1:numel(adjM) % For each element
        tV = zeros(1,i); % Threshold values start : repNum
        for k = 1:length(tV)
            tV(k) = dist1{k}(j);
        end
        vV = var(tV); % Variance of tV
        vS{i}(j) = vV; % Assign to store
    end
end

% Remove 1/2 of data to get rid of repeats
for i = 1:length(vS)
    vS{i}(~triu(rot90(ones(size(vS{i}))))) = NaN; % like 'triu' with NaNs
    vS{i} = vS{i}(:); % Vectorise
    vS{i}(isnan(vS{i})) = []; % Remove NaNs
end

% Calculate std for each repNum
sS = zeros(1,length(a));
for i = 1:length(sS)
    sS(i) = sum(vS{i},'all') / numel(vS{i}); % Average variance
end
sS = sqrt(sS); % Produce std from sqrt(average variance)

X = a; % Assign x axis
ValMean = mS;
UpperStd = ValMean + sS;
LowerStd = ValMean - sS;

coeffVar = sS ./ mS;

nexttile(1,[1 5])
Xf = [X,fliplr(X)]; % Create continuous x value arrow for plotting
Yf = [UpperStd,fliplr(LowerStd)]; % create y values for out and then back
yyaxis left
h = fill(Xf, Yf, c, 'edgecolor', 'none');
set(h,'facealpha',0.3);
hold on
plot(X, ValMean,'-', 'Color', c, 'LineWidth', 2)
xlabel('Number of Repeats')
ylabel('Average threshold value')
yyaxis right
plot(X, coeffVar,'-', 'Color', 'k', 'LineWidth', 1)
ylabel('Coefficient of Variance')
xlim([0 a(end)]);
title('Change in threshold')
aesthetics
set(gca,'TickDir','out');

%% Individual edge changes
% Collect std's
vS = cell(1,length(a));
for i = 1:length(a) % Repeat for each repNum
    vS{i} = zeros(size(adjM)); % Store of variances
    for j = 1:numel(adjM) % For each element
        tV = zeros(1,i); % Threshold values start : repNum
        for k = 1:length(tV)
            tV(k) = dist1{k}(j);
        end
        vV = std(tV); % Standard deviation of tV
        vS{i}(j) = vV; % Assign to store
    end
end

% Remove 1/2 of data to get rid of repeats
tCopy = dist1;
for i = 1:length(tCopy)
    tCopy{i}(~triu(rot90(ones(size(tCopy{i}))))) = NaN; % like 'triu' with NaNs
    tCopy{i} = tCopy{i}(:); % Vectorise
    tCopy{i}(isnan(tCopy{i})) = []; % Remove NaNs
end
for i = 1:length(vS)
    vS{i}(~triu(rot90(ones(size(vS{i}))))) = NaN; % like 'triu' with NaNs
    vS{i} = vS{i}(:); % Vectorise
    vS{i}(isnan(vS{i})) = []; % Remove NaNs
end

% Plot
X = a; % Assign x axis
numEl = length(vS{1});
randSelect = randi(numEl,1,12);
s = 1:numEl;
randEl = s(randSelect);
% colors = distinguishable_colors(length(randEl));
cdist = round(linspace(1, 256, numEl));
cmap = cmocean('thermal');
colors = cmap(cdist,:);
nexttile(6,[1 5])
hold on
for i = 1:length(randEl)
    sDu = zeros(1,length(vS));
    ValMean = zeros(1,length(vS));
    for j = 1:length(vS)
        sDu(j) = vS{j}(randEl(i));
        ValMean(j) = tCopy{j}(randEl(i));
    end
    hold on
    plot(X, ValMean,'-','Color',colors(i,:),'LineWidth', 1)
end
xlim([0 a(end)])
xlabel('Number of Repeats')
ylabel('Threshold value')
title('Raw Data Samples')
aesthetics
set(gca,'TickDir','out');

%% Thresholded adjMs
p = round(linspace(1,length(a),5));
for q = 1:5
    nexttile(10+q)
    hold on
    use = dist1{p(q)};
    blank = zeros(num_nodes,num_nodes);
    for i = 1:length(blank)
        for j = 1:length(blank)
            if (use(i,j) > adjM(i,j)) && (adjM(i,j) ~= 0)
                blank(i,j) = adjM(i,j);
            end
        end
    end
    imagesc(blank)
    xlim([1 length(adjM)]);
    ylim([1 length(adjM)]);
    axis square
    title(['discarded edges (rep' num2str(a(p(q))-1) ')'])
    aesthetics
    set(gca,'TickDir','out');
end

end