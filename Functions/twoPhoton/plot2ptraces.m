function [outputArg1,outputArg2] = plot2ptraces(F, denoisedF, cell_idx, oneFigureHandle)
%PLOT2PTRACES Summary of this function goes here
%   Detailed explanation goes here

figure;
cell_idx = 1;
F = readNPY('/Users/timothysit/Downloads/exmaple2pdata/F.npy');
Fdenoised = readNPY('/Users/timothysit/Downloads/exmaple2pdata/Fdenoised.npy');
peakStartFrames = readNPY('/Users/timothysit/Downloads/exmaple2pdata/peakStartFrames.npy');
peakStartFrames_cell = peakStartFrames(cell_idx, :);
peakStartFrames_cell = peakStartFrames_cell(~isnan(peakStartFrames_cell));

F_cell = F(cell_idx, :);
Fdenoised_cell = Fdenoised(cell_idx, :);

subplot(3, 1, 1)
plot(F_cell, 'LineWidth', 2)
ylabel('Fluorescence')

subplot(3, 1, 2)
F_scaled = (F_cell - min(F_cell)) / (max(F_cell) - min(F_cell)) * max(Fdenoised_cell);
plot(F_scaled, 'LineWidth', 2)
hold on 
plot(Fdenoised_cell, 'LineWidth', 2)
ylabel('Arbitrary units')
legend('Scaled', 'Denoised')

subplot(3, 1, 3)
plot(Fdenoised_cell, 'LineWidth', 2)
hold on 
num_peaks = length(peakStartFrames_cell);
peak_plot_heights = repmat(max(Fdenoised_cell) * 1.2, num_peaks);
scatter(peakStartFrames_cell, peak_plot_heights)
ylabel('Arbitrary units')
legend('Denoised', 'Peaks')
xlabel('Recording frames')

end

