classdef McsStream < handle
% Superclass for the different streams.
%
% Reads and stores the Info struct and the other data attributes.
    
    properties (SetAccess = protected)
        StreamInfoVersion   % (scalar) Version of the stream protocol
        StreamGUID          % (string) The stream GUID
        StreamType          % (string) The stream type (Analog, Event,...)
        SourceStreamGUID    % (string) The GUID of the source stream
        Label               % (string) The stream label
        DataSubType         % (string) The type of data (Electrode, Auxiliary,...)
        
        % Info - (struct) Information about the stream
        % The fields depend on the stream type and hold information about
        % each channel/entity in the stream, such as their IDs, labels,
        % etc.
        Info                
    end
    
    properties (Access = protected)
        FileName            
        StructName          
        DataLoaded = false;
        Internal = false;
        SourceType
    end
    
    methods
        
        function str = McsStream(filename, strStruct, type, sourceType)
        % Reads the Info attributes and the stream attributes.
        %
        % function str = McsStream(filename, strStruct, type)
        % 
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            str.StructName = strStruct.Name;
            str.FileName = filename;
            str.SourceType = sourceType;
            if strcmp(sourceType, 'DataManager')
                infoName = ['/Info' type];
            elseif strcmp(sourceType, 'CMOS-MEA')
                infoName = ['/' type 'Meta'];
            end
            
            inf = McsHDF5.McsH5Helper.ReadCompoundDataset(filename, [strStruct.Name infoName], mode);
            fn = fieldnames(inf);
            for fni = 1:length(fn)
                fname = strrep(fn{fni}, '0x2E', '');
                str.Info(1).(fname) = inf.(fn{fni});
                if verLessThan('matlab','7.11') && strcmp(class(inf.(fn{fni})),'int64')
                    str.Info(1).(fname) = double(str.Info(1).(fname));
                end
            end
            
            if isfield(strStruct,'Attributes')
                dataAttributes = strStruct.Attributes;
                m = metaclass(str); % need to check whether the attribute is part of the class Properties
                if isfield(m, 'PropertyList')
                    propNames = {m.PropertyList.Name};
                else
                    propNames = cellfun(@(x)(x.Name), m.Properties, 'UniformOutput', false);
                end
                for fni = 1:length(dataAttributes)
                    [name, value] = McsHDF5.McsH5Helper.AttributeNameValueForStruct(dataAttributes(fni), mode);
                    if any(arrayfun(@(x)(strcmp(x, name)), propNames))
                        str.(name) = value;
                    else
                        str.Info.(name) = value;
                    end
                end
            end
            
        end
        
        function Fs = getSamplingRate(str,varargin)
        % Returns the sampling rate in Hz
        %    
        % function Fs = getSamplingRate(str)
        %
        % Warning: Will not work for event channels!
        %
        % function Fs = getSamplingRate(str,i)
        %
        % Returns the sampling rate in Hz of channel i of a
        % McsStream.
        
            if isempty(varargin)
                Fs = 1 ./ double(str.Info.Tick(1)) * 1e6;
            else
                Fs = 1 / double(str.Info.Tick(varargin{1})) * 1e6;
            end
        end
        
    end
    
    methods (Access = protected)
        function copyFields(to, from, index)
            to.StreamInfoVersion = from.StreamInfoVersion;
            to.StreamGUID = from.StreamGUID;
            to.StreamType = from.StreamType;
            to.SourceStreamGUID = from.SourceStreamGUID;
            to.Label = from.Label;
            to.DataSubType = from.DataSubType;
            fns = fieldnames(to.Info);
            for fni = 1:length(fns)
                info = from.Info.(fns{fni});
                to.Info.(fns{fni}) = info(index);
            end
        end
    end
    
    methods (Static)
        function cfg = checkStreamParameter(varargin)
            if isempty(varargin)
                cfg = [];
            else
                cfg = varargin{1};
            end
            cfg = McsHDF5.checkParameter(cfg, 'dataType', 'double');
            cfg = McsHDF5.checkParameter(cfg, 'timeStampDataType', 'int64');
            if verLessThan('matlab','7.11')
                cfg.timeStampDataType = 'double';
            end
        end
    end
end