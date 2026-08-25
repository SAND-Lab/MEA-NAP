%% DEMOPLOTTING - demonstrates plotting capabilities
% The ploting function plplottool can be used to produce histograms of
% continuous and discrete data on log-log axes. It can also be used to
% overlay multiple data sets and to plot fits. Finally, it outputs the
% plotted data for other applications. This demo produces multiple data 
% sets and uses plplottool to plot the results.
%
% Other m-files required: PLPLOTTOOL, RLDECODE, PLDIST
% Subfunctions: PLPLOT, PLDIST
% MAT-files required: none
%
% See also: PLPLOT

% Author: Najja Marshall and Nick Timme
% Email: njm2149@columbia.edu and nicholas.m.timme@gmail.com
% July 2014; Last revision: 13-April-2016

%==============================================================================
% Copyright (c) 2014, The Trustees of Indiana University
% All rights reserved.
% 
% Redistribution and use in source and binary forms, with or without
% modification, are permitted provided that the following conditions are met:
% 
%   1. Redistributions of source code must retain the above copyright notice,
%      this list of conditions and the following disclaimer.
% 
%   2. Redistributions in binary form must reproduce the above copyright notice,
%      this list of conditions and the following disclaimer in the documentation
%      and/or other materials provided with the distribution.
% 
%   3. Neither the name of Indiana University nor the names of its contributors
%      may be used to endorse or promote products derived from this software
%      without specific prior written permission.
% 
% THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
% AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
% IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
% ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
% LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
% CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
% SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
% INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
% CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
% ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
% POSSIBILITY OF SUCH DAMAGE.


%% Test 1
% Generate discrete power-law data, fit it, and plot

x = gendata(10000, {'powerlaw', 1.5});
tau = plmle(x);
fitParams = struct; fitParams.tau = tau;
plplottool(x,'fitParams',fitParams,'title','Test 1');
clear

%% Test 2
% Generate multiple discrete power-law data sets, fit them, and plot

x = cell([3,1]);
x{1} = gendata(10000, {'powerlaw', 1.2});
x{2} = gendata(10000, {'powerlaw', 1.5});
x{3} = gendata(10000, {'powerlaw', 1.8});
fitParams = struct;
fitParams.tau = zeros([3,1]);
fitParams.x2fit = zeros([3,1]);
for i = 1:3
    fitParams.tau(i) = plmle(x{i});
    fitParams.x2fit(i) = i;
end
plplottool(x,'fitParams',fitParams,'title','Test 2');
clear

%% Test 3
% Generate continuous power-law data, fit it, and plot

x = gendata(10000, {'powerlaw', 2},'continuous');
tau = plmle(x);
fitParams = struct; 
fitParams.tau = tau;
plplottool(x,'fitParams',fitParams,'title','Test 3');
clear

%% Test 4
% Generate doubly truncated discrete power-law data

xmin = 10;
xmax = 100;
x = gendata(100000, {'truncated_powerlaw', [1.5, 0.125, xmin, xmax]},'sup',1000);
tau = plmle(x,'xmin',xmin,'xmax',xmax);
fitParams = struct; 
fitParams.tau = tau;
fitParams.xmin = xmin;
fitParams.xmax = xmax;
plplottool(x,'fitParams',fitParams,'title','Test 4');
clear

%% Test 5
% Generate discrete power-law data and apply two fits

x = gendata(10000, {'powerlaw', 1.5});
fitParams = struct; 
fitParams.tau = zeros([2,1]);
fitParams.tau(1) = plmle(x,'xmin',1,'xmax',10);
fitParams.tau(2) = plmle(x,'xmin',20,'xmax',90);
fitParams.xmin = [1;20];
fitParams.xmax = [10;90];
plplottool(x,'fitParams',fitParams,'title','Test 5');
clear

%% Test 6
% Generate discrete power-law data and play with plot appearance features

