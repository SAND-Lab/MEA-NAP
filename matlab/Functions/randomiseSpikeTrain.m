function randSpikeTimes = randomiseSpikeTrain(spikeTimes, duration, method)

    if strcmp(method, 'wrap')
        minTime = 0; 
        maxTime = duration;
        cutTime = (maxTime-minTime) .* rand(1,1) + minTime;

        beforeCutTimeIdx = spikeTimes < cutTime;
        afterCutTimeIdx = spikeTimes >= cutTime;

        randSpikeTimes(beforeCutTimeIdx) = (duration - cutTime) + spikeTimes(beforeCutTimeIdx);
        randSpikeTimes(afterCutTimeIdx) = spikeTimes(afterCutTimeIdx) - cutTime;
    end 

end 