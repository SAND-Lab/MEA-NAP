classdef FakeApp < handle
    % Headless stand-in for the MEA-NAP GUI app object, used only by
    % MEApipeline_parity.m so the pipeline's guiMode==1 status-text lines
    % have somewhere to write when running under `matlab -batch`.
    % Purely a sink for status strings — touches no analysis parameter.
    properties
        MEANAPStatusTextArea = struct('Value', {{}});
        ViewOutputsButton = struct('Value', 0);
    end
end
