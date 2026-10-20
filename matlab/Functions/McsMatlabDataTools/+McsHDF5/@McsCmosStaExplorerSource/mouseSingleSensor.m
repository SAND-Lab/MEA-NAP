function mouseSingleSensor(src, evt)
% function mouseHandlerVideo(src, evt)
%
% Is triggered when the mouse is clicked in a Single Unit figure. Reads
% the subplot clicked. On clicking the video, it is played or paused. On
% clicking the Single unit plot, the current frame is moved to the clicked
% x-position

    if strcmp(get(src, 'SelectionType'), 'normal')
        subplts = get(src,'Children');
        curAX = get(src,'CurrentAxes');
        if curAX == findobj(subplts,'Tag','neighborhood') %Neighborhood is clicked
        elseif curAX == findobj(subplts,'Tag','video') %Video is clicked
            data = guidata(src);
            if data.video.playing
                data.video.pauseVideo();
            else
                data.video.playVideo();
            end
        elseif curAX == findobj(subplts,'Tag','singleUnitPlot')
            pt = get(gca,'CurrentPoint');
            data = guidata(src);
            videoLength = size(data.video.imageCube,3);

            x = pt(1,1) - 0.5;
            x = min(x, videoLength);
            x = max(1,x);
            x = round(x);
            if data.video.playing
                data.video.pauseVideo();
            end
            data = guidata(src);
            data.video.curFrame = x;
            
            %prepare data
            imageStack  = data.video.imageCube;
            imageStack  = num2cell(imageStack,[1 2]);
            
            set(data.video.framehandle, 'CData', imageStack{data.video.curFrame});
            set(data.video.linehandle, 'XData', [data.video.curFrame-1 data.video.curFrame-1]);
            drawnow
            
            data.video.curFrame = data.video.curFrame + 1 ;
            
            guidata(src,data);
        end
    end
end

