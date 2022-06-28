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