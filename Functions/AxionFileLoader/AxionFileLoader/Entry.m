%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef(Abstract = true) Entry < handle

    %ENTRY base class for all Axion file entries
    %
    %   EntryRecord: Record that indicated this recod in the file.
    %
    %   Start:       Location (# of bytes from start of file) of this
    %                entryss

    properties (GetAccess = private, SetAccess = private)
        indiciesForChannels
        indiciesForElectrodes
    end

    properties (GetAccess = public, SetAccess = private)
        EntryRecord
        Start
    end

    methods (Access = protected)
        function this = Entry(varargin)
            % Entry: Construct a new instance of Entry.
            %s
            % Valid aruments:
            %
            % Entry()           Consructs an entry that is not tied to a
            %                   location in a file.
            %
            % Entry(aEntryRecord, aStart) Constructs a new Entry where:
            %
            %   aEntryRecord:   An EntryRecord that specifies the type and
            %                   the length of the entry in the file
            %
            %   aStart:         An int64 specifiying the number of bytes
            %                   from the beginning of the file where the
            %                   entry starts in the file.
            %

            fNumArgs = length(varargin);

            if fNumArgs == 0
                % Handle the no-argument case
                return
            elseif  fNumArgs == 2
                aEntryRecord = varargin{1};
                aStart = varargin{2};
            else
                error('Entry: Argument Error')
            end

            if(~isa(aEntryRecord, 'EntryRecord'))
                error('Entry: Unexpected Type')
            end

            if(~isa(aStart, 'int64'))
                error('Entry: Unexpected Type')
            end
            this.EntryRecord = aEntryRecord;
            this.Start = aStart;
        end
    end

end

