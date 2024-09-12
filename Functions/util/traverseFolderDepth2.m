function parentNode = traverseFolderDepth2(parentNode, currentFolder)
    

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
        
        % Skipped over children that were already seen
        if ~isempty(parentNode.Children)
            if ismember(contents(i).name, {parentNode.Children.Text})
               continue 
            end
        end 
        
        if contents(i).isdir
            % If it's a folder, create a new uitreenode
            folderNode = uitreenode(parentNode, 'Text', itemName, 'NodeData', itemFullPath);
            % parentNode.addChild(folderNode);

            % Recursively traverse the folder and add its contents
            traverseFolderAndStop(folderNode, itemFullPath);
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