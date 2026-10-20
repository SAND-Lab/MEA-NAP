function varargout = axionStimEventsTool(action, varargin)
%AXIONSTIMEVENTSTOOL Shared logic for the 'axionStimEvents' stim detection method.
%
% Stimulation times are read straight from the Axion file's StimulationEvents
% (never from the voltage trace). A CSV with columns
%   (1) raw file name, (2) well, (3) stimulated electrode (channel id col*10+row)
% decides which electrode carries those times in each well. The CSV is chosen
% on the General tab of the GUI (Params.axionStimCSV); the .raw files are looked
% for next to that CSV and in the MEA data folder. The same CSV/Params drive
% both the batch pipeline and the interactive stim detection app.
%
% Actions:
%   axionStimEventsTool('selectCSV', editFieldHandle, app)
%       File-picker callback for the 'Stim .raw CSV' button; writes the chosen
%       path into the edit field.
%   stimInfo = axionStimEventsTool('build', recName, channelNames, coords, Params, app)
%       Build stimInfo (one struct per channel) for one recording / well using
%       Params.axionStimCSV.
%   axionStimEventsTool('warnUnmatched', app)
%       Warn about CSV rows that never matched a built recording.
%   axionStimEventsTool('reset')
%       Forget the loaded CSV and cached events.

    persistent loadedCSVPath csvRows eventCache rowMatched

    if isempty(eventCache)
        eventCache = containers.Map('KeyType', 'char', 'ValueType', 'any');
    end

    varargout = {};

    switch action
        case 'selectCSV'
            field = varargin{1};
            app = varargin{2};
            [csvName, csvPath] = uigetfile({'*.csv', 'CSV files (*.csv)'}, ...
                'Select stim .raw CSV (raw file name, well, electrode)');
            if ~isequal(csvName, 0)
                field.Value = fullfile(csvPath, csvName);
            end
            if ~isempty(app) && isvalid(app)
                figure(app.UIFigure)   % return focus to the GUI after the dialog
            end

        case 'build'
            [recName, channelNames, coords, Params, app] = varargin{:};
            csvPath = '';
            if isfield(Params, 'axionStimCSV')
                csvPath = Params.axionStimCSV;
            end
            if isempty(csvPath)
                error('axionStimEvents:notConfigured', ...
                    ['No stim .raw CSV selected. Upload it with the "Stim .raw CSV" ' ...
                     'button on the General tab before using the axionStimEvents method.']);
            end
            if ~strcmp(csvPath, char(loadedCSVPath))
                csvRows = readAxionStimCSV(csvPath);
                loadedCSVPath = csvPath;
                eventCache = containers.Map('KeyType', 'char', 'ValueType', 'any');
                rowMatched = false(numel(csvRows), 1);
            end
            if isempty(rowMatched) || numel(rowMatched) ~= numel(csvRows)
                rowMatched = false(numel(csvRows), 1);
            end
            rawFolders = candidateRawFolders(csvPath, Params);
            [stimInfo, eventCache, rowMatched] = buildForRecording( ...
                recName, channelNames, coords, Params, csvRows, rawFolders, ...
                eventCache, rowMatched, app);
            varargout = {stimInfo};

        case 'warnUnmatched'
            if ~isempty(rowMatched) && any(~rowMatched)
                warnUnmatchedRows(csvRows(~rowMatched), varargin{1});
            end

        case 'reset'
            loadedCSVPath = '';
            csvRows = [];
            eventCache = containers.Map('KeyType', 'char', 'ValueType', 'any');
            rowMatched = [];

        otherwise
            error('axionStimEvents:badAction', 'Unknown axionStimEventsTool action "%s".', action);
    end
end


function folders = candidateRawFolders(csvPath, Params)
% Folders to search for the .raw files: next to the CSV, then the MEA data
% folder (where the Axion conversion co-locates .raw and .mat files).
    folders = {};
    csvFolder = fileparts(csvPath);
    if ~isempty(csvFolder)
        folders{end+1} = csvFolder;
    end
    if isfield(Params, 'rawData') && ~isempty(Params.rawData) && ischar(Params.rawData)
        folders{end+1} = Params.rawData;
    end
    folders = unique(folders, 'stable');
    if isempty(folders)
        folders = {pwd};
    end
end


