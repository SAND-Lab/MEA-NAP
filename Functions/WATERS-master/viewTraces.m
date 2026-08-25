clearvars; clc;
dataPath = '/Volumes/Crucial X8/flexible-electrodes/data/mat_data/merged';
addpath(dataPath);
files = dir(fullfile(dataPath, '*.mat'));
f = randi(length(files),1);
file = load(files(f).name);
%%
close all
global fs duration TP FP FN nSamples
fs = file.fs;
TP = 0;
FP = 0;
FN = 0;
nSamples = 0;
duration = length(file.dat)/fs;

channel = randi(60,1); % Look into a random channel
channel = 23;
trace_raw = file.dat(1:fs*60, channel);
% trace_raw = file.dat(:,channel);
spikeTimes = struct;

% PARAMS
Ns = 2;
multiplier = 3.0;
% wnames = {'mea','bior1.5','bior1.3', 'db2'};
wnames = {'mea'};
Wid = [.5, 1];
L = -0.3765;
nSpikes = 500;
ttx = 0;
minPeakThrMultiplier = -5;
maxPeakThrMultiplier = -100;
posPeakThrMultiplier = 100;

params.multiple_templates = 0;
params.multi_template_method = 0;
channelInfo = 0;
plot_folder = '';
params.run_detection_in_chunks = 0;
params.chunk_length = 60; 
threshold_calculation_window = [0 100];
customAbsThr = 0;
params.filterLowPass = 300;
params.filterHighPass = 800;
params.remove_artifacts = 0;
params.refPeriod = 2; 
params.getTemplateRefPeriod = 2;

% Run CWT spike detection
tic
for wname = wnames
    good_wname = strrep(wname,'.','p');
    
    %[spikeTimes.(good_wname{1}), ~, trace] = detectSpikesCWT(...
    %    trace_raw, fs, Wid, wname{1}, L, Ns, multiplier, nSpikes, ttx, ...
    %    minPeakThrMultiplier, maxPeakThrMultiplier, posPeakThrMultiplier);

    [spikeFrames.(good_wname{1}), spikeWaves, trace, threshold] = ...
                            detectSpikesCWT(trace_raw, fs, Wid, wname{1}, L, Ns, ...
                            multiplier,nSpikes,ttx, minPeakThrMultiplier, ...
                            maxPeakThrMultiplier, posPeakThrMultiplier, ...
                            params.multiple_templates, params.multi_template_method, ...
                            channelInfo, plot_folder, params.run_detection_in_chunks, ...
                            params.chunk_length, threshold_calculation_window, ...
                            customAbsThr, params.filterLowPass, params.filterHighPass, ...
                            params.remove_artifacts, params.refPeriod, params.getTemplateRefPeriod);

end
toc

% Threshold spike detection
[frames, ~, threshold] = detectSpikesThreshold(trace, 3, 0.1, fs, 0);
[spikeTimes.('threshold'), spike_waves_thr] = alignPeaks(find(frames==1), trace, 10,...
    1, minPeakThrMultiplier, maxPeakThrMultiplier, posPeakThrMultiplier);

% Merge spikes from all methods
unique_idx = [];
spikeTimes.all = [];
[spikeTimes.('all'), unique_idx, intersect_matrix] = mergeSpikes(spikeTimes, 'all');

[~, spikeWaveforms] = alignPeaks(spikeTimes.('all'), trace, 10,...
    0, minPeakThrMultiplier, maxPeakThrMultiplier, posPeakThrMultiplier);

    
% Plot all spike markers
global bin_ms
bin_ms = 100;

figure
set(gcf,'color','w');
h = plot(trace-mean(trace), 'k', 'linewidth', .5);
hold on

% admissible = fieldnames(spikeTimes);
admissible = {'all'};
lineStyles = linspecer(length(admissible));

for m = 1:length(admissible)
    spikepos = spikeTimes.(admissible{m});
    scatter(spikepos, repmat(5*std(trace)-(m*threshold/-8), length(spikepos), 1),20, 'v', 'filled',...
        'markerfacecolor', lineStyles(m,:));
end

hold on

% Plot threshold line
yl = yline(threshold, 'magenta--', "Threshold = " + round(threshold,2) + "\muV");
yl.LabelVerticalAlignment = 'bottom';
yl.LineWidth = 1.5;
yl.FontSize = 10;

% Aesthetics
st = 1;
en = st+(bin_ms*25);
xlim([st en]);
ylim([-6*std(trace) 5*std(trace)])
pbaspect([5 1 1])
box off
title("Electrode " + channel)
set(get(get(h,'Annotation'),'LegendInformation'),'IconDisplayStyle','off');
legend(admissible, 'location', 'northeastoutside')
set(gcf, 'position', [0 200 1500 350]);

%----------------------------------------
% Create buttons and callbacks
set(gcf,'KeyPressFcn',@keys);

nextButton = uicontrol('Position',[700 1 150 30],'String','Next',...
    'Callback', @Next);

prevButton = uicontrol('Position',[500 1 150 30],'String','Previous',...
    'Callback', @Prev);

