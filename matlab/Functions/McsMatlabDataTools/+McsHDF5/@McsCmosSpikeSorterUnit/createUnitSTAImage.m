function STAImage = createUnitSTAImage(str)
% STA Image generator for SpikeSorterUnit Object
%
% function STAImages = createUnitSTAImage(str)
%
% Takes a SpikeSorterUnit Object and computes the single Unit STA image
% struct
%
%   INPUT:
%
%       str         -   SpikeSorterUnit Object
%
%
%   OUTPUT:
%
%       STAImage    -   Struct containing an STA Image and Metadata. The
%                           struct holds the following field:
%                           'image': matrix holding the normalized sta
%                               activity values
%                           'sensorIDs: holding the sensor IDs used to
%                               construct the image
%                           'coordinates: holding the coordinates
%                               corresponding to sensor IDs on the chip
%
    % PARAMETERS
    sensorXDimension = 65;
    sensorYDimension = 65;

    channelIDs = regexp(str.RoiSTAsInfo.ChannelIDs, ' ', 'split');
    channelIDs = cellfun(@str2num,channelIDs).';

    % Compute Pixel Values
    pixelValues = max(str.RoiSTAs,[],1);
    
    %Allocate an Image of Sensor size
    image = zeros(sensorYDimension, sensorXDimension);

    % Convert ChannelIDs into coordinates
    for channel=1:length(channelIDs)
        coordinates(:,channel) = McsHDF5.ID2coordinates(channelIDs(channel),sensorYDimension, sensorXDimension);
        image(coordinates(2,channel),coordinates(1,channel)) = pixelValues(channel);
    end
    
    %Normalize Image
    image = image/max(pixelValues);
    
    %trim image to ROI Size
    image = image([min(coordinates(2,:)):1:max(coordinates(2,:))],[min(coordinates(1,:)):1:max(coordinates(1,:))]);
%    imshow(image)
    
    %Store data
    STAImage.image          = image;
    STAImage.sensorIDs      = channelIDs;
    STAImage.coordinates    = coordinates;
    
end

