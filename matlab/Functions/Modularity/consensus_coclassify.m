function [D] = consensus_coclassify(input_cell)
% H Smith, Cambridge, 2020
% Calculate consensus matrix for a series of community partitions
% For an nodes i and j, calculates the proportion of times that i and j are
% in the same modularity group in repeated grouping

% INPUTS:
%   input_cell = cell containing n vectors size node_number x 1 of community 
%       partitions (modularity groups)

% OUTPUTS:
%   D = consensus matrix where element Dij represents proportion of
%       input_cell where input_cell(i) == input_cell(j)

repNum = length(input_cell); % Number of repeats of community partition
node_num = length(input_cell{1}); % Number of nodes in community
D = zeros(node_num,node_num);

for i = 1:node_num
    for j = 1:node_num
        counter = 0;
        for k = 1:repNum
            if input_cell{k}(i) == input_cell{k}(j)
                counter = counter + 1;
            end
        end
        prop = counter / repNum;
        D(i,j) = prop;
    end
end

end