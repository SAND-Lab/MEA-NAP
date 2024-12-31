MEANAPviewerApp = MEANAPviewer;
MEANAPviewerApp.UIFigure.Name = 'MEA-NAP viewer';

% Resize the right column 
% Currently the ordering are 
%(1) Left gap (2) File selection (3) Gap (4) Image (5) File manager button
MEANAPviewerApp.GridLayout.ColumnWidth = {[79]  '0.5x'  [50]  '1x'  [125]};
MEANAPviewerApp.GridLayout.RowHeight = {[22]  [20]  '1x'   'fit'  '0.5x', [20], [20]};
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

recordingFpath = MEANAPviewerApp.RecordingEditField.Value;
nodeColorMetric = MEANAPviewerApp.ListBox.Value;
edgeThresh = MEANAPviewerApp.EdgethresholdEditField.Value;
cellTypeToPlot = MEANAPviewerApp.CelltypesListBox.Value;
expData = [];


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
    
    % TODO: Use experiment mat file selection to plot network
    if MEANAPviewerApp.RecordingSelectButton.Value == 1
        [file, location] = uigetfile('*.mat');
        MEANAPviewerApp.RecordingEditField.Value = fullfile(location, file);
        MEANAPviewerApp.RecordingSelectButton.Value = 0;
        figure(MEANAPviewerApp.UIFigure)  % put app back to focus
        
        MEANAPviewerApp.EdgethresholdEditField.Visible = 'on';
        MEANAPviewerApp.EdgeThresholdLabel.Visible = 'on';
    end
    
    recordingFpathChanged = ~strcmp(recordingFpath, MEANAPviewerApp.RecordingEditField.Value);
    edgeThreshChanged = ~(edgeThresh == MEANAPviewerApp.EdgethresholdEditField.Value);
    nodeColorMetricChanged = ~strcmp(nodeColorMetric, MEANAPviewerApp.ListBox.Value);
    
    if length(cellTypeToPlot) ~= length(MEANAPviewerApp.CelltypesListBox.Value)
       cellTypeToPlotChanged = 1;
    else 
       cellTypeToPlotChanged = any(~strcmp(cellTypeToPlot, MEANAPviewerApp.CelltypesListBox.Value)); 
    end
    
    
    
    if recordingFpathChanged
        recordingFpath = MEANAPviewerApp.RecordingEditField.Value;
        expData = load(recordingFpath);
        adjM = expData.adjMs.adjM1000mslag;
        inclusionIndex = expData.NetMet.adjM1000mslag.activeNodeIndices;
        
        if isfield(expData.Info, 'CellTypes')
            [cellTypeMatrix, cellTypeNames] = getCellTypeMatrix(expData.Info.CellTypes, expData.channels); 
            cellTypeMatrixActive = cellTypeMatrix(inclusionIndex, :);
            MEANAPviewerApp.CelltypesListBox.Items = cellTypeNames;
            MEANAPviewerApp.CelltypesListBox.Value = cellTypeNames{1};
            MEANAPviewerApp.CelltypesListBox.Visible = 'on';
            MEANAPviewerApp.CelltypesListBoxLabel.Visible = 'on';
             
        else 
            cellTypeMatrix = nan; 
            cellTypeNames = nan;
        end
    end
    
    if cellTypeToPlotChanged
        
        cellTypeToPlot = MEANAPviewerApp.CelltypesListBox.Value;
        adjM = expData.adjMs.adjM1000mslag;
        inclusionIndex = expData.NetMet.adjM1000mslag.activeNodeIndices;
        [cellTypeMatrix, cellTypeNames] = getCellTypeMatrix(expData.Info.CellTypes, expData.channels); 
        cellTypeMatrixActive = cellTypeMatrix(inclusionIndex, :);
        
        % do further subsetting based on cell type
        subsetColumns = find(contains(cellTypeNames, cellTypeToPlot));
        cellTypeSubsetIndex = find(sum(cellTypeMatrixActive(:, subsetColumns), 2) == length(cellTypeToPlot));
        
        inclusionIndex = inclusionIndex(cellTypeSubsetIndex);
        cellTypeMatrixActive = cellTypeMatrixActive(cellTypeSubsetIndex, :);
    end
    
    % TODO: max node size, node size scaling, node scaling power 
    maxNodeSize = 1;  
    
    if recordingFpathChanged || nodeColorMetricChanged || edgeThreshChanged || cellTypeToPlotChanged
        
        nodeColorMetric = MEANAPviewerApp.ListBox.Value;
        edgeThresh = MEANAPviewerApp.EdgethresholdEditField.Value;


        adjMsubset = adjM(inclusionIndex, inclusionIndex);
        coords = expData.coords;
                
        z = expData.NetMet.adjM1000mslag.ND; 
        zname = 'Nodedegree';
        
        if strcmp(nodeColorMetric, 'None') 
           z2 = zeros(length(inclusionIndex), 1) + nan;
        else
           z2 = expData.NetMet.adjM1000mslag.(nodeColorMetric); 
        end

        z2name = nodeColorMetric;
        FN = 'temp'; 
        pNum = '1';
        plotType = 'MEA';
        Params = expData.Params;
        lagval = 1000;
        e = 1;
        figFolder = '/home/timothysit/AnalysisPipeline';
        figureHandle = figure('visible', 'off');
        saveFigure = 1;
        
        addpath(genpath('/home/timothysit/AnalysisPipeline/Functions'));
        
        StandardisedNetworkPlotNodeColourMap(adjMsubset, coords, edgeThresh, ...
            z, zname, z2, z2name, plotType, ...
            FN, pNum, Params, lagval, e, figFolder, figureHandle, saveFigure, cellTypeMatrixActive, cellTypeNames); 
        close all
        
        FN = sprintf('%s_%s_NetworkPlot%s%s.png', pNum, plotType, zname, z2name);
        imgPath = fullfile(figFolder, FN);
        img = imread(imgPath);
        set(hImage, 'CData', img);
        
    end
    
        
    if ~isempty(recordingFpath)
       MEANAPviewerApp.ListBox.Visible = 'on'; 
       MEANAPviewerApp.NodeColorLabel.Visible = 'on';
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