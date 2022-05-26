%% TrialLandscapeDensity.m 
%{
This script calculates and plots the distribution 
of Within-module Z-score (Z) and participation coefficient (PC)
for each electrode across recordings.

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
    % TODO: suppress figure handle popping up when loading
    load(FN)
    
    for i = 1:length(Var)
        VN = cell2mat(Var(i));
        VNs = strcat('NetMet.adjM15mslag.',VN);
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


%% find basins of attraction
function findBasinsOfAttraction(DensityLandcape, gridx1, PCmin, PCmax, sigma, Params, fig_folder, add_fig_info)

    % DL1_Zmin = 0.55;  % got these from gridx1(70) using original spacing
    % DL1_Zmax = -1.45; % got these from gridx1(110) using original spacing
    DL1_Zmin = 4;
    DL1_Zmax = -2;
    [~, DL1_index_start] = min(abs(gridx1 - DL1_Zmin));
    [~, DL1_index_end] = min(abs(gridx1 - DL1_Zmax));
    
    DL2_Zmin = 3.05; %  got these from gridx1(20) using original spacing
    DL2_Zmax = 0.55; % got these from gridx1(70) using original spacing
    [~, DL2_index_start] = min(abs(gridx1 - DL2_Zmin));
    [~, DL2_index_end] = min(abs(gridx1 - DL2_Zmax));
    
    % What is 70 to 110???
    DL1 = DensityLandcape(DL1_index_start:DL1_index_end, :);
    DL1 = DL1*-1;
    
    L1 = watershed(DL1);
    % Lrgb = label2rgb(L1);
    % imshow(Lrgb)
    p = [20 100 600 600];
    set(0, 'DefaultFigurePosition', p)
    figure()
    imagesc([PCmin, PCmax], [DL1_Zmin, DL1_Zmax], L1)
    set(gca,'YDir','normal');
    xlabel('Participation Coefficient (PC)')
    ylabel('Within-module Z-score (Z)')
    set(gcf, 'color', 'white')
    sigma_str = strrep(num2str(sigma), '.', 'p');
    fig_name = strcat(['ZandPCLandscape_WaterShedGroup1_sigma_', sigma_str, '_', add_fig_info]); 
    fig_fullpath = fullfile(fig_folder, fig_name);

    % Export figure
    for nFigExt = 1:length(Params.figExt)
        saveas(gcf,strcat([fig_fullpath, Params.figExt{nFigExt}]));
    end 

    close(gcf)
    
    DL2 = DensityLandcape(DL2_index_start:DL2_index_end,:);
    DL2 = DL2*-1;
    
    L2 = watershed(DL2);
    % Lrgb = label2rgb(L1);
    % imshow(Lrgb)
    p = [20 100 600 600];
    set(0, 'DefaultFigurePosition', p)
    figure()
    imagesc([PCmin, PCmax], [DL2_Zmin, DL2_Zmax], L2)
    set(gca,'YDir','normal');
    xlabel('Participation Coefficient (PC)')
    ylabel('Within-module Z-score (Z)')
    
    set(gcf, 'color', 'white')
    fig_name = strcat(['ZandPCLandscape_WaterShedGroup2_sigma_', sigma_str, '_', add_fig_info]); 
    fig_fullpath = fullfile(fig_folder, fig_name);

    % Export figure
    for nFigExt = 1:length(Params.figExt)
        saveas(gcf,strcat([fig_fullpath, Params.figExt{nFigExt}]));
    end 

    close(gcf)

    % Plot the watershed on the whole thing 
    Zmin = -2;
    Zmax = 4;
    DL3 = DensityLandcape;
    DL3 = DL3*-1;
    
    L3 = watershed(DL3);
    % Lrgb = label2rgb(L1);
    % imshow(Lrgb)
    p = [20 100 600 600];
    set(0, 'DefaultFigurePosition', p)
    figure()
    imagesc([PCmin, PCmax], [Zmin, Zmax], L3)
    set(gca,'YDir','normal');
    xlabel('Participation Coefficient (PC)')
    ylabel('Within-module Z-score (Z)')
    
    set(gcf, 'color', 'white')
    fig_name = strcat(['ZandPCLandscape_WaterShed_sigma_', sigma_str, '_', add_fig_info]); 
    fig_fullpath = fullfile(fig_folder, fig_name);

    
    % Export figure
    for nFigExt = 1:length(Params.figExt)
        saveas(gcf,strcat([fig_fullpath, Params.figExt{nFigExt}]));
    end 

    close(gcf)

   
end 

%%

% [N,C] = hist3(X,'Nbins',[100 100]);
% 
% 
% 
% if ~isempty(find(strcmpi(varargin,'edges'), 1))
%   %Put values on the upper edges as if they were in the last
%   %bin
%   N(:,end-1)=N(:,end-1)+N(:,end);
%   N(end-1,:)=N(end-1,:)+N(end,:);
%   %Remove upper edge
%   N(:,end)=[];
%   N(end,:)=[];
%   C{1}(end) = [];
%   C{2}(end) = [];
% end
% %Get polygon half widths
% wx=C{1}(:);
% wy=C{2}(:);
% % display
% figure
% H = pcolor(wx, wy, N');
% box on
% shading interp
% set(H,'edgecolor','none');
% colorbar
% colormap jet
% 
% 
% 
% xlim([0 1])

