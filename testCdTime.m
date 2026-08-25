numChanges = 100;

tic;
dir1 = '/Users/timothysit/AnalysisPipeline';
% dir2 = '/Users/timothysit/AnalysisPipeline/OutputData01Sep2022/1_SpikeDetection';
dir2 = '/Volumes/Elements/MAT_files/AnalysisPipeline/OutputData29Oct2022/1_SpikeDetection/1A_SpikeDetectedData';
for nIdx = 1:numChanges 
    fprintf(sprintf('Running %.f \n', num2str(nIdx)))
    cd(dir1)
    cd(dir2)
end 
toc 