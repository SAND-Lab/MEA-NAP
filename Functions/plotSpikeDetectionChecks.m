function plotSpikeDetectionChecks(spikeTimes,spikeDetectionResult,spikeWaveforms, ... 
    Info,Params)
%
% Make plots to check that spike detection worked properly, and plots
% spike-related statistics such as the firing rate of each unit / recorded
% from each electrode.
% 
% Parameters 
% ----------
% spikeTimes : cell array of structures
%    1 X N cell array, where N is the number of electrodes / units 
%    each item in a cell should be a 1 x 1 struct
%    which contain fields corresponding to the spike detection methods used,
%    eg. bior1p5 [numSpikes x 1 double]
% Info : structure
%     Info.FN : 
%     Info.raw_file_path : (str)
%         path to the folder including the raw matlab files
% Params.dSampF : (int)
%     down-sampling factor for plotting spike detection check 
%     normally no down sampling is necessary, so set this to be equal 
%     to the sampling rate of your acquisition system
% 
% 
% Returns 
% -------
% TODO: how does line 32 work? (seem to assume some file structure 
% where the raw file is located...

%}

FN = char(Info.FN);

% TOOD: directory create and save to folder rather than changing
% directories
mkdir(FN)
cd(FN)

%% load raw voltage trace data
raw_file_name = strcat(FN,'.mat');

if isfield(Info, 'rawData')
    raw_file_name = fullfile(Info.rawData, raw_file_name);
end 

% TODO: load to variable
load(raw_file_name);
dat = double(dat);

% convert everything to be in uV for plotting
if isa(Params.potentialDifferenceUnit, 'char')
    Params.potentialDifferenceUnit = convertCharsToStrings(Params.potentialDifferenceUnit);
end 

if isstring(Params.potentialDifferenceUnit)
    if strcmp(Params.potentialDifferenceUnit, 'V')
        dat = dat .* 10^6;
    elseif strcmp(Params.potentialDifferenceUnit, 'mV')
        dat = dat .* 10^3;
    elseif strcmp(Params.potentialDifferenceUnit, 'uV')
        dat = dat;
    end
else 
    % convert to V by provided multiplication factor, then convert to uV
    % for plotting
    dat = dat .* Params.potentialDifferenceUnit .* 10^6;
end 

%% filter voltage data 

filtered_data = zeros(size(dat));
num_chan = size(dat,2);

for ch = 1:num_chan
    lowpass = Params.filterLowPass;
    highpass = Params.filterHighPass;
    wn = [lowpass highpass] / (fs / 2); % seems like the fs here comes from workspace???
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

%% firing rate plot

p = [100 100 1200 600];
set(0, 'DefaultFigurePosition', p)

if ~isfield(Params, 'oneFigure')
     F1 = figure;
else
    Params.oneFigure.Position = p;
end 

dSampF = Params.dSampF;
for i = 1:length(methods)
    num_samples = ceil(duration_s*fs);
    spk_vec_all = zeros(1, num_samples);
    spk_matrix = zeros(num_chan, ceil(num_samples/dSampF));
    method = methods{i};
    for j = 1:num_chan
        spk_times = round(spikeTimes{j}.(method)*fs);
        spike_times{j}.(method) = spk_times;
        spike_count(j) = length(spk_times);
        spk_vec = zeros(1, num_samples);
        %                 spk_vec = zeros(1, duration_s);
        spk_vec(spk_times) = 1;
        spk_vec = spk_vec(1:num_samples);
        spk_vec_all = spk_vec_all+spk_vec;
        spk_matrix(j,:) = nansum(reshape([spk_vec(:); ...
            nan(mod(-numel(spk_vec),dSampF),1)],dSampF,[]));
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
xlabel('Time (minutes)');
ylabel('Spiking frequency (Hz)');
aesthetics
set(gca,'TickDir','out');
title({strcat(regexprep(FN,'_','','emptymatch')),' '});
legend boxoff