saveButton = uicontrol('Position',[1325, 120, 100, 30],'String','Save',...
    'Callback', @Save);
%----------------------------------------
%% Plot unique spike markers

bin_ms = 100;
figure
set(gcf,'color','w');
h = plot(trace-mean(trace), 'k', 'linewidth', 1);
hold on
methods = fieldnames(spikeTimes);
lineStyles=linspecer(length(methods));
clear unique_counts
unique_counts = table;

for m = 1:length(admissible)
        spks = spikeTimes.all;
        spikepos = find(unique_idx==m);
%         spikepos = find(intersect_matrix(:,m)==1);
        
        scatter(spks(spikepos), repmat(5*std(trace)-(m*threshold/-8), length(spikepos), 1), 'v', 'filled',...
            'markerfacecolor', lineStyles(m,:));
        unique_counts.(methods{m}) = length(spks(spikepos));
end
unique_counts(end-1:end-2,:) = [];

hold on

% Plot threshold line
yl = yline(threshold, 'magenta--', "Threshold = " + round(threshold,2) + "\muV");
yl.LabelVerticalAlignment = 'bottom';
yl.LineWidth = 1.5;
yl.FontSize = 10;

% Show the unique spike counts
clc
unique_counts

% Aesthetics
st = 1;
en = st+(bin_ms*25);
xlim([st en]);
ylim([-6*std(trace) 6*std(trace)])
pbaspect([5 1 1])
box off
title("Electrode " + channel)
set(get(get(h,'Annotation'),'LegendInformation'),'IconDisplayStyle','off');
legend(methods{1:end-2}, 'location', 'northeastoutside')
set(gcf, 'position', [300 300 1500 350]);


%----------------------------------------
% Create buttons and callbacks
set(gcf,'KeyPressFcn',@keys);

nextButton = uicontrol('Position',[700 1 150 30],'String','Next',...
    'Callback', @Next);

prevButton = uicontrol('Position',[500 1 150 30],'String','Previous',...
    'Callback', @Prev);

saveButton = uicontrol('Position',[1325, 120, 100, 30],'String','Save',...
    'Callback', @Save);

