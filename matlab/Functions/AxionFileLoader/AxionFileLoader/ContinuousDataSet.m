%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef ContinuousDataSet < DataSet

    properties (GetAccess = public, SetAccess = private)
        DataSetNames;
        Duration;
    end

    methods
        function obj = ContinuousDataSet(varargin)
            obj@DataSet(varargin{1});
            obj.mLoadData = @obj.LoadRawData;
            switch nargin
                case 1
                    %drop to end
                case 2
                    if(isa(varargin{2}, 'ContinuousBlockVectorHeaderEntry'))
                        aContinuousHeader = varargin{2};
                        fChannelArray = obj.ChannelArray;
                        obj.DataSetNames = aContinuousHeader.DataSetNames;
                        obj.ChannelArray = fChannelArray.GetNewForChannels( ...
                            fChannelArray.Channels(arrayfun(@(a)(fChannelArray.LookupChannelID(a)),[aContinuousHeader.ChannelIDs{:}])));
                        sourceDuration = aContinuousHeader.Duration;
                        if isempty(sourceDuration)
                            obj.Duration = double(obj.DataRegionLength) / ...
                                double(obj.SamplingFrequency * obj.NumBytesPerBlock);
                        else
                            obj.Duration = aContinuousHeader.Duration;
                        end
                        return;
                    end
                otherwise
                    error('Unexpected aarguments')
            end
            obj.DataSetNames = [];
            obj.Duration = double(obj.DataRegionLength) / ...
                double(obj.SamplingFrequency * obj.NumBytesPerBlock);
        end

        function aData = LoadRawData(this, varargin)
            fLoadArgs = LoadArgs(varargin);
            fTargetWell = fLoadArgs.Well;
            fTargetElectrode = fLoadArgs.Electrode;

            fChannelsToLoad = DataSet.get_channels_to_load(this.ChannelArray, fTargetWell, fTargetElectrode);

            fDimensions = fLoadArgs.Dimensions;
            if(isempty(fDimensions))
                fDimensions = LoadArgs.ByElectrodeDimensions;
            end

            fSubsamplingFactor = fLoadArgs.SubsamplingFactor;

            aData = this.GetContinuousWaveforms( ...
                fChannelsToLoad, ...
                fLoadArgs.Timespan, ...
                fDimensions, ...
                fSubsamplingFactor);
        end
   end

   methods(Access = private)
        function Waveforms = GetContinuousWaveforms(...
            this, ...
            aChannelsToLoad, ...
            aTimeRange, ...
            aDimensions, ...
            aSubsamplingFactor)

            fSampleFreq =  this.SamplingFrequency;
            fChannelCount = int64(this.NumChannelsPerBlock);
            fSampleSize = int64(BlockVectorSampleType.GetSizeInBytes(this.SampleType));
            fFreadPrecision = int64(BlockVectorSampleType.GetFreadPrecision(this.SampleType));

            fIsVoltage = this.IsRawVoltage;
            fIsContractility = this.IsRawContractility;

            fseek(this.FileID, int64(this.DataRegionStart), 'bof');
            fStart = 0;

            fBytesPerSecond = fSampleFreq * fChannelCount * fSampleSize;
            fMaxTime = double(this.DataRegionLength) / double(fBytesPerSecond);

            % Read data
            if ~strcmp(aTimeRange, 'all')
                fStart = aTimeRange(1);
                fEnd =aTimeRange(2);

                if(fStart >= fEnd)
                    warning('Invalid timespan argument: end time < start time. No valid waveform can be returned.');
                    Waveforms = Waveform.empty;
                    return;
                end

                fSkipInitialSamples = int64(fStart * fSampleFreq);
                fSkipInitialBytes = fSkipInitialSamples * fChannelCount * fSampleSize;

                if(fStart > fMaxTime)
                    warning('DataSet only contains %d Seconds of data (%d Seconds was the requested start time). No waveform will be returned.', fMaxTime, fStart);
                    Waveforms = Waveform.empty;
                    return;
                end

                if(fEnd > fMaxTime)
                    fEnd = fMaxTime;
                    warning('DataSet only contains %d Seconds of data. Returned waveforms will be shorter than requested (%d Seconds).', fMaxTime, fEnd - fStart);
                end

                fNumSamples  = int64((fEnd - fStart) * fSampleFreq);

                % skip past samples that are before the current time range
                fseek(this.FileID, fSkipInitialBytes, 'cof');
            else
                fNumSamples =  int64((fMaxTime) * fSampleFreq);
            end

            % Read the data for the given channel, skipping from one to the next
            fNumChannels = length(this.ChannelArray.Channels);

            fMaxExtents = PlateTypes.GetElectrodeDimensions(this.ChannelArray.PlateType);

            if (isempty(fMaxExtents))
                fMaxExtents = [max([this.ChannelArray.Channels(:).WellRow]), ...
                    max([this.ChannelArray.Channels(:).WellColumn]), ...
                    max([this.ChannelArray.Channels(:).ElectrodeColumn]), ...
                    max([this.ChannelArray.Channels(:).ElectrodeRow])];
            end

            switch aDimensions
                case {LoadArgs.ByPlateDimensions}
                    Waveforms = [];
                case {LoadArgs.ByWellDimensions}
                    Waveforms = cell(double(fMaxExtents(1:2)));
                case {LoadArgs.ByElectrodeDimensions}
                    Waveforms = cell(double(fMaxExtents));
            end

            if length(aChannelsToLoad) == 1
                % We're only reading one channel. For efficiency, take advantage of fread's
                % 'skip' argument.

                fread(this.FileID, aChannelsToLoad - 1, ['1*' fFreadPrecision]);
                fWaveform = fread(this.FileID, fNumSamples / aSubsamplingFactor, ['1*' fFreadPrecision], fSampleSize * ((fNumChannels * aSubsamplingFactor)-1) );
                fChannelMapping = this.ChannelArray.Channels(aChannelsToLoad);

                if(fIsVoltage)
                    fWaveform = VoltageWaveform(fChannelMapping, fStart, fWaveform, this, aSubsamplingFactor);
                elseif(fIsContractility)
                    fWaveform = ContractilityWaveform(fChannelMapping, fStart, fWaveform, this, aSubsamplingFactor);
                else
                    fWaveform = Waveform(fChannelMapping, fStart, fWaveform, this, aSubsamplingFactor);
                end

                fOuputIndex = double([...
                    fChannelMapping.WellRow, ...
                    fChannelMapping.WellColumn, ...
                    fChannelMapping.ElectrodeColumn, ...
                    fChannelMapping.ElectrodeRow]);

                switch aDimensions

                    case {LoadArgs.ByPlateDimensions}
                        Waveforms = fWaveform;

                    case {LoadArgs.ByWellDimensions}
                        Waveforms{fOuputIndex(1),fOuputIndex(2)} = fWaveform;

                    case {LoadArgs.ByElectrodeDimensions}
                        Waveforms{fOuputIndex(1),fOuputIndex(2), fOuputIndex(3),fOuputIndex(4)} = fWaveform;

                end
            else
                fNumSamples      = (fNumSamples/(aSubsamplingFactor)) * fNumChannels;
                fTempChannelData = fread(this.FileID, fNumSamples, [num2str(fNumChannels) '*' fFreadPrecision], ((fSampleSize*(fNumChannels))*(aSubsamplingFactor-1)));

                % This test (which can fail only when we read the the end of the file)
                % makes sure that we didn't get a number of samples that's not divisible
                % by the number of channels.
                fRemainderCount = mod(length(fTempChannelData), fNumChannels);
                if fRemainderCount ~= 0
                    warning('load_AXiS_raw:remainderCheck', ...
                        'This Data has the wrong number of samples for %u channels, File may be corrupt', ...
                        fNumChannels);
                    fNumSamples = int64((length(fTempChannelData)/ fNumChannels) - 1) * fNumChannels;
                    fTempChannelData = fTempChannelData(1:fNumSamples);
                end

                % Convert the 1D array to a 2D array, with channel as the second dimension
                % (starts as first dimension and then is transposed)
                fTempChannelData = reshape(fTempChannelData(:), fNumChannels, []);

                for fChannelIndex = aChannelsToLoad
                    fChannelMapping = this.ChannelArray.Channels(fChannelIndex);
                    fWaveform = fTempChannelData(fChannelIndex,:)';
                    if(fIsVoltage)
                        fWaveform = VoltageWaveform(fChannelMapping, fStart, fWaveform, this, aSubsamplingFactor);
                    elseif(fIsContractility)
                        fWaveform = ContractilityWaveform(fChannelMapping, fStart, fWaveform, this, aSubsamplingFactor);
                    else
                        fWaveform = Waveform(fChannelMapping, fStart, fWaveform, this, aSubsamplingFactor);
                    end

                    fOuputIndex = double([...
                        fChannelMapping.WellRow, ...
                        fChannelMapping.WellColumn, ...
                        fChannelMapping.ElectrodeColumn, ...
                        fChannelMapping.ElectrodeRow]);

                    switch aDimensions
                        case {LoadArgs.ByPlateDimensions}
                            if(isempty(Waveforms))
                                Waveforms = fWaveform;
                            else
                                Waveforms(length(Waveforms) + 1) = fWaveform;
                            end

                        case {LoadArgs.ByWellDimensions}
                            Waveforms{fOuputIndex(1),fOuputIndex(2)}(...
                                length(Waveforms{fOuputIndex(1),fOuputIndex(2)}) + 1) = fWaveform;

                        case {LoadArgs.ByElectrodeDimensions}
                            Waveforms{fOuputIndex(1),fOuputIndex(2), fOuputIndex(3),fOuputIndex(4)} = fWaveform; %We only expect one Waveform per channel

                    end
                end
            end
        end
   end
   methods (Access = protected)
        function propgrp = getPropertyGroups(obj)
            if ~isscalar(obj)
                propgrp = getPropertyGroups@matlab.mixin.CustomDisplay(obj);
            else
                if(~isempty(obj.DataSetNames) && iscell(obj.DataSetNames))
                    propList = struct(...
                        'Name',obj.Name,...
                        'DataSetNames',obj.DataSetNames,...
                        'Description',obj.Description,...
                        'SamplingFrequency', obj.SamplingFrequency,...
                        'Duration', obj.Duration,...
                        'VoltageScale', obj.VoltageScale,...
                        'BlockVectorStartTime', obj.BlockVectorStartTime.ToDateTimeString(), ...
                        'ExperimentStartTime',obj.ExperimentStartTime.ToDateTimeString(),...
                        'AddedDate', obj.AddedDate.ToDateTimeString(),...
                        'ModifiedDate', obj.ModifiedDate.ToDateTimeString());
                elseif(~(isempty(obj.AddedDate) ||  isempty(obj.ModifiedDate)))
                    propList = struct(...
                        'Description',obj.Description,...
                        'SamplingFrequency', obj.SamplingFrequency,...
                        'VoltageScale', obj.VoltageScale,...
                        'BlockVectorStartTime', obj.BlockVectorStartTime.ToDateTimeString(), ...
                        'ExperimentStartTime',obj.ExperimentStartTime.ToDateTimeString(),...
                        'Duration', obj.Duration,...
                        'AddedDate', obj.AddedDate.ToDateTimeString(),...
                        'ModifiedDate', obj.ModifiedDate.ToDateTimeString());
                else
                    propgrp = DataSet(obj).getPropertyGroups();
                    return;
                end
                propgrp = matlab.mixin.util.PropertyGroup(propList);
            end
        end
    end
end