function STAImage = createSensorSTAImage(str)
% STA Image generator for SpikeSorterSource Object
%
% function STAImages = createUnitSTAImage(str)
%
% Takes a SpikeSorterUnit Object and computes the single Unit STA image
% struct
%
%   INPUT:
%
%       str         -   SpikeSorterSource Object
%
%
%   OUTPUT:
%
%       STAImage    -   Struct containing an STA Image and Metadata. The
%                           struct holds the following field:
%                           'image': matrix that holds the combined STAimage
%                               information

    % PARAMETERS
    sensorXDimension = 65;
    sensorYDimension = 65;
    
    %Allocate an Image of Sensor size
    image = zeros(sensorYDimension, sensorXDimension);

    % Compute unit images and puzzle them together
    for unit=1:length(str.UnitEntities)
        unitSTAImage = McsHDF5.McsCmosSpikeSorterUnit.createUnitSTAImage(str.UnitEntities{unit});
        image(min(unitSTAImage.coordinates(2,:)):1:max(unitSTAImage.coordinates(2,:)), min(unitSTAImage.coordinates(1,:)):1:max(unitSTAImage.coordinates(1,:))) = max(unitSTAImage.image,image(min(unitSTAImage.coordinates(2,:)):1:max(unitSTAImage.coordinates(2,:)), min(unitSTAImage.coordinates(1,:)):1:max(unitSTAImage.coordinates(1,:))));
    end
    %imshow(imresize(image,[512 512]))
    
    %Store data
    STAImage.image          = image;
    
end