function csvRows = readAxionStimCSV(csvFullPath)
% Read the CSV into a struct array with fields rawName / well / electrode.
% Tolerates an optional header row, ignores blank rows, requires a numeric
% electrode (channel id), and flags malformed or conflicting duplicate rows.

    if ~isfile(csvFullPath)
        error('axionStimEvents:csvNotFound', 'Stim .raw CSV not found: %s', csvFullPath);
    end

    raw = readcell(csvFullPath);
    if size(raw, 2) < 3
        error('axionStimEvents:badCSV', ...
            ['CSV "%s" must have at least 3 columns (raw file name, well, ' ...
             'electrode); found %d.'], csvFullPath, size(raw, 2));
    end

    csvRows = struct('rawName', {}, 'well', {}, 'electrode', {});
    seenKeys = {};

    for r = 1:size(raw, 1)
        if isBlankCell(raw{r, 1}) && isBlankCell(raw{r, 2}) && isBlankCell(raw{r, 3})
            continue   % skip fully empty rows
        end

        rawName = stripKnownExt(toChar(raw{r, 1}));
        well    = normalizeWell(toChar(raw{r, 2}));
        [elec, elecOk] = toElectrodeId(raw{r, 3});

        if ~elecOk
            if r == 1
                continue   % non-numeric electrode in row 1: treat as header
            end
            warning('axionStimEvents:malformedRow', ...
                'Skipping malformed CSV row %d (electrode "%s" is not a numeric channel id).', ...
                r, toChar(raw{r, 3}));
            continue
        end

        if isempty(rawName) || isempty(well)
            warning('axionStimEvents:malformedRow', ...
                'Skipping malformed CSV row %d (empty raw file name or well).', r);
            continue
        end

        key = lower([rawName '_' well]);
        dupIdx = find(strcmp(seenKeys, key), 1);
        if ~isempty(dupIdx)
            if csvRows(dupIdx).electrode ~= elec
                error('axionStimEvents:duplicateRow', ...
                    'Conflicting duplicate CSV rows for %s (well %s): electrodes %d and %d.', ...
                    rawName, well, csvRows(dupIdx).electrode, elec);
            end
            warning('axionStimEvents:duplicateRow', ...
                'Ignoring identical duplicate CSV row %d for %s (well %s).', r, rawName, well);
            continue
        end

        csvRows(end+1) = struct('rawName', rawName, 'well', well, 'electrode', elec); %#ok<AGROW>
        seenKeys{end+1} = key; %#ok<AGROW>
    end

    if isempty(csvRows)
        error('axionStimEvents:emptyCSV', ...
            'No valid data rows found in CSV "%s".', csvFullPath);
    end
end


function [stimInfo, eventCache, rowMatched] = buildForRecording( ...
        recName, channelNames, coords, Params, csvRows, rawFolders, eventCache, rowMatched, app)
