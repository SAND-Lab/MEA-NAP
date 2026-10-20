function checkIfAnySpikes(spikeTimes, ExpName)

    spikeDetectionMethodUsed = fieldnames(spikeTimes{1}); 
    all_method_spikes_detected = 0;
    for nmethod = 1:length(spikeDetectionMethodUsed)
        methodName = spikeDetectionMethodUsed{nmethod}; 
        method_detected_spikes = 0;
        for channel = 1:length(spikeTimes)
            if ~isempty(spikeTimes{channel})
                method_detected_spikes = method_detected_spikes + length(spikeTimes{channel}.(methodName));
            end 
        end 
        if method_detected_spikes == 0 
            fprintf(sprintf('No spikes detected in any channels in %s using %s \n', ExpName, methodName))
        end 
        all_method_spikes_detected = all_method_spikes_detected + method_detected_spikes;
    end 

    if all_method_spikes_detected == 0 
        fprintf(sprintf(['WARNING: In %s, no spikes were detected in any channels using any of the specified detection methods, \n ' ...
            'consider removing this dataset from the analysis list or re-running spike detection,\n' ...
            'otherwise downstream analysis may fail. \n'], ExpName))
    end 


end 