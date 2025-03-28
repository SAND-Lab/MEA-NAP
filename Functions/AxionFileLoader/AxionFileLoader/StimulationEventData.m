%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef StimulationEventData
    %STIMULATIONTAGBLOCK Structure that contains the data describing a
    %marked, stimulation portion of a file

    properties(SetAccess = private)
        %ID: Number that StimulationEvent tags attach to
        ID;
        %StimDuration: Length of time (in seconds) that ths stimulation
        %portion of this block lasted
        StimDuration;
        %ArtifactEliminationDuration: Length of time (in seconds) that this
        %Artifact Elimination portion of this block lasted
        ArtifactEliminationDuration;
        %ChannelArrayIdList Channel array IDs that were used in this block
        ChannelArrayIdList;
        %Textual description of this Tag block
        Description;
    end

    methods
        function this = StimulationEventData(...
                aId, aStimDuration, aArtElimDuration,...
                aChannelArrayIdList, aDescription)
            this.ID = aId;
            this.StimDuration = aStimDuration;
            this.ArtifactEliminationDuration = aArtElimDuration;
            this.ChannelArrayIdList = aChannelArrayIdList;
            this.Description = aDescription;
        end
    end

end

