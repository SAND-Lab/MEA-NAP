%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef WellInformation < Tag
    %WELLINFORMATION Class that describes the platemap data for a single well
    properties(GetAccess = public, SetAccess = private)

        % location bytes that are currently irrelevant
        WellColumn;
        WellRow;

        % IsOn: Active state of the well
        IsOn;
        % IsControl: True if this well was intended to be a control
        IsControl;

        %0 - 255 RGB values for the displayed color
        Red;
        Green;
        Blue;

        % Unbounded treatment identification string for a well's treatment
        TreatmentWhat;

        % Unbounded string for additional comments from the user about the well treatment
        AdditionalInformation;

        % Number of the "how much", normalized to the TreatmentHowMuchBaseUnit
        TreatmentHowMuchBaseValue;

        % Numeric representation of the exponent applied by an SI unit prefix
        % e.g. in "30 uM", TreatmentHowMuchUnitExponent = 6 because 1e6 is used to
        % normalizes the stored 30e-6 in TreatmentHowMuchBaseValue to 30.
        TreatmentHowMuchUnitExponent;


        % String contains the user entered base unit e.g. the 'M' in "nM"
        % or the "Hz" in "kHz"
        TreatmentHowMuchBaseUnit;

    end

    methods
        function this = WellInformation(aFileID, aRawTag)
            this = this@Tag(aRawTag.TagGuid);

            %Move to the correct location in the file
            fStart = aRawTag.Start + TagEntry.BaseSize;
            fEnd = aRawTag.Start + aRawTag.EntryRecord.Length;

            fSeekResult = fseek(aFileID, fStart, 'bof');

            if(fSeekResult == 0)
                this.WellColumn = fread(aFileID, 1, 'uint8=>uint8');
                this.WellRow = fread(aFileID, 1, 'uint8=>uint8');
                fElectrodeColumn = fread(aFileID, 1, 'uint8=>uint8');
                fElectrodeRow = fread(aFileID, 1, 'uint8=>uint8');

                %Verify well coordinates
                if this.WellColumn == 0 || this.WellRow == 0
                    error('WellInformationTag %s contains invalid data', aRawTag.TagGuid);
                end

                %Electrode position should alweays be broadcast to well
                %here
                if fElectrodeColumn ~= 0 ||  fElectrodeRow ~= 0
                    warning('File may be corrupt');
                end

                fWellType = fread(aFileID, 1, 'uint8=>uint8');
                if bitand(fWellType, 1) ~= 0
                    this.IsOn = true;
                else
                    this.IsOn = false;
                end

                if bitand(fWellType, 2) ~= 0
                    this.IsControl = true;
                else
                    this.IsControl = false;
                end

                fBytesRemaining = fEnd - ftell(aFileID);

                %We should have at least 12 bytes remaining: 3 for RGB, at
                %least 8 for empty strings, and 1 for TreatmentHowMuchUnitExponent
                if fBytesRemaining >= 12

                    this.Red = fread(aFileID, 1, 'uint8=>uint8');
                    this.Green = fread(aFileID, 1, 'uint8=>uint8');
                    this.Blue = fread(aFileID, 1, 'uint8=>uint8');

                    %User Treatment Data
                    this.TreatmentWhat = freadstring(aFileID);
                    this.AdditionalInformation = freadstring(aFileID);

                    fBytesRemaining = fEnd - ftell(aFileID);

                    % Make sure we have at least 13 bytes remaining - 8 for
                    % TreatmentHowMuchBaseValue, 1 for exponent, 4 for
                    % empty string
                    if fBytesRemaining > 9
                        this.TreatmentHowMuchBaseValue = fread(aFileID, 1, 'double=>double');
                        this.TreatmentHowMuchUnitExponent = fread(aFileID, 1, 'int8=>int8');
                        this.TreatmentHowMuchBaseUnit = freadstring(aFileID);
                    else
                        warning('Tag %s is missing treatment amount', aRawTag.TagGuid)
                    end
                else
                    warning('Tag %s is an old-style tag - no treatment data', aRawTag.TagGuid);
                end

                if ftell(aFileID) >  (fStart + aRawTag.EntryRecord.Length)
                    warning('File may be corrupt');
                end
            else
                 error('Encountered an error while loading StimulationChannels %s', aRawTag.TagGuid);
            end
        end
    end
end

