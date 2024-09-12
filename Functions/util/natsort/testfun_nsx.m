function chk = testfun_nsx(fnh)
% Test function for ARBSORT, NATSORT, NATSORTFILES, and NATSORTROWS. Do not call!
%
% (c) 2012-2024 Stephen Cobeldick
%
% See also ARBSORT_TEST NATSORT_TEST NATSORTFILES_TEST NATSORTROWS_TEST

chk = @nestfun;
wrn = warning('off','SC:natsort:rgx:SanityCheck');
cnt = 0;
itr = 0;
if feature('hotlinks')
	fmt = '<a href="matlab:opentoline(''%1$s'',%2$d)">%1$s|%2$d:</a>';
else
	fmt = '%s|%3d:';
end
%
	function nestfun(varargin)
		% (in1, in2, in3, ..., fnh, out1, out2, out3, ...)
		%
		dbs = dbstack();
		%
		if ~nargin % post-processing
			fprintf(fmt, dbs(2).file, dbs(2).line);
			fprintf(' %d of %d testcases failed.\n',cnt,itr)
			warning(wrn);
			return
		end
		%
		idx = find(cellfun(@(f)isequal(f,fnh),varargin));
		assert(nnz(idx)==1,'Missing/duplicated function handle.')
		xpC = varargin(idx+1:end);
		opC =  cell(size(xpC));
		boo = false(size(xpC));
		%
		[opC{:}] = fnh(varargin{1:idx-1});
		%
		for k = 1:numel(xpC)
			opA = opC{k};
			xpA = xpC{k};
			if isequal(xpA,@i)
				% ignore this output
			elseif ~isequal(class(opA),class(xpA))
				boo(k) = true;
				opT = class(opA);
				xpT = class(xpA);
			elseif ~isequalwithequalnans(opA,xpA) %#ok<DISEQN>
				boo(k) = true;
				if isa(xpA,'table')
					opV = opA.Properties.VariableNames;
					xpV = xpA.Properties.VariableNames;
					if isequal(opV,xpV)
						[~,opX] = ismember(opA,xpA,'rows');
						[~,xpX] = ismember(xpA,opA,'rows');
						opY = 1:size(opA,1);
						xpY = 1:size(xpA,1);
						opT = ['RowIndices:',tfPretty(xpX),tfPretty(opY(:))];
						xpT = ['RowIndices:',tfPretty(xpY(:)),tfPretty(opX)];
					else % different variables
						boo(k) = true;
						opT = ['VariableNames:',tfPretty(opV)];
						xpT = ['VariableNames:',tfPretty(xpV)];
					end
				else % string, cell of char, char, numeric, struct
					opT = tfPretty(opA);
					xpT = tfPretty(xpA);
				end
			end
			if boo(k)
				dmn = min(numel(opT),numel(xpT));
				dmx = max(numel(opT),numel(xpT));
				dtx = repmat('^',1,dmx);
				dtx(opT(1:dmn)==xpT(1:dmn)) = ' ';
				%
				fprintf(fmt, dbs(2).file, dbs(2).line);
				fprintf(' (output #%d)\n',k);
				fprintf('actual: %s\n',opT);
				fprintf('expect: %s\n',xpT);
				fprintf('diff:   ')
				fprintf(2,'%s\n',dtx); % red!
			end
		end
		cnt = cnt+any(boo);
		itr = itr+1;
	end
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%testfun_nsx
function out = tfPretty(inp)
if isempty(inp)|| ndims(inp)>2 %#ok<ISMAT>
	out = sprintf('x%u',size(inp));
	out = sprintf('%s %s',out(2:end),class(inp));
elseif isnumeric(inp) || islogical(inp)
	out = regexprep(mat2str(inp,23),'\s+',',');
elseif ischar(inp)
	out = mat2str(inp);
elseif isa(inp,'string')
	if isscalar(inp)
		out = sprintf('"%s"',inp);
	else
		fmt = repmat(',"%s"',1,size(inp,2));
		out = sprintf([';',fmt(2:end)],inp.');
		out = sprintf('[%s]',out(2:end));
	end
elseif iscell(inp)
	tmp = cellfun(@tfPretty,inp.','uni',0);
	fmt = repmat(',%s',1,size(inp,2));
	out = sprintf([';',fmt(2:end)],tmp{:});
	out = sprintf('{%s}',out(2:end));
elseif isstruct(inp) % assume DIR output structure.
	tmp = inp.';
	fmt = repmat(',''%s''',1,size(inp,2));
	out = sprintf([';',fmt(2:end)],tmp.name);
	out = sprintf('<name:%s>',out(2:end));
else
	error('Class "%s" is not supported.',class(inp))
end
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%tfPretty