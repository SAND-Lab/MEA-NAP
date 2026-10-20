classdef McsFrameStream < McsHDF5.McsStream
% Holds the contents of a FrameStream
%
% Contains one or more FrameDataEntity in a cell array. The other fields
% and the Info field provide general information about the frame stream.
%
% (c) 2016 by Multi Channel Systems MCS GmbH
    
    properties (SetAccess = private)
        FrameDataEntity = {} % (cell array) McsFrameDataEntity objects
    end
    
    methods
        
        function str = McsFrameStream(filename, strStruct, source, cfg)
        % Constructs a McsFrameStream object. 
        %
        % function str = McsFrameStream(filename, strStruct, cfg)
        %
        % Calls the constructors for the individual McsFrameDataEntity
        % objects. The FrameData from the individual FrameDataEntity is
        % not read directly from the file, but only once the FrameData
        % field is actually accessed.
            
            metaName = 'Frame';
            if strcmp(source, 'CMOS-MEA')
                metaName = 'Sensor';
            end
            str = str@McsHDF5.McsStream(filename,strStruct,metaName,source);
            
            if strcmp(source, 'DataManager')
                str = ConstructFromDataManager(filename, str, strStruct, cfg);
            elseif strcmp(source, 'CMOS-MEA')
                str = ConstructFromCMOSMea(filename, str, strStruct, cfg);
            end
                
        end
    end
    
    methods (Access = private)
        function str = ConstructFromDataManager(filename, str, strStruct, cfg)
            % check if entities are present
            if ~isempty(strStruct.Groups)
                str.FrameDataEntity = cell(1,length(strStruct.Groups));
                for gidx = 1:length(strStruct.Groups)
                    info = structfun(@(x)(x(gidx)),str.Info,'UniformOutput',false);
                    fullName = [strStruct.Groups(gidx).Name '/' 'FrameData'];
                    str.FrameDataEntity{gidx} = McsHDF5.McsFrameDataEntity(filename,info,strStruct.Groups(gidx), fullName, 'DataManager', cfg);
                end
            end 
        end
        
        function str = ConstructFromCMOSMea(filename, str, strStruct, cfg)
            if exist('h5info')
                mode = 'h5';
            else
                mode = 'hdf5';
            end
            
            % check if entities are present
            if ~isempty(strStruct.Datasets)
                frameTypeID = '49da47df-f397-4121-b5da-35317a93e705';
                for didx = 1:length(strStruct.Datasets)
                    typeID = McsHDF5.McsH5Helper.GetFromAttributes(strStruct.Datasets(didx), 'ID.TypeID', mode);
                    if strcmp(typeID, frameTypeID)
                        regionID = McsHDF5.McsH5Helper.GetFromAttributes(strStruct.Datasets(didx), 'RegionID', mode);
                        infoIdx = str.Info.RegionID == regionID;
                        info = structfun(@(x)(McsHDF5.McsFrameStream.GetFromInfo(x, infoIdx)),str.Info,'UniformOutput',false);
                        if strcmp(mode, 'h5')
                            fullName = [strStruct.Name '/' strStruct.Datasets(didx).Name];
                        else
                            fullName = strStruct.Datasets(didx).Name;
                        end
                        entity = McsHDF5.McsFrameDataEntity(filename,info,strStruct.Datasets(didx), fullName, 'CMOS-MEA', cfg);
                        str.FrameDataEntity = [str.FrameDataEntity {entity}];
                    end
                end
            end
            str.Label = McsHDF5.McsH5Helper.GetFromAttributes(strStruct, 'ID.Instance', mode);
            str.DataSubType = 'Frame';
            str.StreamType = 'Frame';
        end
    end
    
    methods (Static, Access = private)
        function infoOut = GetFromInfo(infoIn, infoIdx)
            if ischar(infoIn) || isscalar(infoIn)
                infoOut = infoIn;
            elseif iscell(infoIn)
                infoOut = infoIn{infoIdx};
            else
                infoOut = infoOn(infoIdx);
            end
        end
    end
end