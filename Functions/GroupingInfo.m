function [GrpInfo, GrpNames] = GroupingInfo(spikeDetectedData)

% this function allows user to input information about groups/categories for the data

cd(spikeDetectedData)

GrpInfo = [];

%% how many types of groupings?

GrpNum =  inputdlg({'How many group/category types? For example, if categories are age and cell line, enter ''2'''});

GrpNum = str2double(GrpNum);

%% what are the names of the groupings and categories

for i = 1:GrpNum
    TempCell{i,1} = strcat('Grouping',num2str(i));
end

prompt = TempCell;
dlgtitle = 'What are the names of the group/category types? For example ''DIV'' and ''CellLine''';
dims = [1 35];
definput = {'DIV','CellLine'};
GrpNames =  inputdlg(prompt,dlgtitle,dims,definput);


for i = 1:length(GrpNames)
    eval(['GrpInfo.' char(GrpNames(i)) ' = [];']);
end

clear TempCell

%% loop through each recording 

RecList = dir('*.mat');

for i = 1:length(RecList)
    for j = 1:length(GrpNames)
        TempCell{j,1} = strcat('Within the category ',char(GrpNames(j)),', name the group this recording belongs to (e.g. WT, KO or DIV150)');
    end
    
    GrpInd = inputdlg(TempCell,RecList(i).name);
    
    for j = 1:length(GrpNames)
        eval(['GrpInfo.' char(GrpNames(j)) '{i} = GrpInd(j);']);
    end
    
end

clear TempCell

end