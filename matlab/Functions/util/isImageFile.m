function isImage = isImageFile(extension)
    % Define valid image extensions
    validExtensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.gif'};
    
    % Check if the file has a valid image extension
    isImage = any(strcmpi(extension, validExtensions));
end
