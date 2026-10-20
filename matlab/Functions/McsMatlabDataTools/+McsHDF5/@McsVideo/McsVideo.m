classdef McsVideo < handle
    %UNTITLED Summary of this class goes here
    %   Detailed explanation goes here
    
    properties %(Access = private)
        playing = 0;
        environment     = [];
        imageCube       = [];
        framerate       = [];
        curFrame        = 1;
        framehandle     = [];
        linehandle      = [];
    end
    
    methods 
        function vid = McsVideo(fig, images, linehandle, varargin)
            % Construct an instance of class McsVideo
            vid.environment     = fig;
            vid.imageCube       = images;
            vid.framerate       = 25;
            %scale Images
            maxValue         	= max(max(max(abs(images))));
            images              = images/maxValue;
            minValue          	= min(min(min(images)));
            images              = images-minValue;
            maxValue         	= max(max(max(abs(images))));
            images              = images/maxValue;
            vid.imageCube       = images;
            vid.linehandle      = linehandle;
        end
        
        function playVideo( vid )
            %fetch data
            data                        = guidata(vid.environment);
            vid                         = data.video;

            %prepare data
            imageStack                  = vid.imageCube;
            imageStack  = num2cell(imageStack,[1 2]);
            %Prepare figure
            figure(vid.environment);
            
            %play video
            vid.playing = 1;
            
            %save state playing
            data.video  = vid;
            guidata(vid.environment,data)
            %

            while(vid.playing && gcf == vid.environment)
                for frame=vid.curFrame:size(imageStack,3)
                    if gcf ~= vid.environment %&& gca~=AX_Video
                        break
                    end
                    
                    %show Video
                    set(0,'CurrentFigure',vid.environment) %not the optimal solution: multithreading would be better
                    
                    % update video frame
                    set(vid.framehandle, 'CData', imageStack{frame});
                    % update position of the vertical line
                    set(vid.linehandle,'XData',[frame-1 frame-1]);
                    % draw the updates and process callbacks
                    drawnow
                    pause(1/vid.framerate);
                    
                    %handle interruption
                    if ishghandle(vid.environment,'figure')
                        data = guidata(vid.environment);
                    else
                        break
                    end
                    if data.video.playing == 0
                        data.video.curFrame = frame;
                        guidata(data.video.environment,data);
                        break
                    end
                    guidata(data.video.environment,data);
                end
                %handle interruption
                if ishghandle(vid.environment,'figure')
                    data = guidata(vid.environment);
                else
                    break
                end
                if data.video.playing == 0
                    break
                end
                
                vid.curFrame = 1;
            end
        end
        
        function pauseVideo( vid )
            data = guidata(vid.environment);
            data.video.playing = 0;
            guidata(vid.environment,data);
        end
        
        function [ vid , success ] = loadVideo( vid , AX )
            success        	= 0;
            colormap(AX,gray);
            if exist('imshow')
                vid.framehandle = imshow(vid.imageCube(:,:,1),'Parent',AX);
            else
                vid.framehandle = imagesc(vid.imageCube(:,:,1),[0 1]);
                set(vid.framehandle,'Parent',AX);
            end
            set(vid.framehandle,'Interruptible','on');
            vid.curFrame    = 2;
            if ishghandle(vid.framehandle)
                success         = 1;
            end
        end
    end
    
    methods (Access = private)
    end
end