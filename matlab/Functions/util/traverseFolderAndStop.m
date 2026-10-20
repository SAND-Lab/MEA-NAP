function parentNode = traverseFolderAndStop(parentNode, currentFolder)
    % This only goes one folder (does not recurvesily go through folder)

    % Get all contents of the current folder
    contents = dir(currentFolder);
    
    % Filter out '.' and '..' directories
    contents = contents(~ismember({contents.name}, {'.', '..'}));
    [~, sort_idx] = natsort({contents.name});
    contents = contents(sort_idx);
    
    for i = 1:length(contents)
        % Get the name and full path of the current item
        itemName = contents(i).name;
        itemFullPath = fullfile(currentFolder, itemName);
        
        if contents(i).isdir
            % If it's a folder, create a new uitreenode
            folderNode = uitreenode(parentNode, 'Text', itemName, 'NodeData', itemFullPath);
            % parentNode.addChild(folderNode);
           
        else
            % If it's an image file, create a new node and add it
            [~, ~, ext] = fileparts(itemFullPath);
            if isImageFile(ext)
                imageNode = uitreenode(parentNode, 'Text', itemName, 'NodeData', itemFullPath);
                % parentNode.addChild(imageNode);
            end
        end
    end
    
end