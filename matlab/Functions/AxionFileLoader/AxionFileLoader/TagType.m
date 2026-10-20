%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef TagType < uint16
    %TAGTYPE Enumeration of the types of tags that are known.

    enumeration
        %Deleted: Tag revision where this TagGUID has been deleted
        %remarks: This is a special case, Tags may alternate between this
        %         type and their own as the are deleted / undeleted
        Deleted(uint16(0)),

        % WellTreatment:  Describes the treatment state of a well in a file
        WellTreatment(uint16(1)),

        %UserAnnotation: Time based note added to the file by the user
        UserAnnotation(uint16(2)),

        %SystemAnnotation: Time based note added to the file by Axis
        SystemAnnotation(uint16(3)),

        %DataLossEvent: Tag that records any loss of data in the system that affects this
        %               recorded file.
        %Remarks:       Coming soon, Currently Unused!
        DataLossEvent(uint16(4)),

        %StimulationEvent: Tag that describes a stimulation that was applied to the plate
        %                   during recording
        StimulationEvent(uint16(5)),

        %StimulationChannelGroup: Tag that lists the channels that were loaded for stimulation for a StimulationEvent
        %                         Many StimulationEvent tags may reference the same StimulationChannelGroup
        StimulationChannelGroup (uint16(6)),

        %StimulationWaveform: Tag that lists the stimulation that was applied for stimulation for a StimulationEvent
        %                     Many StimulationEvent tags may reference the same StimulationWaveform
        StimulationWaveform (uint16(7)),

        %CalibrationTag: Tag that is used for axis's internal calibration
        %                of noise mesurements (Use is currently not
        %                supported in matlab)
        CalibrationTag(uint16(8)),

        %StimulationLedGroup: Tag that lists the LEDs that were loaded for stimulation for a StimulationEvent
        %                     Many StimulationEvent tags may reference the same StimulationLedGroup
        StimulationLedGroup (uint16(9)),

        %DoseEvent: (Unsupported in in this library)
        DoseEvent (uint16(10)),

        %StringDictonaryKeyPair: (Unsupported in in this library)
        StringDictonaryKeyPair (uint16(11)),

        %LeapInductionEvent: Tag marking a LEAP induction event for a plate/recording
        LeapInductionEvent (uint16(12)),

        %ViabilityImpedanceEvent: Tag for acquiring viability data
        ViabilityImpedanceEvent (uint16(13)),
    end

end

