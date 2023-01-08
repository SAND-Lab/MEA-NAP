function [hubBoundaryWMdDeg, periPartCoef, proHubpartCoef, nonHubconnectorPartCoef, connectorHubPartCoef] = ...
    TrialLandscapeDensity(ExpList, fig_folder, add_fig_info, cartographyLagVal)
%{
This script calculates and plots the distribution 
of Within-module Z-score (Z) and participation coefficient (PC)
for each electrode across recordings.

Parameters
-----------
ExpList: struct 
    structure containing names of files to analyse, this should be the
    output of dir() command, so should contain the fields : name, folder,
    date, bytes, isdir, datenum
fig_folder : str
    folder to save the plots
add_fig_info : str
    optional str to add an extra name tag to the figure, set to '' if this
    is not needed
cartographyLagVal : int 
    lag value in ms
Returns
-------
hubBoundaryWMdDeg : float
    boundary that separates hub and non-hubs

%}

PC = [];
Z = [];

%% Parameters
% TODO: explain what are these parameters
% sigma = [0 0.035 0.05 0.08];  
sigma = [0];
% I think the sigma and bandwidth does more or less the same thing
% so one can just keep sigma at 0 and play with more bandwidth parameters

PCmin = 0;
PCmax = 1;
Zmin = -2;
Zmax = 4;

bandw = [0.06, 0.08, 0.1];  % TODO: allow trying out more values

%% For each recording, load Z (within-module Z-score) and PC (participation coefficient)
Var = {'PC','Z'};

for n = 1:length(ExpList)
    
    FN = ExpList(n).name;
    fileFolder = ExpList(n).folder;
    filePath = fullfile(fileFolder, FN);
    % TODO: suppress figure handle popping up when loading
    load(filePath)
    
    for i = 1:length(Var)
        VN = cell2mat(Var(i));
        VNs = strcat(sprintf('NetMet.adjM%.fmslag.', cartographyLagVal), VN);
        eval([VN '= [' VN ';' VNs '];']);
    end
    
    clear Info NetMet adjMs
    
end

% In case figure handles are loaded
close all 

X = [Z,PC];

sortZ = sort(Z,'descend');

% I guess this can be commented out?
% 0.02*length(Z)

%% Determine clusters 
n_z_partitions = 2;
z_cluster_idx = kmeans(Z, n_z_partitions);
z_cluster_group_1 = Z(z_cluster_idx == 1);
z_cluster_group_2 = Z(z_cluster_idx == 2);

z_cluster_group_1_min = min(z_cluster_group_1);
z_cluster_group_1_max = max(z_cluster_group_1);
z_cluster_group_2_min = min(z_cluster_group_2);
z_cluster_group_2_max = max(z_cluster_group_2);

if z_cluster_group_1_max > z_cluster_group_2_max
    z_boundary = (z_cluster_group_2_max + z_cluster_group_1_min) / 2;
    else
    z_boundary = (z_cluster_group_1_max + z_cluster_group_2_min) / 2;
end 


%{
figure;
histogram(z_cluster_group_1, 'FaceColor', 'blue');
hold on
histogram(z_cluster_group_2, 'FaceColor', 'red');
xline(z_boundary)
set(gcf, 'color', 'white')
ylabel('Count')
xlabel('Z')
%} 

num_hub_partitions = 3;
num_non_hub_partitions = 3;

% Compute the boundary values for the hubs
hub_pc_vals = PC(Z >= z_boundary);
hub_cluster_idx = kmeans(hub_pc_vals, num_hub_partitions);
hub_group_pc_mins = zeros(num_hub_partitions, 1);
hub_group_pc_maxs = zeros(num_hub_partitions, 1);
for group_id = 1:num_hub_partitions
    hub_group_pc_mins(group_id) = min(hub_pc_vals(hub_cluster_idx == group_id));
    hub_group_pc_maxs(group_id) = max(hub_pc_vals(hub_cluster_idx == group_id));