% Assemble stimInfo for one recording (one well). The well is identified by
% matching <rawName>_<well> from the CSV against the recording name; the full
% set of StimulationEvent times is then assigned to the CSV-specified electrode.

    recKey = stripKnownExt(recName);

    matchIdx = [];
    for k = 1:numel(csvRows)
        if strcmpi([csvRows(k).rawName '_' csvRows(k).well], recKey)
            matchIdx(end+1) = k; %#ok<AGROW>
        end
    end

    if numel(matchIdx) > 1
        error('axionStimEvents:ambiguousMatch', ...
            'Multiple CSV rows match recording %s; cannot decide the stimulated electrode.', recName);
    end

    if isempty(matchIdx)
        warning('axionStimEvents:noMatch', ...
            'No CSV row matches recording %s; assigning no stimulation to this well.', recName);
        stimInfo = buildStimInfo(channelNames, coords, [], NaN, Params);
        return
    end

    rowMatched(matchIdx) = true;
    row = csvRows(matchIdx);

    if ~any(channelNames == row.electrode)
        error('axionStimEvents:electrodeNotFound', ...
            ['Electrode %d (CSV) is not a channel in recording %s. ' ...
             'Available channels: %s.'], row.electrode, recName, mat2str(channelNames(:)'));
    end

    [eventTimes, eventCache] = getEventTimes(rawFolders, row.rawName, eventCache, app);
    if isempty(eventTimes)
        warning('axionStimEvents:noEvents', ...
            'No StimulationEvents found in raw file "%s"; well %s will have no stimulation times.', ...
            row.rawName, recName);
    end

    stimInfo = buildStimInfo(channelNames, coords, eventTimes, row.electrode, Params);
end


function [eventTimes, eventCache] = getEventTimes(rawFolders, rawName, eventCache, app)
% Return the StimulationEvent times (seconds, column vector) for a raw file,
% reading them via AxisFile and caching per raw file. Voltage is never loaded.

    cacheKey = lower(rawName);
    if isKey(eventCache, cacheKey)
        eventTimes = eventCache(cacheKey);
        return
    end

    matchFile = '';
    for fi = 1:numel(rawFolders)
        rawList = dir(fullfile(rawFolders{fi}, '*.raw'));
        for f = 1:numel(rawList)
            if strcmpi(stripKnownExt(rawList(f).name), rawName)
                matchFile = fullfile(rawFolders{fi}, rawList(f).name);
                break
            end
        end
        if ~isempty(matchFile)
            break
        end
    end
    if isempty(matchFile)
        error('axionStimEvents:rawNotFound', ...
            'Raw file "%s.raw" referenced by the CSV was not found in: %s.', ...
            rawName, strjoin(rawFolders, '; '));
    end

    statusUpdate(app, sprintf('axionStimEvents: reading stimulation events from %s', rawName));
    fileData = AxisFile(matchFile);
    events = fileData.StimulationEvents;
    if isempty(events)
        eventTimes = [];
    else
        et = double([events.EventTime]);
        eventTimes = sort(et(:));   % seconds, column vector
    end

    eventCache(cacheKey) = eventTimes;
end


function stimInfo = buildStimInfo(channelNames, coords, eventTimes, targetChannel, Params)
% Build the stimInfo cell (one struct per channel) in the exact format the
% existing methods produce. All StimulationEvent times are assigned to the
% stimulated electrode; every other channel gets none. The blanking fields are
% populated so downstream artifact removal ignores [stimTime, stimTime +
% postStimWindowDur] (the GUI "post stim ignore duration").

    stimDur = Params.stimDuration;
    numChannels = length(channelNames);
    eventTimes = eventTimes(:);
    stimInfo = cell(numChannels, 1);

    for channel_idx = 1:numChannels
        if ~isnan(targetChannel) && channelNames(channel_idx) == targetChannel
            elecStimTimes = eventTimes;
        else
            elecStimTimes = [];
        end

        stimStruct = struct();
        stimStruct.elecStimTimes = elecStimTimes;
        stimStruct.elecStimDur   = repmat(stimDur, length(elecStimTimes), 1);
        stimStruct.channelName   = channelNames(channel_idx);
        stimStruct.coords        = coords(channel_idx, :);

        % Each stimulation time starts a blank; the blank duration is left at 0
        % so the ignored window equals [stimTime, stimTime + postStimWindowDur].
        stimStruct.blankStarts        = elecStimTimes;
        stimStruct.blankEnds          = elecStimTimes;
        stimStruct.nonStimBlankStarts = 0;
        stimStruct.nonStimBlankEnds   = 0;
        stimStruct.blankDurations     = zeros(length(elecStimTimes), 1);

        stimInfo{channel_idx} = stimStruct;
    end
end


function warnUnmatchedRows(unmatchedRows, app)
    names = arrayfun(@(r) sprintf('%s_%s', r.rawName, r.well), unmatchedRows, ...
        'UniformOutput', false);
    msg = sprintf('axionStimEvents: %d CSV row(s) did not match any processed recording: %s', ...
        numel(unmatchedRows), strjoin(names, ', '));
    warning('axionStimEvents:unmatchedRows', '%s', msg);
    statusUpdate(app, msg);
end


function statusUpdate(app, msg)
    if ~isempty(app) && isvalid(app) && isprop(app, 'MEANAPStatusTextArea')
        app.MEANAPStatusTextArea.Value = [app.MEANAPStatusTextArea.Value; msg];
        drawnow
    end
end


function s = stripKnownExt(s)
% Remove any directory part and a trailing .raw/.mat extension only, preserving
% dots inside the name (e.g. "AK_HCNT24.4_DIV60").
    s = strtrim(s);
    sepIdx = find(s == '/' | s == '\', 1, 'last');
    if ~isempty(sepIdx)
        s = s(sepIdx+1:end);
    end
    if numel(s) >= 4 && (strcmpi(s(end-3:end), '.raw') || strcmpi(s(end-3:end), '.mat'))
        s = s(1:end-4);
    end
end


function w = normalizeWell(w)
    w = strtrim(w);
    w = regexprep(w, '^_+', '');   % drop leading underscores if present
end


function s = toChar(v)
    if ischar(v)
        s = strtrim(v);
    elseif isstring(v)
        s = strtrim(char(v));
    elseif isnumeric(v)
        if isempty(v) || (isscalar(v) && isnan(v))
            s = '';
        else
            s = strtrim(num2str(v));
        end
    elseif isa(v, 'missing')
        s = '';
    else
        s = strtrim(char(string(v)));
    end
end


function [id, ok] = toElectrodeId(v)
    ok = false;
    id = NaN;
    if isnumeric(v)
        if isscalar(v) && isfinite(v)
            id = double(v);
            ok = true;
        end
    else
        n = str2double(toChar(v));
        if ~isnan(n)
            id = n;
            ok = true;
        end
    end
    if ok
        id = round(id);
    end
end


function tf = isBlankCell(v)
    if isa(v, 'missing')
        tf = true;
    elseif isnumeric(v)
        tf = isempty(v) || all(isnan(v(:)));
    elseif ischar(v) || isstring(v)
        tf = strlength(strtrim(string(v))) == 0;
    else
        tf = false;
    end
end
