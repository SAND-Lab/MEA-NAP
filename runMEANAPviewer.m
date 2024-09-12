MEANAPviewerApp = MEANAPviewer;
MEANAPviewerApp.UIFigure.Name = 'MEA-NAP viewer';

% Resize the right column 
% Currently the ordering are 
%(1) Left gap (2) File selection (3) Gap (4) Image (5) File manager button
MEANAPviewerApp.GridLayout.ColumnWidth = {[79]  '0.5x'  [50]  '1x'  [125]};
MEANAPviewerApp.GridLayout.RowHeight = {[22]  [20]  '1x'   'fit'  '0.5x'};
% Update viewer tree
mainFolder = pwd;

% Get output folder, either from MEANAPapp (app) or set to empty at first
if exist('app', 'var') 
    outputFolder = app.OutputDataFolderEditField.Value;
    MEANAPviewerApp.OutputFolderEditField.Value = outputFolder;
else 
    addpath(genpath(fullfile(mainFolder, 'Functions', 'util')));
    outputFolder = MEANAPviewerApp.OutputFolderEditField.Value;
end 

% Directly get tree (only do it when outputFolder is updated...)
if isfolder(outputFolder)
    folderTree = constructTree(MEANAPviewerApp.Tree, outputFolder);
else 
    folderTree = nan;
end

% Get figure legend table 
figureLegendTable = readtable(fullfile(mainFolder, 'imgs', 'figureLegends.csv'));

% Initialise legend text 
MEANAPviewerApp.FigurelegendLabel.Text = 'Please select a figure to display figure legend';

prevSelectedItemText = '';

% initialise image axes and blank image) 
% NOTE: somehow it is much faster / prevents the app from hanging if you 
% create uiaxes() programmatically, rather than do it in the app designer 
% so here I am using an app.Image object as a placeholder, then move over
% some of the properties onto imageAxes, then delete the app.Image object
% NOTE: imagesc() is faster than imshow()
initialImage = zeros(100, 100, 3) + 255;
imageAxes = uiaxes(MEANAPviewerApp.GridLayout);
imageAxes.Layout = MEANAPviewerApp.Image.Layout;
hImage = imagesc(initialImage, 'Parent', imageAxes, 'Interpolation','nearest');
imageAxes.XTick = [];
imageAxes.YTick = [];
imageAxes.XAxis.Visible = 'off';
imageAxes.YAxis.Visible = 'off';
axis(imageAxes, 'equal'); 
delete(MEANAPviewerApp.Image)

while isvalid(MEANAPviewerApp)
   
    % Output folder selection button 
    if MEANAPviewerApp.OutputFolderSelectButton.Value == 1
        MEANAPviewerApp.OutputFolderEditField.Value = uigetdir;
        MEANAPviewerApp.OutputFolderSelectButton.Value = 0;
        figure(MEANAPviewerApp.UIFigure)  % put app back to focus
    end 
    
    % Check if output folder field has changed, if so update the tree
    if ~strcmp(outputFolder, MEANAPviewerApp.OutputFolderEditField.Value)
        outputFolder = MEANAPviewerApp.OutputFolderEditField.Value;
        if isfolder(outputFolder)
            treeChildren = MEANAPviewerApp.Tree.Children;
            % Remove previous children (to avoid duplicates)
            treeChildren.delete;
            % folderTree = traverseFolder(MEANAPviewerApp.Tree, outputFolder);
            folderTree = traverseFolderDepth2(MEANAPviewerApp.Tree, outputFolder);
        else 
            folderTree = nan;
        end
    end
    
    % Get selected tree item 
    if isa(folderTree, 'matlab.ui.container.Tree')
        selectedItems = folderTree.SelectedNodes;
    else 
        selectedItems = [];
    end
    
    % Display selected image
    if ~isempty(selectedItems) && ~strcmp(prevSelectedItemText, selectedItems.Text)
        prevSelectedItemText = selectedItems.Text;
        [~, fname, ext] = fileparts(selectedItems.NodeData);
        
        if isfolder(selectedItems.NodeData)
            selectedItems = traverseFolderDepth2(selectedItems, selectedItems.NodeData);
            expand(selectedItems)
        elseif isImageFile(ext)
            % MEANAPviewerApp.Image.ImageSource = selectedItems.NodeData;
            img = imread(selectedItems.NodeData);
            set(hImage, 'CData', img);
            % reset the axes
            imageAxes.XLim = [-inf inf];
            imageAxes.YLim = [-inf inf];
            drawnow
            
            % See if figure legend exists, if so update it
            if any(ismember(figureLegendTable.FigureName, fname))
                figureIndex = find(ismember(figureLegendTable.FigureName, fname));
                MEANAPviewerApp.FigurelegendLabel.Text = figureLegendTable.Legend{figureIndex};
                MEANAPviewerApp.FigureTitleLabel.Text = figureLegendTable.Title{figureIndex};
            else
                MEANAPviewerApp.FigurelegendLabel.Text = 'Please select a figure to display figure legend';
                MEANAPviewerApp.FigureTitleLabel.Text = 'Figure title';
            end
            
        end
    end 
    
    % Show image in default folder 
    if MEANAPviewerApp.OpeninfilemanagerButton.Value == 1
        [selectedItemFolder,~,~] = fileparts(selectedItems.NodeData);
        system(['open ' selectedItemFolder]);
        MEANAPviewerApp.OpeninfilemanagerButton.Value = 0;
    end 
    
    
    pause(0.1)
end