% Export figure
figName = 'SpikeFrequencies';

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 

%% examples traces
p = [100 100 1400 800];
set(0, 'DefaultFigurePosition', p)

if ~isfield(Params, 'oneFigure')
    F1 = figure;
else
    Params.oneFigure.Position = p;
end 

tiledlayout(5,2,'TileSpacing','Compact');

% l iterates through the 9 example traces?
for l = 1:9
    
    bin_ms = 30;  % What is this???
    channel = randi([1,num_chan],1);
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
        scatter(spike_train, repmat(5*std(trace)-m*(0.5*std(trace)), ...
            length(spike_train), 1), 15, 'v', 'filled', ... 
            'markerfacecolor',cmap(colors(m),:), ... 
            'markeredgecolor', cmap(colors(m),:), 'linewidth',0.1);
    end
    methodsl = strrep(methods, 'p','.');
    
    % Why is the try catch required here???
    % st is a random spike train???

    if isempty(spike_train)
        fprintf('WARNING: spike_train is empty, not going to plot example traces \n')
        continue
    end 

    st = randi([1 length(spike_train)]);
    st = spike_train(st);
    if st+15*25 < length(trace)
        xlim([st-bin_ms*25 st+bin_ms*25]);
    else
        xlim([st-bin_ms*25 inf]);
    end

    ylim([-6*std(trace) 5*std(trace)])
    box off
    set(gca,'xcolor','none');
    ylabel('Amplitude (\muV)');
    axis fill
    title({["Electrode "+channel], [(st-bin_ms*25)/Params.dSampF + " - " + (st+bin_ms*25)/Params.dSampF + " s"]})
    aesthetics
    set(gca,'TickDir','out');
end
hL = legend('Filtered voltage trace', methodsl{:});
newPosition = [0.6 0.12 0.1 0.1];
newUnits = 'normalized';
set(hL,'Position', newPosition,'Units', newUnits,'Box','off');
title({strcat(regexprep(FN,'_','','emptymatch')),' '});


% Export figure
figName = 'ExampleTraces';

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 


%% waveforms
[~, unique_idx, ~] = mergeSpikes(spike_times{channel},'all');

p = [100 100 600 700];
set(0, 'DefaultFigurePosition', p)

if ~isfield(Params, 'oneFigure')
    F1 = figure;
else
    Params.oneFigure.Position = p;
end 

t = tiledlayout(2, ceil(length(methods)/2), 'tilespacing','none','padding','none');
t.Title.String = {strcat(regexprep(FN,'_','','emptymatch')),' ',["Unique spikes by method from electrode " + channel]};
for i = 1:length(methods)
    method = methods{i};
    if ~strcmp(method, 'all')
        spk_method = find(unique_idx == i);
        spk_waves_method = spikeWaveforms{channel}.(method);

        % convert spike waveform to the appropriate units as well 
        if isstring(Params.potentialDifferenceUnit)
            if strcmp(Params.potentialDifferenceUnit, 'V')
                spk_waves_method = spk_waves_method .* 10^6;
            elseif strcmp(Params.potentialDifferenceUnit, 'mV')
                spk_waves_method = spk_waves_method .* 10^3;
            elseif strcmp(Params.potentialDifferenceUnit, 'uV')
                spk_waves_method = spk_waves_method;
            end
        else 
            % convert to V by provided multiplication factor, then convert to uV
            % for plotting
            spk_waves_method = spk_waves_method .* Params.potentialDifferenceUnit .* 10^6;
        end 

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


% Export figure
figName = 'Waveforms';

if ~isfield(Params, 'oneFigure')
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, F1);
else 
    pipelineSaveFig(figName, Params.figExt, Params.fullSVG, Params.oneFigure);
end 

if ~isfield(Params, 'oneFigure')
    close all
else 
    set(0, 'CurrentFigure', Params.oneFigure);
    clf reset
end 

end