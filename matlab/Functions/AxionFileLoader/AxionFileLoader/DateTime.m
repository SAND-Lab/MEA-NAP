%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef DateTime < matlab.mixin.CustomDisplay

    properties (GetAccess = public, Constant = true)
        Size = 14;
    end
    %DATETIME class representation of a date and time.
    properties (GetAccess = public, SetAccess = private)
        Year
        Month
        Day
        Hour
        Minute
        Second
        Millisecond
    end

    methods(Access = public)

        function this = DateTime(aFileID)
            %DateTime: Loads a DateTime from a file, assuming the read stream is
            %pointed at the correct location.
            this.Year        = fread(aFileID, 1, 'uint16=>double');
            this.Month       = fread(aFileID, 1, 'uint16=>double');
            this.Day         = fread(aFileID, 1, 'uint16=>double');
            this.Hour        = fread(aFileID, 1, 'uint16=>double');
            this.Minute      = fread(aFileID, 1, 'uint16=>double');
            this.Second      = fread(aFileID, 1, 'uint16=>double');
            this.Millisecond = fread(aFileID, 1, 'uint16=>double');
        end

        function datevector = ToDateTimeVect(this)
            %returns a six element date vector containing the represented time
            % and date in decimal form.
            % See also: clock, datevec, datenum, now
            fSeconds = this.Second + (this.Millisecond * 1e-3);
            datevector = double([this.Year this.Month this.Day this.Hour this.Minute fSeconds]);
        end

        function  datenumber = ToDateTimeNumber(this)
            % returns the represented date and time as a serial date
            %  number.
            % See also: clock, datevec, datenum, now
            datenumber = datenum(this.ToDateTimeVect());
        end

        function matlabdatetime = ToMatlabDateTime(this)
            matlabdatetime = datetime( ...
                this.Year, ...
                this.Month, ...
                this.Day, ...
                this.Hour, ...
                this.Minute, ...
                this.Second, ...
                this.Millisecond);
        end

        function  datestring = ToDateTimeString(this)
            % returns the represented date and time as a serial date
            %  number.
            % See also: clock, datevec, datenum, now
            datestring = datestr(this.ToDateTimeNumber(), 'yyyy-mm-dd HH:MM:SS.FFF');
        end
    end
    methods(Access = protected)
        function displayScalarObject(obj)
            disp(obj.ToDateTimeString());
        end
    end

end