%% Plot unique spike waveforms
methods = fieldnames(spikeTimes);
t = tiledlayout(1, length(methods)-1);
t.Title.String = 'Spikes detected uniquely by each method';
for i = 1:length(methods)-1
    method = methods{i};
    if ~strcmp(method, 'all')
        spk_method = find(unique_idx == i);
        spk_waves_method = spikeWaveforms(spk_method, :);
        nexttile
        plot(spk_waves_method', 'linewidth', 0.1, 'color', [0.7 0.7 0.7 0.1])
        hold on
        plot(mean(spk_waves_method), 'linewidth', 1.5, 'color', [0 0 0])
        title({[method],["No. unique spikes: " + length(spk_method)]})
        box off;
        axis tight
        ylim([-6*std(trace) 5*std(trace)]);
        ylabel('Voltage [\muV]')
        set(gca, 'xcolor', 'none');
        yl = yline(threshold, 'r--');
        yl.LineWidth = 1.5;
        if i~=1
            axis off
        end
    end
end
set(gcf, 'color', 'w', 'position', [200 200 1500 500]);
set(findall(gcf,'-property','FontSize'),'FontSize', 12);
set(findall(gcf,'-property','FontName'),'FontName','Roboto')

%% Plot histograms
histogram(spikeWaveforms(:, 25),50);
box off;
%%

% tiledlayout(3,3,'tilespacing','none','padding','none')
for i = 1:length(methods)-1
    spk_method = find(unique_idx == i);
    spk_waves_method = spikeWaveforms(spk_method, :);
    hold on;
    h = histogram(spk_waves_method(:,25),100);
    h.FaceAlpha = 0.5;
    h(i) = gca;
end
hold on
xl1 = xline(threshold, 'r--', 'Threshold');
xl1.LineWidth = 2;
xlim([-inf 0])
legend(methods{1:end-1},'location','bestoutside');
set(gcf, 'color','w', 'position',[200 200 1000 500]);
xlabel('Voltage amplitude (\muV)')
ylabel('No. entries');
title('Histogram of unique spike amplitudes')

%%
figure
clear counts;
num_bins = 50;
binrng = linspace(min(spikeWaveforms(:,25)),max(spikeWaveforms(:,25)),num_bins);

for i = 1:length(methods)-1
    spk_method = find(unique_idx == i);
    spk_waves_method = spikeWaveforms(spk_method, :);
    counts(i,:) = histc(spk_waves_method(:,25), binrng);
end
countss = sum(counts);

tt = tiledlayout(length(methods)-1,1, 'tilespacing','none','padding','none');
tt.Title.String = 'Unique spike amplitudes';
cl = linspecer(length(methods)-1);
for i = 1:length(methods)-1
    nexttile
    bar(binrng, counts(i,:),'facealpha', 1, 'facecolor', [.7 .7 .7]);
    title(methods{i});
    if i~=6
        set(gca,'xcolor','none');
    end
    hold on
    box off
    xl1 = xline(threshold, 'r-');
    xl1.LineWidth = 3;
end

xlabel("Voltage amplitude ("+char(956)+"V)")
ylabel('No. entries');
set(gcf, 'color','w','position',[200,100,800,800]);
set(findall(gcf,'-property','FontSize'),'FontSize', 14);
set(findall(gcf,'-property','FontName'),'FontName','Roboto')

% Uncomment to get consistent scale across all histograms
% linkaxes([nexttile(1), nexttile(2), nexttile(3), nexttile(4), nexttile(5), nexttile(6)])
% exportgraphics(gcf, 'histogram_unique.png','resolution',600);
%%
clear counts;
figure
num_bins = 50;
binrng = linspace(min(spikeWaveforms(:,25)),max(spikeWaveforms(:,25)),num_bins);

for i = 1:length(methods)-1
    spk_method = logical(intersect_matrix(:,i));
    spk_waves_method = spikeWaveforms(spk_method, :);
    counts(i,:) = histc(spk_waves_method(:,25), binrng);
end
% countss = sum(counts);

cl = linspecer(length(methods)-1);
tt = tiledlayout(length(methods)-1,1, 'tilespacing','none','padding','none');
tt.Title.String = 'All spike amplitudes';
cl = linspecer(length(methods)-1);
for i = 1:length(methods)-1
    nexttile
    bar(binrng, counts(i,:),'facealpha', 1,'facecolor',[.7 .7 .7]);
    title(methods{i});
    if i~=6
        set(gca,'xcolor','none');
    end
    hold on
    box off
    xl1 = xline(threshold, 'r-');
    xl1.LineWidth = 3;
end
xlabel("Voltage amplitude ("+char(956)+"V)")
ylabel('No. entries');
set(gcf, 'color','w','position',[300,100,800,800]);
set(findall(gcf,'-property','FontSize'),'FontSize', 14);
set(findall(gcf,'-property','FontName'),'FontName','Roboto')
% linkaxes([nexttile(1), nexttile(2), nexttile(3), nexttile(4), nexttile(5), nexttile(6)])
% exportgraphics(gcf, 'histogram_all.png','resolution',600);

%%

% Get other features
spikes = spikeWaveforms;
halfWidth = zeros(length(spikeWaveforms),1);
peak2peak = zeros(length(spikeWaveforms),1);
for i = 1:length(spikes)
    spike = diff(spikeWaveforms(i,:));
    [pks,locs,W,~] = findpeaks(-spike,'widthreference','halfheight');
    [nvePeak,pos] = min(-pks);
    nvePeakPos = locs(pos);
    halfWidth(i) = W(pos);
    try
        [~,locs,~,~] = findpeaks(spike,'widthreference','halfprom','minpeakprominence',-nvePeak/15);
        pvePeakPos = locs(locs>nvePeakPos);
        pvePeakPos = pvePeakPos(1);
        peak2peak(i) = pvePeakPos-nvePeakPos;
    catch
        continue
    end
end

halfWidth = halfWidth(peak2peak>0);
peak2peak = peak2peak(peak2peak>0);
%%
figure
tiledlayout(2,1,'tilespacing','none','padding','none')
nexttile
histogram(halfWidth,20);
h1 = gca;
box off
axis tight
xlabel('Half width (ms)');

nexttile
histogram(peak2peak,10);
h2 = gca;
box off
axis tight
xlabel('Peak-to-peak (ms)');

linkaxes([h1,h2],'x');
h2.XTickLabel = h2.XTick/25;
h1.XTickLabel = h1.XTick/25;













%% UI functions
function keys(src, event)
global TP FP FN nSamples bin_ms
switch event.Key
    case 'rightarrow'
        Next;
    case 'leftarrow'
        Prev;
    case 'z'
        TP = TP + 1;
        nSamples = nSamples + 1;
    case 'x'
        FP = FP + 1;
        nSamples = nSamples + 1;
    case 'c'
        FN = FN + 1;
        nSamples = nSamples + 1;
    case 'r'
        FN = 0;
        TP = 0;
        FP = 0;
        nSamples = 0;
end
delete(findall(gcf,'type','annotation'));

annotation('textbox', [0.91, 0.5, 0.1, 0.1],...
    'String', "Sensitivity: " + round(TP/(TP + FN), 2)*100 + "%",...
    'FontSize', 14, 'edgecolor', 'none');

annotation('textbox', [0.91, 0.4, 0.1, 0.1],...
    'String', "Precision: " + round(TP/(TP + FP), 2)*100 + "%",...
    'FontSize', 14, 'edgecolor', 'none')
end

function Next(nextButton, EventData)
global duration fs bin_ms
lims = get(gca, 'xlim');
st = lims(2);
en = st+(bin_ms*25);
if en <= duration*fs
    set(gca,'xlim', [st en]);
end
end

function Prev(prevButton, ~)
global bin_ms
lims = get(gca, 'xlim');
en = lims(1);
st = en-(bin_ms*25);
if st >= 1
    set(gca,'xlim', [st en]);
end
end

function Save(saveButton, EventData)
% save("MPT200220_3A_DIV21" + "stats.mat", 'TP', 'TN', 'FP', 'nSamples');
end