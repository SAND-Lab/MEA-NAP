% Like questdlg() but this one lets you specify the font size so that it's bigger and easier to see.
%
% Sample calls
% promptMessage = sprintf('Do you want to Continue processing,\nor Quit processing?');
% dialogTitleString = 'Continue?';
% No font size specified.  Use default of 16.
% buttonText = questdlg(promptMessage, dialogTitleString, choice1, choice2, opts);
% buttonText = questdlg(promptMessage, dialogTitleString, choice1, choice2, choice2, opts); % Have default be choice2.
% buttonText = questdlg(promptMessage, dialogTitleString, choice1, choice2, choice3, opts); % Three distinct choices.
% A font size was specified.
% buttonText = questdlg(promptMessage, dialogTitleString, choice1, choice2, opts, 17);
% buttonText = questdlg(promptMessage, dialogTitleString, choice1, choice2, choice3, opts, 17); % Three distinct choices.
%
% For example, to check on which button they clicked on, use contains to see if it contains a unique word from one of your choices.
% if contains(buttonText, 'Quit', 'IgnoreCase', true)
% 	return; % or break or continue.
% end

function buttonText = questdlgbig(varargin)
try
	buttonText = ''; % Initialize.
% 	nargin
% 	celldisp(varargin)
	if nargin < 5
		celldisp(varargin)
		uiwait(errordlg('Not enough input arguments to questdlgbig.'));
		return;
	end

	% See if any of the inputs is a number.  If so, consider it to be the font size.
	fontSize = 16; % Initialize
	inputArguments = varargin'; % Initialize.
	for k = 1 : nargin
		if isnumeric(inputArguments{k})
			% It's a number.
			fontSize = inputArguments{k};
			% Remove that cell
			inputArguments(k) = [];
			break;
		end
	end

	% Parse the arguments
	promptMessage = inputArguments{1};
	dialogTitleString = inputArguments{2};
	choice1 = inputArguments{3};
	choice2 = inputArguments{4};
	choice3 = [];
	numInputs = numel(inputArguments);

	% Determine if it's a 2 choice or 3 choice situation.
	% Note: if the call is like this:
	% 	buttonText = questdlg(promptMessage, dialogTitleString, choice1, choice2, choice3, fontSize);
	% Then if choice3 is equal to choice1 or choice2, then it's a two-choice situation
	% and choice3 would be the default choice and should equal either choice1 or choice2.
	% If choice2 does not equal either choice1 or choice2, then it's a 3 choice situation.
	% That's just the way questdlg operates.
	if numInputs >= 5
		% Potentially three choices.  Can't specify default button in arg list but you can as part of opts.
		choice3 = inputArguments{5};
		if strcmp(choice3, choice1)
			% Choice3 matched choice2.
			% So this is a "Two choices" situation.  Can specify default button.
			choice3 = [];
			opts.Default = choice1; % The third input is the default and should be either choice1 or choice2.
		elseif strcmp(choice3, choice2)
			% Choice3 matched choice2.
			% So this is a "Two choices" situation.  Can specify default button.
			choice3 = [];
			opts.Default = choice2; % The third input is the default and should be either choice1 or choice2.
		else
			% Three choice situation.
			% strangely enough with 3 choices, you cannot specify the default button 
			% yet you must still have a "Default" field for opts.
			opts.Default = choice1; % Just say the default is choice1.
		end
	else
		% Two choices but they forgot to specify a default.
		opts.Default = choice1; % Just say the default is choice1.
	end

	% If there is a backslash in the string (like from a folder), then it needs to be replaced by double backslashes.
	promptMessage = strrep(promptMessage, '\', '\\');
	% Replace underlines with \_ so the next character won't be a subscript.
	promptMessage = strrep(promptMessage, '_', '\_');
	
	opts.Interpreter = 'tex';
	opts.WindowStyle = 'modal';
	
	% Embed the required tex code in before the string.
	latexMessage = sprintf('\\fontsize{%d}%s', fontSize, promptMessage);
	if isempty(choice3)
		% Two choices.
		buttonText = questdlg(latexMessage, dialogTitleString, choice1, choice2, opts);
	else
		% Three choices.
		% With 3 choices, you can either specify a default option, or opts (font size) but NOT BOTH.
		% Here we go with the opts.
		buttonText = questdlg(latexMessage, dialogTitleString, choice1, choice2, choice3, opts);
	end
catch ME
	errorMessage = sprintf('Error in questdlgbig():\n%s', ME.message);
	fprintf('%s\n', errorMessage);
	uiwait(warndlg(errorMessage));
end
return; % from questdlgbig()