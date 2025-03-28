%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef LoadArgs < handle
    %LOADARGS parser for file loading arguments
    properties (GetAccess = private, Constant = true)
        wellVal = 1;
        electrodeVal = 2;
        timespanVal = 3;
        dimensionsVal = 4;
        expansionVal = 5;

        supportedModifiers = {'SubsamplingFactor'};
    end

    properties (GetAccess = public, Constant = true)
        ByPlateDimensions = 1;
        ByWellDimensions = 3;
        ByElectrodeDimensions = 5;
    end

    properties (GetAccess = public, SetAccess = private)
        Well
        Electrode
        Timespan
        Dimensions
        SubsamplingFactor
    end

    methods (Static)

        function this = LoadArgs(argin)
            % Internal support function for AxisFile Construction
            % loadAxISFileParseArgs Parses arguments for file readers
            %
            %  Legal forms:
            %     LoadArgs();
            %     LoadArgs(well);
            %     LoadArgs(electrode);
            %     LoadArgs(well, electrode);
            %     LoadArgs(timespan);
            %     LoadArgs(well, timespan);
            %     LoadArgs(electrode, timespan);
            %     LoadArgs(well, electrode, timespan);
            %     LoadArgs(dimensions);
            %     LoadArgs(well, dimensions);
            %     LoadArgs(electrode, dimensions);
            %     LoadArgs(well, electrode, dimensions);
            %     LoadArgs(timespan, dimensions);
            %     LoadArgs(well, timespan, dimensions);
            %     LoadArgs(electrode, timespan, dimensions);
            %     LoadArgs(well, electrode, timespan, dimensions);
            %
            %     LoadArgs(~, ~, ~, ~, {commands});
            %
            %
            %  Required arguments:
            %    filename    Pathname of the file to load
            %
            %  Optional arguments:
            %    well        String listing which wells (in a multiwell file) to load.
            %                Format is a comma-delimited string with whitespace ignored, e.g.
            %                'A1, B2,C3' limits the data loaded to wells A1, B2, and C3.
            %                Also acceptable: 'all' to load all wells.
            %                If this parameter is omitted, all wells are loaded.
            %                For a single-well file, this parameter is ignored.
            %
            %    electrode   Which electrodes to load.  Format is either a comma-delimited string
            %                with whitespace ignored (e.g. '11, 22,33') or a single channel number;
            %                that is, a number, not part of a string.
            %                Also acceptable: 'all' to load all channels and 'none', '-1', or -1
            %                to load no data (returns only header information).
            %                If this parameter is omitted, all channels are loaded.
            %
            %    timespan    Span of time, in seconds, over which to load data.  Format is a two-element
            %                array, [t0 t1], where t0 is the start time and t1 is the end time and both
            %                are in seconds after the first sample in the file.  Samples returned are ones
            %                that were taken at time >= t0 and <= t1.  The beginning of the file
            %                is at 0 seconds.
            %                If this parameter is omitted, the data is not filtered based on time.
            %
            %    dimensions  Preferred number of dimensions to report the waveforms in.
            %                Value must be a whole number scalar, and only certain values are allowed:
            %
            %                dimensions = 1 -> ByPlate: returns a vector of Waveform objects, 1 Waveform
            %                        s          per signal in the plate
            %                dimensions = 3 -> ByWell: Cell Array of vectors of waveform 1 Waveform per signal
            %                                  in the electrode with size (well Rows) x (well Columns)
            %                dimensions = 5 -> ByElectrode: Cell Array of vectors of waveform 1 Waveform per .
            %                                  signal in the electrode with size (well Rows) x (well Columns) x
            %                                  (electrode Columns) x (electrode Rows)
            this.Well = [];
            this.Electrode = [];
            this.Timespan = [];
            this.Dimensions = [];
            this.SubsamplingFactor = 1;

            fLastArg = [];

            fNumArgs = length(argin);

            if fNumArgs > 5
                error('LoadArgs:excessArgs', 'Too many arguments specified');
            end

            for i = 1:fNumArgs
                fCurrentArg = argin{i};

                if isempty(fCurrentArg) %ignore empty args
                    continue
                end

                if isempty(fLastArg)
                    fParseAsWell = LoadArgs.canonical_well_electrode_argument(fCurrentArg, LoadArgs.wellVal);
                    if ~isempty(fParseAsWell)
                        % Argument is a well
                        this.Well = fParseAsWell;
                        fLastArg = LoadArgs.wellVal;
                        continue;
                    end
                end

                if isempty(fLastArg) || fLastArg == LoadArgs.wellVal
                    fParseAsElectrode = LoadArgs.canonical_well_electrode_argument(fCurrentArg, LoadArgs.electrodeVal);
                    if ~isempty(fParseAsElectrode)
                        % Argument is an electrode
                        this.Electrode = fParseAsElectrode;
                        fLastArg = LoadArgs.electrodeVal;
                        continue;
                    end
                end

                if isempty(fLastArg) || fLastArg == LoadArgs.wellVal || fLastArg == LoadArgs.electrodeVal
                    fParseAsTimespan = LoadArgs.canonical_timespan_argument(fCurrentArg);
                    if ~isempty(fParseAsTimespan)
                        % Argument is a timespanVal
                        if isnumeric(fParseAsTimespan) && fParseAsTimespan(2) < fParseAsTimespan(1)
                            error('load_AxIS_file_parse_args:invalidTimespan', 'Invalid timespan argument: t1 < t0');
                        end

                        this.Timespan = fParseAsTimespan;
                        fLastArg = LoadArgs.timespanVal;
                        continue;
                    end
                end

                if isempty(fLastArg) || fLastArg == LoadArgs.wellVal || fLastArg == LoadArgs.electrodeVal || fLastArg == LoadArgs.timespanVal
                    if isscalar(fCurrentArg) && isnumeric(fCurrentArg)
                        switch fCurrentArg
                            case { LoadArgs.ByPlateDimensions, ...
                                    LoadArgs.ByWellDimensions, ...
                                    LoadArgs.ByElectrodeDimensions}
                                this.Dimensions = fCurrentArg;
                            otherwise
                                this.Dimensions = [];
                        end
                        fLastArg = LoadArgs.dimensionsVal;
                        continue;
                    end
                end

                if isempty(fLastArg) ||iscell(fCurrentArg)
                    this.ParseExpansionArguments(this, fCurrentArg);
                    fLastArg = LoadArgs.expansionVal;
                    continue;
                end



                % If we get here, the argument couldn't be parsed
                error('load_AxIS_file_parse_args:invalidArg', ['Invalid argument #' num2str(i+1) ' to load_AxIS_file']);
            end

            if isempty(this.Well)
                % Default: all wells
                this.Well = 'all';
            end

            if isempty(this.Electrode)
                % Default: all electrodes
                this.Electrode = 'all';
            end

            if isempty(this.Timespan)
                % Default: all time
                this.Timespan = 'all';
            end

        end

    end

    methods(Static, Access = private)

        function aParseOutput = canonical_well_electrode_argument(aArgument, type)

            DELIMITER = ',';
            aParseOutput = [];

            % Error-check argument type
            if isa(aArgument, 'LoadArgs') && ~(LoadArgs.wellVal || LoadArgs.electrodeVal)
                error('canonical_well_electrode_argument:invalidArgType', 'Internal error: Invalid argument type for parsing');
            end

            % Special cases
            if strcmpi(aArgument, 'all')
                aParseOutput = 'all';
            elseif type == LoadArgs.electrodeVal && isscalar(aArgument) && aArgument == -1
                aParseOutput = 'none';
            elseif type == LoadArgs.electrodeVal && isscalar(aArgument) && isnumeric(aArgument) && aArgument > 10
                aParseOutput = [floor(aArgument/10) mod(aArgument, 10) ];
            elseif ischar(aArgument)

                if type == LoadArgs.electrodeVal && ( strcmp(strtrim(aArgument), '-1') || strcmpi(aArgument, 'none') )
                    aParseOutput = 'none';
                    return;
                end


                % Convert well names to upper case
                fCanonicalArg = upper(aArgument);

                % Strip whitespace
                fCanonicalArg(isspace(fCanonicalArg)) = [];

                % Is it valid?
                while ~isempty(fCanonicalArg)
                    if   length(fCanonicalArg) >= 2 &&  ...
                            ( (type == LoadArgs.wellVal)      && isletter(fCanonicalArg(1))    && LoadArgs.isdigit_ax(fCanonicalArg(2))) || ...
                            ( (type == LoadArgs.electrodeVal) && LoadArgs.isdigit_ax(fCanonicalArg(1))  && LoadArgs.isdigit_ax(fCanonicalArg(2)))

                        % Valid format
                        if type == LoadArgs.wellVal
                            % Format is Letter then Number, where letter is the row and number is the column
                            % Build array of column, row
                            [nextWell, fCanonicalArg] = strtok(fCanonicalArg, ',');
                            aParseOutput = [ aParseOutput ; ...
                                str2num(nextWell(2:end)) (char(nextWell(1)) - char('A') + 1)];
                        else
                            % Format is Number then Number, where the first is the column and the second is the row
                            % Build array of column, row
                            [nextWell, fCanonicalArg] = strtok(fCanonicalArg, ',');
                            aParseOutput = [ aParseOutput ; ...
                                str2num(nextWell(1)) str2num(nextWell(2:end))];
                        end

                        % Look for the next delimiter
                        if length(fCanonicalArg) >= 1
                            if fCanonicalArg(1) == DELIMITER
                                fCanonicalArg = fCanonicalArg(2:end);
                            else
                                % Invalid next character - not a delimiter
                                aParseOutput = [];
                                break;
                            end
                        end
                    else
                        % Invalid Well ID
                        aParseOutput = [];
                        break;
                    end
                end
            end
        end

        function ParseExpansionArguments(aLoadArgsParent, aExpansionCommands)
            %Define supported 'expanded' load commands here.

            for i = 1:length(LoadArgs.supportedModifiers)
                supportedMod = cellfun(@(x) any(strcmpi(x, LoadArgs.supportedModifiers{i})), aExpansionCommands);

                if any(supportedMod)
                    eval([ 'aLoadArgsParent.', LoadArgs.supportedModifiers{i}, ' = ', num2str(aExpansionCommands{supportedMod}{2}), ';']);
                end
            end
        end

        function aParseOutput = canonical_timespan_argument(aArgument)

            if isvector(aArgument) && length(aArgument) == 2 && isnumeric(aArgument)
                aParseOutput = aArgument(:);
            else
                aParseOutput = [];
            end

        end

        function t = isdigit_ax(c)
            %ISDIGIT True for decimal digits.
            %
            %   For a string C, ISDIGIT(C) is 1 for decimal digits and 0 otherwise.
            %
            narginchk(1, 1);

            t = ischar(c) & ( '0' <= c ) & ( c <= '9' );
        end

    end
end

