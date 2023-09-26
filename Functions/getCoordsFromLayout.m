function [channels,coords] = getCoordsFromLayout(channelLayout)
%GETCOORDSFROMLAYOUT Summary of this function goes here
%   Detailed explanation goes here
if strcmp(channelLayout, 'MCS60old')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [21 31 41 51 61 71 12 22 32 42 52 62 72 82 13 23 33 43 53 63 ... 
    73 83 14 24 34 44 54 64 74 84 15 25 35 45 55 65 75 85 16 26 ...
    36 46 56 66 76 86 17 27 37 47 57 67 77 87 28 38 48 58 68 78];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx); 
    coords = Params.coords(reorderingIdx, :);

elseif strcmp(channelLayout, 'MCS60')

     channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [47, 48, 46, 45, 38, 37, 28, 36, 27, 17, 26, 16, 35, 25, ...
    15, 14, 24, 34, 13, 23, 12, 22, 33, 21, 32, 31, 44, 43, 41, 42, ...
    52, 51, 53, 54, 61, 62, 71, 63, 72, 82, 73, 83, 64, 74, 84, 85, 75, ...
    65, 86, 76, 87, 77, 66, 78, 67, 68, 55, 56, 58, 57];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    coords = Params.coords(reorderingIdx, :);
    % Params.reorderingIdx = reorderingIdx;

elseif strcmp(channelLayout, 'MCS59')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];

    channelsOrdering = ...
    [47, 48, 46, 45, 38, 37, 28, 36, 27, 17, 26, 16, 35, 25, ...
    15, 14, 24, 34, 13, 23, 12, 22, 33, 21, 32, 31, 44, 43, 41, 42, ...
    52, 51, 53, 54, 61, 62, 71, 63, 72, 82, 73, 83, 64, 74, 84, 85, 75, ...
    65, 86, 76, 87, 77, 66, 78, 67, 68, 55, 56, 58, 57];

    Params.coords = zeros(length(channels), 2);
    Params.coords(:, 2) = repmat(linspace(1, 0, 8), 1, 8);
    Params.coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);

    subset_idx = find(~ismember(channels, [11, 81, 18, 88]));
    channels = channels(subset_idx);

    reorderingIdx = zeros(length(channels), 1);
    for n = 1:length(channels)
        reorderingIdx(n) = find(channelsOrdering(n) == channels);
    end 
    
    Params.coords = Params.coords(subset_idx, :);

    % Re-order the channel IDs and coordinates to match the original
    % ordering
    channels = channels(reorderingIdx);
    Params.channels = channels; 
    Params.coords = Params.coords(reorderingIdx, :);

    inclusionIndex = find(channelsOrdering ~= 82);
    channels = channels(inclusionIndex);
    coords = Params.coords(inclusionIndex, :);
    % Params.reorderingIdx = reorderingIdx; % (inclusionIndex)


elseif strcmp(channelLayout, 'Axion64')

    channels = [11, 12, 13, 14, 15, 16, 17, 18, ... 
            21, 22, 23, 24, 25, 26, 27, 28, ...
            31, 32, 33, 34, 35, 36, 37, 38, ...
            41, 42, 43, 44, 45, 46, 47, 48, ...
            51, 52, 53, 54, 55, 56, 57, 58, ...
            61, 62, 63, 64, 65, 66, 67, 68, ...,
            71, 72, 73, 74, 75, 76, 77, 78, ...,
            81, 82, 83, 84, 85, 86, 87, 88];
    coords = zeros(length(channels), 2);
    coords(:, 2) = repmat(linspace(0, 1, 8), 1, 8);
    coords(:, 1) = repelem(linspace(0, 1, 8), 1, 8);



elseif strcmp(channelLayout, 'Custom')

    x_min = 0;
    x_max = 1;
    y_min = 0;
    y_max = 1;
    num_nodes = 64;
    
    rand_x_coord = (x_max - x_min) .* rand(num_nodes,1) + x_min;
    rand_y_coord = (y_max - y_min) .* rand(num_nodes, 1) + y_min; 
    coords = [rand_x_coord, rand_y_coord];

    coords  = Params.coords * 8;

end 

coords  = coords * 8;  % Do not remove this line after specifying coordinate positions in (0 - 1 format)

end

