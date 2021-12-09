function plotSpikeDetectionChecks(spikeTimes,spikeDetectionResult,spikeWaveforms,Info,Params)

FN = char(Info.FN);

mkdir(FN)
cd(FN)

%% frequency plot

raw_file_name = strcat(FN,'.mat');
load(raw_file_name);
dat = double(dat);
filtered_data = zeros(size(dat));
num_chan = size(dat,2);

for ch = 1:num_chan
    lowpass = 600;
    highpass = 8000;
    wn = [lowpass highpass] / (fs / 2);
    filterOrder = 3;
    [b, a] = butter(filterOrder, wn);
    filtered_data(:,ch) = filtfilt(b, a, dat(:,ch));
end


methods = fieldnames(spikeTimes{1});
methods = sort(methods);

bin_s = 10;
Params.fs = spikeDetectionResult.params.fs;
duration_s = spikeDetectionResult.params.duration;
channel = 15;
while channel == 15
    channel = randi([1,num_chan],1);
end
trace = filtered_data(:, channel);


p = [100 100 1200 600];
set(0, 'DefaultFigurePosition', p)
F1 = figure;

dSampF = 25000;
for i = 1:length(methods)
    spk_vec_all = zeros(1, duration_s*fs);
    spk_matrix = zeros(num_chan, duration_s*fs/dSampF);
    method = methods{i};
    for j = 1:num_chan
        spk_times = round(spikeTimes{j}.(method)*fs);
        spike_times{j}.(method) = spk_times;
        spike_count(j) = length(spk_times);
        spk_vec = zeros(1, duration_s*fs);
        %                 spk_vec = zeros(1, duration_s);
        spk_vec(spk_times) = 1;
        spk_vec = spk_vec(1:duration_s*fs);
        spk_vec_all = spk_vec_all+spk_vec;
        spk_matrix(j,:) = nansum(reshape([spk_vec(:); nan(mod(-numel(spk_vec),dSampF),1)],dSampF,[]));
    end
    spike_counts.(method) = spike_count;
    spike_freq.(method) = spike_count/duration_s;
    spk_matrix_all.(method) = spk_matrix;
    down_spk_matrix_all = mean(spk_matrix,1);
    plot(down_spk_matrix_all, 'linewidth', 2)
    %             plot(movmean(spk_vec_all, bin_s*fs), 'linewidth', 2)
    hold on
end
xticks((duration_s)/(duration_s/60):(duration_s)/(duration_s/60):duration_s)
xticklabels({'1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17'})
xlim([0 duration_s])
legend(strrep(methods, 'p','.'), 'location','northeastoutside');
xlabel('Time (s)');
ylabel('Spiking frequency (Hz)');
aesthetics
set(gca,'TickDir','out');
title({strcat(regexprep(FN,'_','','emptymatch')),' '});
legend boxoff

if Params.figMat == 1
    saveas(gcf,'SpikeFrequencies.fig');
end

if Params.figPng == 1
    saveas(gcf,'SpikeFrequencies.png');
end

if Params.figEps == 1
    saveas(gcf,'SpikeFrequencies.eps');
end

close all

%% examples traces
p = [100 100 1400 800];
set(0, 'DefaultFigurePosition', p)
F1 = figure;
tiledlayout(5,2,'TileSpacing','Compact');
for l = 1:9
    
    bin_ms = 30;
    channel = 15;
    while channel == 15
        channel = randi([1,num_chan],1);
    end
    trace = filtered_data(:, channel);
    
    nexttile
    cmap = jet;
    colors = round(linspace(1,256,length(methods)));
    plot(trace, 'k-')
    hold on
    
    for m = 1:length(methods)
        method = methods{m};
        spike_train = spikeTimes{channel}.(method);
        switch spikeDetectionResult.params.unit
            case 's'
                spike_train = spike_train * fs;
            case 'ms'
                spike_train = spike_train * fs/1000;
            case 'frames'
        end
        color = parula(colors(m));
        scatter(spike_train, repmat(5*std(trace)-m*(0.5*std(trace)), length(spike_train), 1), 15, 'v', 'filled','markerfacecolor',cmap(colors(m),:), 'markeredgecolor', cmap(colors(m),:), 'linewidth',0.1);
    end
    methodsl = strrep(methods, 'p','.');
    
    try
    st = randi([1 length(spike_train)]);
    st = spike_train(st);
    if st+15*25 < length(trace)
        xlim([st-bin_ms*25 st+bin_ms*25]);
    else
        xlim([st-bin_ms*25 inf]);
    end
    catch
    end
    ylim([-6*std(trace) 5*std(trace)])
    box off
    set(gca,'xcolor','none');
    ylabel('Amplitude (\muV)');
    axis fill
    title({["Electrode "+channel], [(st-bin_ms*25)/25000 + " - " + (st+bin_ms*25)/25000 + " s"]})
    aesthetics
    set(gca,'TickDir','out');
end
hL = legend('Filtered voltage trace', methodsl{:});
newPosition = [0.6 0.12 0.1 0.1];
newUnits = 'normalized';
set(hL,'Position', newPosition,'Units', newUnits,'Box','off');
title({strcat(regexprep(FN,'_','','emptymatch')),' '});

% if Params.figMat == 1
%     saveas(gcf,strcat(FN,'_ExampleTraces.fig'));
% end
if Params.figPng == 1
    saveas(gcf,'ExampleTraces.png');
end
if Params.figEps == 1
    saveas(gcf,'ExampleTraces.eps');
end

close all

%% waveforms
[~, unique_idx, ~] = mergeSpikes(spike_times{channel},'all');

p = [100 100 600 700];
set(0, 'DefaultFigurePosition', p)
F1 = figure;

t = tiledlayout(2, ceil(length(methods)/2), 'tilespacing','none','padding','none');
t.Title.String = {strcat(regexprep(FN,'_','','emptymatch')),' ',["Unique spikes by method from electrode " + channel]};
for i = 1:length(methods)
    method = methods{i};
    if ~strcmp(method, 'all')
        spk_method = find(unique_idx == i);
        spk_waves_method = spikeWaveforms{channel}.(method);
        if size(spk_waves_method,2) > 1000
            spk_waves_method = spk_waves_method(:, round(linspace(1,length(spk_waves_method),1000)));
        end
        nexttile
        plot(spk_waves_method', 'linewidth', 0.1, 'color', [0.7 0.7 0.7])
        hold on
        plot(mean(spk_waves_method), 'linewidth', 1.5, 'color', [0 0 0])
        title({[method]})
        box off;
        axis tight
        pbaspect([1,2,1]);
        ylim([-6*std(trace) 5*std(trace)]);
        ylabel('Voltage [\muV]')
        set(gca, 'xcolor', 'none');
        aesthetics
    end
end

if Params.figMat == 1
    saveas(gcf,'Waveforms.fig');
end

if Params.figPng == 1
    saveas(gcf,'Waveforms.png');
end

if Params.figEps == 1
    saveas(gcf,'Waveforms.eps');
end

close all
end