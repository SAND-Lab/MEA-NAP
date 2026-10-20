%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef BlockVectorSet < handle
    %BLOCKVECTORSET is a grouping of data and metadata for a series of data contained within an AxisFile.
    %   this class is composed of 4 major parts:
    %
    %   ChannelArray:        The channel array (See ChannelArray.m) is a listing of
    %                        all of the channels that were recorded in this
    %                        loaded set.
    %
    %   Header:              The header of the data (See BlockVectorHeader.m) contains the basic infomation
    %                        that is used in loading and using the data in this
    %                        set (e.g. Sampling Frequency, Voltage Scale, etc...)
    %
    %   HeaderExtension:     The header extension (See BlockVectorHeaderExtension.m)
    %                        contains metadata about the data capture / Reprocessing.
    %
    %   Data:                The data in this file (See BlockVectorData.m)
    %                        contains the methods for loading the sample data
    %                        from this set.
    %

    properties (SetAccess = private, GetAccess = private)
        mSourceFile
    end

    properties(GetAccess = public, SetAccess = private)
        ChannelArray
        Header
        HeaderExtension
        Data
        CombinedBlockVector
    end

    methods

        function this = BlockVectorSet(varargin)
            this.SetValue(varargin{:});
        end


        function SetValue(this, varargin)
            for i = 1:length(varargin)

                arg = varargin{i};

                if(isa(arg,'ChannelArray'))
                    this.ChannelArray = arg;
                elseif(isa(arg,'BlockVectorHeader'))
                    this.Header = arg;
                elseif(isa(arg,'BlockVectorHeaderExtension'))
                    this.HeaderExtension = arg;
                elseif(isa(arg,'BlockVectorData'))
                    this.Data = arg;
                elseif(isa(arg,'AxisFile'))
                    this.mSourceFile = arg;
                elseif(isa(arg,'CombinedBlockVectorHeaderEntry'))
                    this.CombinedBlockVector = arg;
                    % HACK: Provide access to the CombinedBlockVector
                    % properties through Header and HeaderExtension to
                    % support old code.
                    this.Header = arg;
                    this.HeaderExtension = arg;
                else
                    error('Unknown member type');
                end

            end
        end

        function handle = SourceFile(this)
            handle = this.mSourceFile;
        end
    end
end