end 
[hub_group_pc_maxs_sorted, sort_idx] = sort(hub_group_pc_maxs);
hub_group_pc_mins_sorted = hub_group_pc_mins(sort_idx);
hub_pc_boundaries = zeros(num_hub_partitions-1, 1);
for n_boundary = 1:num_non_hub_partitions-1
    % boundary set to be halfway between the max of the "left" group 
    % and the min of the "right" group
    hub_pc_boundaries(n_boundary) = (hub_group_pc_maxs_sorted(n_boundary) + hub_group_pc_mins_sorted(n_boundary+1)) / 2;
end 

% Compute the boundary vlaues for the non-hubs
non_hub_pc_vals = PC(Z < z_boundary);
non_hub_cluster_idx = kmeans(non_hub_pc_vals, num_non_hub_partitions);
non_hub_group_pc_mins = zeros(num_non_hub_partitions, 1);
non_hub_group_pc_maxs = zeros(num_non_hub_partitions, 1);
for group_id = 1:num_non_hub_partitions
    non_hub_group_pc_mins(group_id) = min(non_hub_pc_vals(non_hub_cluster_idx == group_id));
    non_hub_group_pc_maxs(group_id) = max(non_hub_pc_vals(non_hub_cluster_idx == group_id));
end 
[non_hub_group_pc_maxs_sorted, non_hub_sort_idx] = sort(non_hub_group_pc_maxs);
non_hub_group_pc_mins_sorted = non_hub_group_pc_mins(non_hub_sort_idx);
non_hub_pc_boundaries = zeros(num_non_hub_partitions-1, 1);
for n_boundary = 1:num_non_hub_partitions-1
    % boundary set to be halfway between the max of the "left" group 
    % and the min of the "right" group
    non_hub_pc_boundaries(n_boundary) = (non_hub_group_pc_maxs_sorted(n_boundary) + non_hub_group_pc_mins_sorted(n_boundary+1)) / 2;
end 


% Plot the final automatically generated partitions 
figure;
scatter(PC, Z);
hold on 
yline(z_boundary)

for n_boundary = 1:num_hub_partitions-1
    plot([hub_pc_boundaries(n_boundary), hub_pc_boundaries(n_boundary)], ...
        [z_boundary, Zmax])
end 

for n_boundary = 1:num_non_hub_partitions-1
    plot([non_hub_pc_boundaries(n_boundary), non_hub_pc_boundaries(n_boundary)], ...
        [-Zmax, z_boundary])
end 


xlabel('Participation Coefficient (PC)')
ylabel('Within-module Z-score (Z)')
set(gcf, 'color', 'white');
fig_name = strcat(['ZandPC_scatter_with_kmeans_boundaries_', add_fig_info]); 
fig_fullpath = fullfile(fig_folder, fig_name);
% Export figure

% temporary measure to make this backwards compatible
if ~isfield(Params, 'figExt')
    Params.figExt = {'.png'}; 
end 

for nFigExt = 1:length(Params.figExt)
    saveas(gcf,strcat([fig_fullpath, Params.figExt{nFigExt}]));
end 

close(gcf)


%% Add gaussian distribution

% The first sigma (0) is withouut Gaussian convolution, so 
% just set it to the original Z and PC values
eval(['Xsigm' num2str(sigma(1)) '= [Z,PC];']);

