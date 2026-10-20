function getMemoryUsage()
%GETMEMORYUSAGE Summary of this function goes here
%   Detailed explanation goes here
% Get memory usage 
if ispc 
    user = memory;
    total_mem_usage_mb = user.MemUsedMATLAB / (10.^6);
    
else
    [tmp pid] = system('pgrep MATLAB');
    pid_split = strsplit(pid);
    total_mem_usage_mb = 0;
    for pid_idx = 1:length(pid_split)-1
        [tmp mem_usage] = system(['cat /proc/' strtrim(pid_split{pid_idx}) '/status | grep VmSize']);
        mem_usage_mb = round(str2num(strtrim(extractAfter(extractBefore(mem_usage, ' kB'), ':'))) / 1000);
        total_mem_usage_mb = total_mem_usage_mb + mem_usage_mb;
    end
    
    
end

fprintf(sprintf('MATLAB memory used: %.f MB \n', total_mem_usage_mb))

end

