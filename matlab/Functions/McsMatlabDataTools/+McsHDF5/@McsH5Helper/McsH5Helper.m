classdef McsH5Helper
% A selection of useful helper methods for dealing with HDF5 files
%
% (c) 2017 by Multi Channel Systems MCS GmbH
    methods (Static)
        function equal = AttributeNameEquals(attribute, str, mode)
        % Checks if the name of an attributes equals a given string
        %
        % function equal = AttributeNameEquals(attribute, str, mode)
        %
        % Input:
        %   attribute       -   (struct) A hdf5 attribute
        %   str             -   (string) The expected name of the attribute
        %   mode            -   (string) The hdf5 reading mode, can be
        %                       either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                       the old hdf5read interface is used. In
        %                       mode 'h5' the new h5read interface is used.
        %                       Use 'h5' for Matlab versions R2011a and
        %                       newer
        %
        % Output:
        %   equal           -   (bool) True, if the attribute name matches
        %                       str
        %
            equal = false;
            if strcmp(mode, 'hdf5')
                name = regexp(attribute.Name,'/[\.\w]+$','match');
                name = name{length(name)}(2:end);
                equal = strcmp(name, str);
            elseif strcmp(mode, 'h5')
                equal = strcmp(attribute.Name, str);
            end
        end
        
        function value = AttributeValue(attribute, mode)
        % Extracts the value of an attribute
        %
        % function value = AttributeValue(attribute, mode)
        %
        % Input:
        %   attribute       -   (struct) A hdf5 attribute
        %   mode            -   (string) The hdf5 reading mode, can be
        %                       either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                       the old hdf5read interface is used. In
        %                       mode 'h5' the new h5read interface is used.
        %                       Use 'h5' for Matlab versions R2011a and
        %                       newer
        %
        % Output:
        %   value           -   The attribute value
        %
            if strcmp(mode, 'hdf5')
                if isa(attribute.Value, 'hdf5.h5string')
                    value = attribute.Value.Data;
                else
                    value = attribute.Value;
                end
            elseif strcmp(mode, 'h5')
                if ischar(attribute.Value) && ~isempty(attribute.Value) > 0 && double(attribute.Value(end)) == 0
                    attribute.Value = attribute.Value(1:end-1);
                end
                value = attribute.Value;
            end
        end
        
        function isValid = AttributeIsValid(attribute, fun, mode)
        % Checks if the value of an attribute conforms to a prediccate
        %
        % function isValid = AttributeIsValid(attribute, fun, mode)
        %
        % Input:
        %   attribute       -   (struct) A hdf5 attribute
        %   fun             -   An anonymous function that takes the
        %                       attribute value as input and outputs a
        %                       boolean value
        %   mode            -   (string) The hdf5 reading mode, can be
        %                       either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                       the old hdf5read interface is used. In
        %                       mode 'h5' the new h5read interface is used.
        %                       Use 'h5' for Matlab versions R2011a and
        %                       newer
        %
        % Output:
        %   isValid         -   (bool) The return value of fun for the
        %                       attribute value
        %
            value = McsHDF5.McsH5Helper.AttributeValue(attribute, mode);
            isValid = fun(value);
        end
        
        function value = GetFromAttributes(obj, str, mode)
        % Searches for a specific attribute among all attributes of an hdf5
        % object and returns its value.
        %
        % function value = GetFromAttributes(obj, str, mode)
        %
        % Input:
        %   obj         -   (struct) A hdf5 object with field Attributes
        %   str         -   (string) The name of an attribute of this
        %                   object
        %   mode        -   (string) The hdf5 reading mode, can be
        %                   either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                   the old hdf5read interface is used. In
        %                   mode 'h5' the new h5read interface is used.
        %                   Use 'h5' for Matlab versions R2011a and
        %                   newer
        %
        % Output:
        %   value       -   The attribute value
        %
            for aidx = 1:length(obj.Attributes)
                if McsHDF5.McsH5Helper.AttributeNameEquals(obj.Attributes(aidx), str, mode)
                    value = McsHDF5.McsH5Helper.AttributeValue(obj.Attributes(aidx), mode);
                    return
                end
            end
            
            value = [];
        end
        
        function name = MakeName(input)
        % Constructs a valid field name for a struct from an input string
        %
        % function name = MakeName(input)
        %
        % Input:
        %   input       -   (string) A (tentative) field name for a struct.
        %                   This might be the full path to a hdf5 object or
        %                   it might contain dots, spaces or other
        %                   characters that are not valid in struct names.
        %                   All of them are stripped from the name
        %
        % Output:
        %   name        -   (string) A valid struct fieldname
        %
            idx = strfind(input, '/');
            if ~isempty(idx) % if it's the full path of a group, we only want the last part of the path
                input = input(idx(end):end);
            end
            toReplace = {' ','/','.','0x2E'};
            name = input;
            for ti = 1:length(toReplace)
                name = strrep(name, toReplace{ti},'');
            end
        end
        
        function [name, value] = AttributeNameValueForStruct(attribute, mode)
        % Extracts the name and the value from a hdf5 attribute. Invalid
        % characters are removed from the name so that it can be used as a
        % fieldname in a struct.
        %
        % function [name, value] = AttributeNameValueForStruct(attribute, mode)
        %
        % Input:
        %   attribute       -   (struct) a hdf5 attribute
        %   mode            -   (string) The hdf5 reading mode, can be
        %                       either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                       the old hdf5read interface is used. In
        %                       mode 'h5' the new h5read interface is used.
        %                       Use 'h5' for Matlab versions R2011a and
        %                       newer
        %
        % Output:
        %   name            -   (string) The attribute name. If the
        %                       attribute name contained characters not
        %                       valid for field names, they are removed
        %   value           -   The attribute value
        %
            if strcmp(mode, 'h5')
                name = attribute.Name;
            else
                name = strrep(attribute.Name, '.','');
                str = regexp(name,'/\w+$','match');
                name = str{length(str)}(2:end);
            end
            name = McsHDF5.McsH5Helper.MakeName(name);
            value = McsHDF5.McsH5Helper.AttributeValue(attribute, mode);
        end
        
        function data = ReadCompoundDataset(filename, datasetname, mode)
        % Reads a compound dataset from a file.
        %
        % function data = ReadCompoundDataset(filename, datasetname, mode)
        %
        % Input:
        %   filename        -   (string) The HDF5 file name
        %   datasetname     -   (string) The full path to the dataset in
        %                       the file
        %   mode            -   (string) The hdf5 reading mode, can be
        %                       either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                       the old hdf5read interface is used. In
        %                       mode 'h5' the new h5read interface is used.
        %                       Use 'h5' for Matlab versions R2011a and
        %                       newer
        %
        % Output:
        %   data            -   (struct) The compound data set as a struct
            if strcmp(mode,'h5')
                data = h5read(filename, datasetname);
            else
                fid = H5F.open(filename,'H5F_ACC_RDONLY','H5P_DEFAULT');
                did = H5D.open(fid, datasetname);
                data = H5D.read(did,'H5ML_DEFAULT','H5S_ALL','H5S_ALL','H5P_DEFAULT');
                H5D.close(did);
                H5F.close(fid);
            end
        end
        
        function info = ReadInfoFromAttributes(strStruct, mode)
        % Reads all attributes of a HDF5 structure into a single structure
        %
        % function info = ReadInfoFromAttributes(strStruct, mode)
        %
        % Input:
        %   strStruct       -   (struct) The HDF5 structure generated by
        %                       the h5info command
        %   mode            -   (string) The hdf5 reading mode, can be
        %                       either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                       the old hdf5read interface is used. In
        %                       mode 'h5' the new h5read interface is used.
        %                       Use 'h5' for Matlab versions R2011a and
        %                       newer
        %
        % Output:
        %   info            -   (struct) A structure containing all
        %                       attributes of the structure. The attribute
        %                       name is converted to a valid fieldname for
        %                       a struct.
            info = [];
            for ai = 1:length(strStruct.Attributes)
                [name, value] = McsHDF5.McsH5Helper.AttributeNameValueForStruct(strStruct.Attributes(ai), mode);
                info.(name) = value;
            end
        end
        
        function set = ReadDatasetsToStruct(filename, strStruct, mode, types)
        % Reads all datasets that have a specific type to a struct.
        %
        % function set = ReadDatasetsToStruct(filename, strStruct, mode, types)
        %
        % Input:
        %   filename        -   (string) The HDF5 file name
        %   strStruct       -   (struct) The HDF5 structure generated
        %                       by the h5info command
        %   mode            -   (string) The hdf5 reading mode, can be
        %                       either 'hdf5' or 'h5'. If 'hdf5' is set,
        %                       the old hdf5read interface is used. In
        %                       mode 'h5' the new h5read interface is used.
        %                       Use 'h5' for Matlab versions R2011a and
        %                       newer
        %   types           -   (cell array) Array of GUID type strings.
        %                       All datasets that match (with their
        %                       ID.TypeID attribute) one of the type
        %                       strings in this array are read and added as
        %                       a field to the structure. The field name is
        %                       the name of the dataset, converted, if
        %                       necessary, to a valid struct field name.
        %
        % Output:
        %   set             -   (struct) A struct with all datasets that
        %                       have a type matching one of the entries in
        %                       'types'
            set = [];
            for di = 1:length(strStruct.Datasets)
                type = McsHDF5.McsH5Helper.GetFromAttributes(strStruct.Datasets(di), 'ID.TypeID', mode);
                if ~any(strcmpi(types, type))
                    continue;
                end
                name = McsHDF5.McsH5Helper.GetFromAttributes(strStruct.Datasets(di), 'ID.Instance', mode);
                setName = McsHDF5.McsH5Helper.MakeName(name);
                inf = McsHDF5.McsH5Helper.ReadCompoundDataset(filename, [strStruct.Name '/' strStruct.Datasets(di).Name], mode);
                
                fn = fieldnames(inf);
                for fni = 1:length(fn)
                    fname = strrep(fn{fni}, '0x2E', '');
                    set.(setName).(fname) = inf.(fn{fni});
                    if verLessThan('matlab','7.11') && strcmp(class(inf.(fn{fni})),'int64')
                        str.(setName).(fname) = double(str.(setName).(fname));
                    end
                end
            end
        end
    end
end