x = gendata(10000, {'powerlaw', 1.5});
fitParams = struct; 
fitParams.tau = plmle(x,'xmin',5,'xmax',90);
fitParams.xmin = 5;
fitParams.xmax = 90;
fitParams.dot = 'on';
fitParams.dotsize = 3;
fitParams.color = [200/255,0,255/255];
fitParams.linewidth = 1;
fitParams.linestyle = ':';
plotParams = struct;
plotParams.linewidth = 2;
plotParams.dot = 'on';
plotParams.dotsize = 5;
plotParams.color = [0,125/255,255/255];
plplottool(x,'fitParams',fitParams,'plotParams',plotParams,'title','Test 6');

%% Test 7
% Use the same plot features as above, but use continuous data and decrease the bin density

x = gendata(10000, {'powerlaw', 2},'continuous');
fitParams.tau = plmle(x,'xmin',5,'xmax',90);
plplottool(x,'fitParams',fitParams,'plotParams',plotParams,'binDensity',10,'title','Test 7');
clear

%% Test 8
% Generate, plot, and fit continuous and discrete power-law data at the same time

x = cell([2,1]);
x{1} = gendata(10000, {'powerlaw', 2});
x{2} = gendata(10000, {'powerlaw', 2},'continuous');
fitParams = struct;
fitParams.tau = zeros([2,1]);
fitParams.tau(1) = plmle(x{1});
fitParams.tau(2) = plmle(x{2});
fitParams.x2fit = [1;2];
plplottool(x,'fitParams',fitParams,'title','Test 8');
clear

%% Test 9
% Generate different types of data, use plplottool to reorganize the data,
% suppress immediate plotting, and make a hot pdf to show at group meeting
% or to your significant other

x = cell([4,1]);
x{1} = gendata(10000, {'powerlaw', 2});
x{2} = gendata(10000, {'powerlaw', 2},'continuous');
x{3} = gendata(10000, {'exponential', 0.125});
x{4} = gendata(10000, {'exponential', 0.125},'continuous');
fitParams = struct;
fitParams.tau = zeros([4,1]);
for i = 1:4
    fitParams.tau(i) = plmle(x{i});
end
fitParams.x2fit = [1;2;3;4];
plotdata = plplottool(x,'fitParams',fitParams,'plot','off');

% Set parameters
lmargin = 0.5; % Left Margin
rmargin = 0.1; % Right Margin
tmargin = 0.35; % Top Margin
bmargin = 0.5; % Bottom Margin
hspace = 0.5; % Horizontal Space Between Plots
vspace = 0.6; % Vertical Space Between Plots
papersize = [6,5]; % Papersize in inches

% Calculate plot features
width = (papersize(1) - hspace - lmargin - rmargin)/2;
height = (papersize(2) - vspace - tmargin - bmargin)/2;
leftcoord = [lmargin,lmargin,lmargin + width + hspace,lmargin + width + hspace];
bottomcoord = [bmargin + height + vspace,bmargin,bmargin + height + vspace,bmargin];

% Normalize
width = width/papersize(1);
height = height/papersize(2);
leftcoord = leftcoord./papersize(1);
bottomcoord = bottomcoord./papersize(2);

% Set the titles of the plots
plottitles = {'Discrete Power-Law Model','Continuous Power-Law Model','Discrete Exponential Model','Continuous Exponential Model'};

% Make the figure
F1 = figure('PaperPosition',[0 0 papersize],'PaperSize',papersize);
set(gcf, 'PaperUnits', 'inches');

for iPlot = 1:4
    f = subplot('Position',[leftcoord(iPlot),bottomcoord(iPlot),width,height]);
    hold on
    
    plot(plotdata.x{iPlot}(1,:),plotdata.x{iPlot}(2,:),'k','LineWidth',1)
    plot(plotdata.fit{iPlot}(1,:),plotdata.fit{iPlot}(2,:),'r--','LineWidth',1)
    
    legh = legend('Data',['PL Fit (tau = ',num2str(fitParams.tau(iPlot),3),')']);
    set(legh,'FontSize',8)
    
    set(gca,'FontSize',6)
    set(gca,'XScale','log')
    set(gca,'YScale','log')
    xlabel('x','FontSize',8)
    ylabel('p(x)','FontSize',8)
    title(plottitles{iPlot},'FontSize',10)
end

% Print the figure
print(F1,'-dpdf','-painters','demoplottingexample')