for n = 2:length(sigma)
    
    PCtemp = [];
    Ztemp = [];
    
    for i = 1:length(PC)
        
        pd = makedist('Normal','mu',PC(i),'sigma',sigma(n));
        r = random(pd,[1,1000]);
        
        pd2 = makedist('Normal','mu',Z(i),'sigma',sigma(n));
        r2 = random(pd2,[1,1000]);
        
        PCtemp = [PCtemp; r'];
        Ztemp = [Ztemp; r2'];
        
        clear pd pd2 r r2
    end
    
    Xtemp = [Ztemp,PCtemp];
    eval(['Xsigm' num2str(sigma(n)*1000) ' = Xtemp;']);
    eval(['PCsigm' num2str(sigma(n)*1000) ' = PCtemp;']);
    eval(['Zsigm' num2str(sigma(n)*1000) ' = Ztemp;']);
    
    clear PCtemp Ztemp Xtemp
    
end

      
%% ks density version
% TODO: this part takes longer than I expect, look into what is slow

zSpacing = -0.05;  % originally -0.05, modify to speed things up
pcSpacing = 0.02;  % originally 0.01, modify to speed things up 

gridx1 = Zmax:zSpacing:Zmin;
gridx2 = PCmin:pcSpacing:PCmax;
[x1,x2] = meshgrid(gridx1, gridx2);
x1 = x1(:);
x2 = x2(:);
xi = [x1 x2];

gridx1b = 1:length(gridx1);
gridx2b = 1:length(gridx2);
[x1b,x2b] = meshgrid(gridx1b, gridx2b);

for n = 1:length(sigma)
    
    eval(['X = Xsigm' num2str(sigma(n)*1000) ';']);
    
    p = [20 100 1400 400];
    set(0, 'DefaultFigurePosition', p)
    figure()
    subplot(1,length(bandw)+1,1)
    scatter(X(:,2),X(:,1),5,'filled')
    xlim([PCmin PCmax])
    ylim([Zmin Zmax])
    xlabel('PC')
    ylabel('Z')
    title(strcat('sigma=',num2str(sigma(n))))
    
    for u = 1:length(bandw)

        % This line here seems to take quite long
        [f,xii] = ksdensity(X,xi,'Bandwidth',bandw(u));
        
        DensityLandcape = accumarray([x1b(:),x2b(:)],f(:));
        subplot(1,length(bandw)+1,u+1)
        imagesc(DensityLandcape)
        colormap(jet(256))
        colorbar
        
        xtcks = 0:length(gridx2b)/5:length(gridx2b);
        xticks(xtcks)
        xtcklab = PCmin:0.2:PCmax;
        xticklabels(strsplit(num2str(xtcklab)))
        
        ytcks = length(gridx1b)/(Zmax-Zmin):length(gridx1b)/(Zmax-Zmin):length(gridx1b)/(Zmax-Zmin)*(Zmax-Zmin);
        yticks(ytcks);
        ytcklab = Zmax-1:-1:Zmin+1;
        yticklabels(strsplit(num2str(ytcklab)))
        
        xlabel('PC')
        ylabel('Z')
        title(strcat('sigma=',num2str(sigma(n)),',','bandwidth=',num2str(bandw(u))))

                
    end 


     % TODO: save the figure
    sigma_str = strrep(num2str(sigma(n)), '.', 'p');
    fig_name = strcat(['ZandPCLandscape_sigma_', sigma_str, '_', add_fig_info]); 
    fig_fullpath = fullfile(fig_folder, fig_name);

    % Export figure
    for nFigExt = 1:length(Params.figExt)
        saveas(gcf,strcat([fig_fullpath, Params.figExt{nFigExt}]));
    end 

    close gcf 

    % Find basins of attraction for given 'DensityLandcape' matrix
    findBasinsOfAttraction(DensityLandcape, gridx1, PCmin, PCmax, ...
        sigma, Params, fig_folder, add_fig_info);


    % TODO: work on putting everything in one figure handle
    % if ~isfield(Params, 'oneFigure')
    %     close all
    % else 
    %     set(0, 'CurrentFigure', Params.oneFigure);
    %     clf reset
    % end 

end

% Assign boundaries
hubBoundaryWMdDeg = z_boundary;
periPartCoef = non_hub_pc_boundaries(1); % boundary that separates peripheral node and none-hub connector 
nonHubconnectorPartCoef = non_hub_pc_boundaries(2); % boundary that separates non-hub connector and non-hub kinless node 

proHubpartCoef = hub_pc_boundaries(1); % boundary that separates provincial hub and connector hub (default: 0.3)
connectorHubPartCoef = hub_pc_boundaries(2);  % boundary that separates connector hub and kinless hub 


end
