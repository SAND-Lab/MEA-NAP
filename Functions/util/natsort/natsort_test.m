function natsort_test()
% Test function for NATSORT.
%
% (c) 2012-2024 Stephen Cobeldick
%
% See also NATSORT TESTFUN_NSX ARBSORT_TEST NATSORTFILES_TEST NATSORTROWS_TEST

fnh = @natsort;
chk = testfun_nsx(fnh);
%
try categorical(0); isc=true; catch; isc=false; warning('No categorical class.'), end %#ok<CTCH,WNTAG>
try sum(uint64(0)); isl=true; catch; isl=false; warning('No (u)int64 class.'), end %#ok<CTCH,WNTAG>
try pad(strings()); iss=true; catch; iss=false; warning('No string class.'), end %#ok<CTCH,WNTAG>
try arbsort({'X'}); isa=true; catch; isa=false; warning('No ARBSORT found.'), end %#ok<CTCH,WNTAG>
%
if iss
	txf = @string;
else
	txf = @cellstr;
end
%
%% Mfile Examples %%
%
A =         txf({'x2','x10','x1'});
chk(A, fnh, txf({'x1','x2','x10'}))
chk(A, fnh,                     @i,      @i, {'x',2;'x',10;'x',1})
chk(A, fnh, txf({'x1','x2','x10'}),      @i, {'x',2;'x',10;'x',1}) % not in Mfile
chk(A, fnh, txf({'x1','x2','x10'}), [3,1,2], {'x',2;'x',10;'x',1}) % not in Mfile
chk(A, fnh, txf({'x1','x2','x10'}), [3,1,2]) % not in Mfile
%
chk({'v10.6','v9.10','v9.5','v10.10','v9.10.20','v9.10.8'}, fnh,... Aa
	{'v9.5','v9.10','v9.10.8','v9.10.20','v10.6','v10.10'}, [3,2,6,5,1,4])
chk({'test+NaN','test11.5','test-1.4','test','test-Inf','test+0.3'}, '(+|-)?(Inf|\d+\.?\d*)', fnh,... Ab
	{'test','test-Inf','test-1.4','test+0.3','test11.5','test+NaN'}, [4,5,3,6,2,1])
chk({'0.56e007','','43E-2','10000','9.8'}, '\d+\.?\d*(E(+|-)?\d+)?', fnh,... Ac
	{'','43E-2','9.8','10000','0.56e007'}, [2,3,5,4,1])
chk({'a0X7C4z','a0X5z','a0X18z','a0XFz'}, '0X[0-9A-F]+', '%i', fnh,... Ad
	{'a0X5z','a0XFz','a0X18z','a0X7C4z'}, [2,4,3,1])
chk({'a11111000100z','a101z','a000000000011000z','a1111z'}, '[01]+', '%b', fnh,... Ae
	{'a101z','a1111z','a000000000011000z','a11111000100z'}, [2,4,3,1])
%
Af =                           {'a2','A20','A1','a10','A2','a1'};
chk(Af, [], 'ignorecase', fnh, {'A1','a1','a2','A2','a10','A20'}, [3,6,1,5,4,2]) % default
chk(Af, [], 'matchcase',  fnh, {'A1','A2','A20','a1','a2','a10'}, [3,5,2,6,1,4])
%
Ag =                         {'2','a','','3','B','1'};
chk(Ag, [],   'ascend', fnh, {'','1','2','3','a','B'}, [3,6,1,4,2,5]) % default
chk(Ag, [],  'descend', fnh, {'B','a','3','2','1',''}, [5,2,4,1,6,3])
chk(Ag, [], 'num<char', fnh, {'','1','2','3','a','B'}, [3,6,1,4,2,5]) % default
chk(Ag, [], 'char<num', fnh, {'','a','B','1','2','3'}, [3,2,5,6,1,4])
%
if isl
	chk({'a18446744073709551615z','a18446744073709551614z'}, [], '%lu', fnh,...
		{'a18446744073709551614z','a18446744073709551615z'}, [2,1])
end
%
%% HTML Examples %%
%
Aa =         txf({'a2','a10','a1'});
chk(Aa, fnh, txf({'a1','a2','a10'}))
chk(Aa, fnh, txf({'a1','a2','a10'}), [3,1,2]) % not in HTML
%
Ab =         txf({'ver9.10','ver9.5','ver9.2','ver9.10.20','ver9.10.8'});
chk(Ab, fnh, txf({'ver9.2','ver9.5','ver9.10','ver9.10.8','ver9.10.20'}))
chk(Ab, fnh, txf({'ver9.2','ver9.5','ver9.10','ver9.10.8','ver9.10.20'}), [3,2,1,5,4]) % not in HTML
%
if isc
	chk(categorical({'a2','a10','a1'}), fnh,... Ac
		categorical({'a1','a2','a10'}));
end
%
Ad =         {'1.3','1.10','1.2'};
chk(Ad, fnh, {'1.2','1.3','1.10'})
chk(Ad, fnh, {'1.2','1.3','1.10'}, [3,1,2]) % not in HTML
chk(Ad, '\d\.?\d*', fnh, {'1.10','1.2','1.3'})
chk(Ad, '\d\.?\d*', fnh, {'1.10','1.2','1.3'}, [2,3,1]) % not in HTML
%
Ae =                           {'a2','A20','A1','a','A','a10','A2','a1'};
chk(Ae, [], 'ignorecase', fnh, {'a','A','A1','a1','a2','A2','a10','A20'})
chk(Ae, [], 'ignorecase', fnh, {'a','A','A1','a1','a2','A2','a10','A20'}, [4,5,3,8,1,7,6,2]) % not in HTML
chk(Ae, [],  'matchcase', fnh, {'A','A1','A2','A20','a','a1','a2','a10'})
chk(Ae, [],  'matchcase', fnh, {'A','A1','A2','A20','a','a1','a2','a10'}, [5,3,7,2,4,8,1,6]) % not in HTML
%
Af =                         {'2','a','','10','B','1'};
chk(Af, [],   'ascend', fnh, {'','1','2','10','a','B'}, [3,6,1,4,2,5]) % index not in HTML
chk(Af, [],  'descend', fnh, {'B','a','10','2','1',''}, [5,2,4,1,6,3]) % index not in HTML
chk(Af, [], 'num<char', fnh, {'','1','2','10','a','B'}, [3,6,1,4,2,5]) % index not in HTML
chk(Af, [], 'char<num', fnh, {'','a','B','1','2','10'}, [3,2,5,6,1,4]) % index not in HTML
%
Ag =                               {'10','1','NaN','2'};
chk(Ag, 'NaN|\d+', 'num<NaN', fnh, {'1','2','10','NaN'}, [2,4,1,3]) % index not in HTML
chk(Ag, 'NaN|\d+', 'NaN<num', fnh, {'NaN','1','2','10'}, [3,2,4,1]) % index not in HTML
%
if isl
	Ah =                    {'18446744073709551614','18446744073709551615','18446744073709551613'};
	chk(Ah, [], '%lu', fnh, {'18446744073709551613','18446744073709551614','18446744073709551615'})
	chk(Ah, [], '%lu', fnh, {'18446744073709551613','18446744073709551614','18446744073709551615'}, [3,1,2]) % not in HTML
end
%
if isa
	Ap = txf({'ña_2', 'ño', 'os', 'ña_10', 'ni', 'ña_1'});
	alfabeto = num2cell(['A':'N','Ñ','O':'Z']); % Spanish alphabet
	chk(Ap, [], @(t)arbsort(t,alfabeto), fnh,...
		txf({'ni', 'ña_1', 'ña_2', 'ña_10', 'ño', 'os'}))
end
%
Ak =         {'abc2xyz','abc10xyz','abc2xyz','abc1xyz'};
chk(Ak, fnh, {'abc1xyz','abc2xyz','abc2xyz','abc10xyz'}) % not in HTML
chk(Ak, fnh, {'abc1xyz','abc2xyz','abc2xyz','abc10xyz'}, [4,1,3,2])
chk(Ak, fnh, {'abc1xyz','abc2xyz','abc2xyz','abc10xyz'}, [4,1,3,2], ...
	{'abc',2,'xyz';'abc',10,'xyz';'abc',2,'xyz';'abc',1,'xyz'}) % not in HTML
chk(Ak, fnh, @i, @i, ...
	{'abc',2,'xyz';'abc',10,'xyz';'abc',2,'xyz';'abc',1,'xyz'})
%
chk({'x+NaN','x11.5','x-1.4','x','x-Inf','x+0.3'}, '(+|-)?(NaN|Inf|\d+\.?\d*)', fnh,... Al
	{'x','x-Inf','x-1.4','x+0.3','x11.5','x+NaN'}, [4,5,3,6,2,1]) % index not in HTML
chk({'0.56e007','','43E-2','10000','9.8'}, '(+|-)?\d+\.?\d*([eE](+|-)?\d+)?', fnh,... Am
	{'','43E-2','9.8','10000','0.56e007'}, [2,3,5,4,1]) % index not in HTML
chk({'a0X7C4z','a0X5z','a0X18z','a0XFz'}, '0X[0-9A-F]+', '%x', fnh,... An
	{'a0X5z','a0XFz','a0X18z','a0X7C4z'}, [2,4,3,1]) % index not in HTML
chk({'a11111000100z','a101z','a000000000011000z','a1111z'}, '[01]+', '%b', fnh,... Ao
	{'a101z','a1111z','a000000000011000z','a11111000100z'}, [2,4,3,1]) % index not in HTML
%
Ap =                      [' 9';'23';'10';' 0';'5 '];
chk(Ap,              fnh, ['5 ';'10';'23';' 0';' 9'])
chk(Ap, '\s*\d+\s*', fnh, [' 0';'5 ';' 9';'10';'23'])
%
As =                     txf({'1,3', '1,10', '1,2'});
chk(As, '\d+,?\d*', fnh, txf({'1,10', '1,2', '1,3'}))
chk(As, '\d+,?\d*', fnh, txf({'1,10', '1,2', '1,3'}),[2,3,1]) % not in HTML
%
%% Number Substring Table %%
%
% unsigned integer:
chk({'0','123','4','56789'}, '\d+', '%f', fnh, {'0','4','123','56789'}, [1,3,2,4], {0;123;4;56789})
chk({'0','123','4','56789'}, '\d+', '%i', fnh, {'0','4','123','56789'}, [1,3,2,4], {0;123;4;56789})
chk({'0','123','4','56789'}, '\d+', '%u', fnh, {'0','4','123','56789'}, [1,3,2,4], {0;123;4;56789})
chk({'0','123','4','56789'}, '\d+', '%lu', fnh, {'0','4','123','56789'}, [1,3,2,4], {0;123;4;56789})
% signed integer:
chk({'+1','23','-45','678'}, '(+|-)?\d+', '%f', fnh, {'-45','+1','23','678'}, [3,1,2,4], {1;23;-45;678})
chk({'+1','23','-45','678'}, '(+|-)?\d+', '%i', fnh, {'-45','+1','23','678'}, [3,1,2,4], {1;23;-45;678})
chk({'+1','23','-45','678'}, '(+|-)?\d+', '%d', fnh, {'-45','+1','23','678'}, [3,1,2,4], {1;23;-45;678})
chk({'+1','23','-45','678'}, '(+|-)?\d+', '%ld', fnh, {'-45','+1','23','678'}, [3,1,2,4], {1;23;-45;678})
% floating point:
chk({'012','3.45','678.9'}, '\d+\.?\d*', '%f', fnh, {'3.45','012','678.9'}, [2,1,3], {12;3.45;678.9})
chk({'123','4','NaN','Inf'}, '\d+|Inf|NaN', '%f', fnh, {'4','123','Inf','NaN'}, [2,1,4,3], {123;4;NaN;Inf})
chk({'0.123e4','5.67e08'}, '\d+\.\d+E\d+', fnh, {'0.123e4','5.67e08'}, [1,2], {0.123e4;5.67e08})
% octal:
chk({'012','03456','0700'}, '0[0-7]+', '%i', fnh, {'012','0700','03456'}, [1,3,2], {10;1838;448})
chk({'012','03456','0700'}, '0[0-7]+', '%o', fnh, {'012','0700','03456'}, [1,3,2], {10;1838;448})
chk({ '12', '3456', '700'},  '[0-7]+', '%o', fnh, { '12', '700', '3456'}, [1,3,2], {10;1838;448})
% hexadecimal:
chk({'0X0','0X3E7','0XFF'}, '0X[0-9A-F]+', '%i', fnh, {'0X0','0XFF','0X3E7'}, [1,3,2], {0;999;255})
chk({'0X0','0X3E7','0XFF'}, '0X[0-9A-F]+', '%x', fnh, {'0X0','0XFF','0X3E7'}, [1,3,2], {0;999;255})
chk({  '0',  '3E7',  'FF'},   '[0-9A-F]+', '%x', fnh, {  '0',  'FF',  '3E7'}, [1,3,2], {0;999;255})
% binary:
chk({'0B1','0B101','0B10'}, '0B[01]+', '%b', fnh, {'0B1','0B10','0B101'}, [1,3,2], {1;5;2})
chk({  '1',  '101',  '10'},   '[01]+', '%b', fnh, {  '1',  '10',  '101'}, [1,3,2], {1;5;2})
%
%% Numeric XOR Alphabetic %%
%
chk(   {}, fnh,    {},[])
chk( {''}, fnh,  {''}, 1)
chk({' '}, fnh, {' '}, 1)
chk({'x'}, fnh, {'x'}, 1)
chk({'y'}, fnh, {'y'}, 1)
chk({'z'}, fnh, {'z'}, 1)
chk({'0'}, fnh, {'0'}, 1)
chk({'1'}, fnh, {'1'}, 1)
chk({'2'}, fnh, {'2'}, 1)
chk({'3'}, fnh, {'3'}, 1)
chk({'4'}, fnh, {'4'}, 1)
chk({'5'}, fnh, {'5'}, 1)
chk({'6'}, fnh, {'6'}, 1)
chk({'7'}, fnh, {'7'}, 1)
chk({'8'}, fnh, {'8'}, 1)
chk({'9'}, fnh, {'9'}, 1)
%
C = {'BAA','AA','CA','B','A','C'};
chk(C, fnh,...
	{'A','AA','B','BAA','C','CA'}, [5,2,4,1,6,3], C(:))
%
C = {'100','00','20','1','0','2'};
chk(C, fnh, ...
	{'00','0','1','2','20','100'}, [2,5,4,6,3,1], num2cell(str2double(C(:))))
%
C = {'000000000','0','00000','00','000','00000000','0','0000','000000'};
chk(C, fnh, C, 1:numel(C), num2cell(zeros(numel(C),1)))
C = {'000000001','1','00001','01','001','00000001','1','0001','000001'};
chk(C, fnh, C, 1:numel(C), num2cell(ones(numel(C),1)))
C = {'000000001','2','00003','04','005','00000006','7','0008','000009'};
chk(C, fnh, C, 1:numel(C), num2cell((1:numel(C)).'))
C = {'NaN','NaN','NaN','NaN','NaN','NaN','NaN','NaN','NaN','NaN','NaN'};
chk(C, 'NaN|\d+', fnh, C, 1:numel(C), num2cell(nan(numel(C),1)))
C = {'+Inf','+Inf','+Inf','+Inf','+Inf','+Inf','+Inf','+Inf','+Inf'};
chk(C, '(+|-)?Inf|\d+', fnh, C, 1:numel(C), num2cell(+inf(numel(C),1)))
C = {'-Inf','-Inf','-Inf','-Inf','-Inf','-Inf','-Inf','-Inf','-Inf'};
chk(C, '(+|-)?Inf|\d+', fnh, C, 1:numel(C), num2cell(-inf(numel(C),1)))
%
%% Input Classes %%
%
if isc
	%
	X = [3;5;4;7;2;6;1];
	C = ['100  ';'20   ';'1    ';'9    ';'2    ';'90   ';'10   '];
	chk(C, fnh, ... char
		['1    ';'2    ';'9    ';'10   ';'20   ';'90   ';'100  '])
	C = categorical(cellstr(C));
	chk(C, fnh, C(X))
	%
end
%
%% 64 Bit Integers %%
%
if isl
	%
	u2c = @(m) arrayfun(@int2str,intmax('uint64')-uint64(m(:)-1),'uni',0);
	chk(u2c(magic(0)), [], '%lu', fnh, u2c(00:-1:1))
	chk(u2c(magic(1)), [], '%lu', fnh, u2c(01:-1:1))
	chk(u2c(magic(2)), [], '%lu', fnh, u2c(04:-1:1))
	chk(u2c(magic(3)), [], '%lu', fnh, u2c(09:-1:1))
	chk(u2c(magic(4)), [], '%lu', fnh, u2c(16:-1:1))
	chk(u2c(magic(5)), [], '%lu', fnh, u2c(25:-1:1))
	chk(u2c(magic(6)), [], '%lu', fnh, u2c(36:-1:1))
	chk(u2c(magic(7)), [], '%lu', fnh, u2c(49:-1:1))
	chk(u2c(magic(8)), [], '%lu', fnh, u2c(64:-1:1))
	chk(u2c(magic(9)), [], '%lu', fnh, u2c(81:-1:1))
	chk(u2c(magic(0)), [], '%lu',  'ascend', fnh, u2c(00:-1:1))
	chk(u2c(magic(1)), [], '%lu',  'ascend', fnh, u2c(01:-1:1))
	chk(u2c(magic(2)), [], '%lu',  'ascend', fnh, u2c(04:-1:1))
	chk(u2c(magic(3)), [], '%lu',  'ascend', fnh, u2c(09:-1:1))
	chk(u2c(magic(4)), [], '%lu',  'ascend', fnh, u2c(16:-1:1))
	chk(u2c(magic(5)), [], '%lu',  'ascend', fnh, u2c(25:-1:1))
	chk(u2c(magic(6)), [], '%lu',  'ascend', fnh, u2c(36:-1:1))
	chk(u2c(magic(7)), [], '%lu',  'ascend', fnh, u2c(49:-1:1))
	chk(u2c(magic(8)), [], '%lu',  'ascend', fnh, u2c(64:-1:1))
	chk(u2c(magic(9)), [], '%lu',  'ascend', fnh, u2c(81:-1:1))
	chk(u2c(magic(0)), [], '%lu', 'descend', fnh, u2c(1:+1:00))
	chk(u2c(magic(1)), [], '%lu', 'descend', fnh, u2c(1:+1:01))
	chk(u2c(magic(2)), [], '%lu', 'descend', fnh, u2c(1:+1:04))
	chk(u2c(magic(3)), [], '%lu', 'descend', fnh, u2c(1:+1:09))
	chk(u2c(magic(4)), [], '%lu', 'descend', fnh, u2c(1:+1:16))
	chk(u2c(magic(5)), [], '%lu', 'descend', fnh, u2c(1:+1:25))
	chk(u2c(magic(6)), [], '%lu', 'descend', fnh, u2c(1:+1:36))
	chk(u2c(magic(7)), [], '%lu', 'descend', fnh, u2c(1:+1:49))
	chk(u2c(magic(8)), [], '%lu', 'descend', fnh, u2c(1:+1:64))
	chk(u2c(magic(9)), [], '%lu', 'descend', fnh, u2c(1:+1:81))
	chk(u2c(magic(0)), [],  'ascend', '%lu', fnh, u2c(00:-1:1))
	chk(u2c(magic(1)), [],  'ascend', '%lu', fnh, u2c(01:-1:1))
	chk(u2c(magic(2)), [],  'ascend', '%lu', fnh, u2c(04:-1:1))
	chk(u2c(magic(3)), [],  'ascend', '%lu', fnh, u2c(09:-1:1))
	chk(u2c(magic(4)), [],  'ascend', '%lu', fnh, u2c(16:-1:1))
	chk(u2c(magic(5)), [],  'ascend', '%lu', fnh, u2c(25:-1:1))
	chk(u2c(magic(6)), [],  'ascend', '%lu', fnh, u2c(36:-1:1))
	chk(u2c(magic(7)), [],  'ascend', '%lu', fnh, u2c(49:-1:1))
	chk(u2c(magic(8)), [],  'ascend', '%lu', fnh, u2c(64:-1:1))
	chk(u2c(magic(9)), [],  'ascend', '%lu', fnh, u2c(81:-1:1))
	chk(u2c(magic(0)), [], 'descend', '%lu', fnh, u2c(1:+1:00))
	chk(u2c(magic(1)), [], 'descend', '%lu', fnh, u2c(1:+1:01))
	chk(u2c(magic(2)), [], 'descend', '%lu', fnh, u2c(1:+1:04))
	chk(u2c(magic(3)), [], 'descend', '%lu', fnh, u2c(1:+1:09))
	chk(u2c(magic(4)), [], 'descend', '%lu', fnh, u2c(1:+1:16))
	chk(u2c(magic(5)), [], 'descend', '%lu', fnh, u2c(1:+1:25))
	chk(u2c(magic(6)), [], 'descend', '%lu', fnh, u2c(1:+1:36))
	chk(u2c(magic(7)), [], 'descend', '%lu', fnh, u2c(1:+1:49))
	chk(u2c(magic(8)), [], 'descend', '%lu', fnh, u2c(1:+1:64))
	chk(u2c(magic(9)), [], 'descend', '%lu', fnh, u2c(1:+1:81))
	n2c = @(m) arrayfun(@int2str,intmin('int64')+int64(m(:)-1),'uni',0);
	p2c = @(m) arrayfun(@int2str,intmax('int64')-int64(m(:)-1),'uni',0);
	chk(n2c(magic(0)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:00))
	chk(n2c(magic(1)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:01))
	chk(n2c(magic(2)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:04))
	chk(n2c(magic(3)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:09))
	chk(n2c(magic(4)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:16))
	chk(n2c(magic(5)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:25))
	chk(n2c(magic(6)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:36))
	chk(n2c(magic(7)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:49))
	chk(n2c(magic(8)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:64))
	chk(n2c(magic(9)), '(+|-)?\d+', '%ld', fnh, n2c(1:+1:81))
	chk(p2c(magic(0)), '(+|-)?\d+', '%ld', fnh, p2c(00:-1:1))
	chk(p2c(magic(1)), '(+|-)?\d+', '%ld', fnh, p2c(01:-1:1))
	chk(p2c(magic(2)), '(+|-)?\d+', '%ld', fnh, p2c(04:-1:1))
	chk(p2c(magic(3)), '(+|-)?\d+', '%ld', fnh, p2c(09:-1:1))
	chk(p2c(magic(4)), '(+|-)?\d+', '%ld', fnh, p2c(16:-1:1))
	chk(p2c(magic(5)), '(+|-)?\d+', '%ld', fnh, p2c(25:-1:1))
	chk(p2c(magic(6)), '(+|-)?\d+', '%ld', fnh, p2c(36:-1:1))
	chk(p2c(magic(7)), '(+|-)?\d+', '%ld', fnh, p2c(49:-1:1))
	chk(p2c(magic(8)), '(+|-)?\d+', '%ld', fnh, p2c(64:-1:1))
	chk(p2c(magic(9)), '(+|-)?\d+', '%ld', fnh, p2c(81:-1:1))
	chk(n2c(magic(0)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:00))
	chk(n2c(magic(1)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:01))
	chk(n2c(magic(2)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:04))
	chk(n2c(magic(3)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:09))
	chk(n2c(magic(4)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:16))
	chk(n2c(magic(5)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:25))
	chk(n2c(magic(6)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:36))
	chk(n2c(magic(7)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:49))
	chk(n2c(magic(8)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:64))
	chk(n2c(magic(9)), '(+|-)?\d+', '%ld',  'ascend', fnh, n2c(1:+1:81))
	chk(n2c(magic(0)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(00:-1:1))
	chk(n2c(magic(1)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(01:-1:1))
	chk(n2c(magic(2)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(04:-1:1))
	chk(n2c(magic(3)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(09:-1:1))
	chk(n2c(magic(4)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(16:-1:1))
	chk(n2c(magic(5)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(25:-1:1))
	chk(n2c(magic(6)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(36:-1:1))
	chk(n2c(magic(7)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(49:-1:1))
	chk(n2c(magic(8)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(64:-1:1))
	chk(n2c(magic(9)), '(+|-)?\d+', '%ld', 'descend', fnh, n2c(81:-1:1))
	chk(p2c(magic(0)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(00:-1:1))
	chk(p2c(magic(1)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(01:-1:1))
	chk(p2c(magic(2)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(04:-1:1))
	chk(p2c(magic(3)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(09:-1:1))
	chk(p2c(magic(4)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(16:-1:1))
	chk(p2c(magic(5)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(25:-1:1))
	chk(p2c(magic(6)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(36:-1:1))
	chk(p2c(magic(7)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(49:-1:1))
	chk(p2c(magic(8)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(64:-1:1))
	chk(p2c(magic(9)), '(+|-)?\d+', '%ld',  'ascend', fnh, p2c(81:-1:1))
	chk(p2c(magic(0)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:00))
	chk(p2c(magic(1)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:01))
	chk(p2c(magic(2)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:04))
	chk(p2c(magic(3)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:09))
	chk(p2c(magic(4)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:16))
	chk(p2c(magic(5)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:25))
	chk(p2c(magic(6)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:36))
	chk(p2c(magic(7)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:49))
	chk(p2c(magic(8)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:64))
	chk(p2c(magic(9)), '(+|-)?\d+', '%ld', 'descend', fnh, p2c(1:+1:81))
	chk(n2c(magic(0)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:00))
	chk(n2c(magic(1)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:01))
	chk(n2c(magic(2)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:04))
	chk(n2c(magic(3)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:09))
	chk(n2c(magic(4)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:16))
	chk(n2c(magic(5)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:25))
	chk(n2c(magic(6)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:36))
	chk(n2c(magic(7)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:49))
	chk(n2c(magic(8)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:64))
	chk(n2c(magic(9)), '(+|-)?\d+',  'ascend', '%ld', fnh, n2c(1:+1:81))
	chk(n2c(magic(0)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(00:-1:1))
	chk(n2c(magic(1)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(01:-1:1))
	chk(n2c(magic(2)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(04:-1:1))
	chk(n2c(magic(3)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(09:-1:1))
	chk(n2c(magic(4)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(16:-1:1))
	chk(n2c(magic(5)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(25:-1:1))
	chk(n2c(magic(6)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(36:-1:1))
	chk(n2c(magic(7)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(49:-1:1))
	chk(n2c(magic(8)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(64:-1:1))
	chk(n2c(magic(9)), '(+|-)?\d+', 'descend', '%ld', fnh, n2c(81:-1:1))
	chk(p2c(magic(0)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(00:-1:1))
	chk(p2c(magic(1)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(01:-1:1))
	chk(p2c(magic(2)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(04:-1:1))
	chk(p2c(magic(3)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(09:-1:1))
	chk(p2c(magic(4)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(16:-1:1))
	chk(p2c(magic(5)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(25:-1:1))
	chk(p2c(magic(6)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(36:-1:1))
	chk(p2c(magic(7)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(49:-1:1))
	chk(p2c(magic(8)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(64:-1:1))
	chk(p2c(magic(9)), '(+|-)?\d+',  'ascend', '%ld', fnh, p2c(81:-1:1))
	chk(p2c(magic(0)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:00))
	chk(p2c(magic(1)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:01))
	chk(p2c(magic(2)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:04))
	chk(p2c(magic(3)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:09))
	chk(p2c(magic(4)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:16))
	chk(p2c(magic(5)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:25))
	chk(p2c(magic(6)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:36))
	chk(p2c(magic(7)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:49))
	chk(p2c(magic(8)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:64))
	chk(p2c(magic(9)), '(+|-)?\d+', 'descend', '%ld', fnh, p2c(1:+1:81))
	%
end
%
%% Numbers and NaN %%
%
H = {'aa','a1','10','1','','ac','2a','a10','ab','2','a2','a','10a','1a','c','b'};
chk(H, [], 'num<char','ascend', fnh,...
	{'','1','1a','2','2a','10','10a','a','a1','a2','a10','aa','ab','ac','b','c'}, [5,4,14,10,7,3,13,12,2,11,8,1,9,6,16,15])
chk(H, [], 'num<char', 'descend', fnh,...
	{'c','b','ac','ab','aa','a10','a2','a1','a','10a','10','2a','2','1a','1',''}, [15,16,6,9,1,8,11,2,12,13,3,7,10,14,4,5])
chk(H, [], 'char<num', 'ascend', fnh,...
	{'','a','aa','ab','ac','a1','a2','a10','b','c','1','1a','2','2a','10','10a'}, [5,12,1,9,6,2,11,8,16,15,4,14,10,7,3,13])
chk(H, [], 'char<num', 'descend', fnh,...
	{'10a','10','2a','2','1a','1','c','b','a10','a2','a1','ac','ab','aa','a',''}, [13,3,7,10,14,4,15,16,8,11,2,6,9,1,12,5])
%
I = {'a','1','b','10','','2','a2','a10','a1','a1y','a1z','a1x9','a1x10','a1x1','a1x'};
chk(I, [], 'num<char', 'ascend', fnh,...
	{'','1','2','10','a','a1','a1x','a1x1','a1x9','a1x10','a1y','a1z','a2','a10','b'}, [5,2,6,4,1,9,15,14,12,13,10,11,7,8,3])
chk(I, [], 'num<char', 'descend', fnh,...
	{'b','a10','a2','a1z','a1y','a1x10','a1x9','a1x1','a1x','a1','a','10','2','1',''}, [3,8,7,11,10,13,12,14,15,9,1,4,6,2,5])
chk(I, [], 'char<num', 'ascend', fnh,...
	{'','a','a1','a1x','a1x1','a1x9','a1x10','a1y','a1z','a2','a10','b','1','2','10'}, [5,1,9,15,14,12,13,10,11,7,8,3,2,6,4])
chk(I, [], 'char<num', 'descend', fnh,...
	{'10','2','1','b','a10','a2','a1z','a1y','a1x10','a1x9','a1x1','a1x','a1','a',''}, [4,6,2,3,8,7,11,10,13,12,14,15,9,1,5])
%
J = {'aaa','111','a11','1a1','aa1','11a','a1a','1aa'};
chk(J, [], 'num<char', 'ascend', fnh,...
	{'1a1','1aa','11a','111','a1a','a11','aa1','aaa'}, [4,8,6,2,7,3,5,1])
chk(J, [], 'num<char', 'descend', fnh,...
	{'aaa','aa1','a11','a1a','111','11a','1aa','1a1'}, [1,5,3,7,2,6,8,4])
chk(J, [], 'char<num', 'ascend', fnh,...
	{'aaa','aa1','a1a','a11','1aa','1a1','11a','111'}, [1,5,7,3,8,4,6,2])
chk(J, [], 'char<num', 'descend', fnh,...
	{'111','11a','1a1','1aa','a11','a1a','aa1','aaa'}, [2,6,4,8,3,7,5,1])
%
K = {'1234','1200','129'};
chk(K, '\d{1,2}', fnh,... quantifier
	{'1200','129','1234'}, [2,3,1], {12,34;12,0;12,9})
chk(K, '(?<=\d{2})\d+', fnh,... lookaround assertion
	{'1200','129','1234'}, [2,3,1], {'12',34;'12',0;'12',9})
%
inpM = {'10','NaNb','NaN','NaNc','1','NaNNaN','2','NaNa','NaN','10'};
dbgM = {10,[];NaN,'b';NaN,[];NaN,'c';1,[];NaN,NaN;2,[];NaN,'a';NaN,[];10,[]};
chk(inpM, 'NaN|\d+', 'num<NaN', 'ascend', fnh,...
	{'1','2','10','10','NaN','NaN','NaNNaN','NaNa','NaNb','NaNc'}, [5,7,1,10,3,9,6,8,2,4], dbgM)
chk(inpM, 'NaN|\d+', 'num<NaN', 'descend', fnh,...
	{'NaNc','NaNb','NaNa','NaNNaN','NaN','NaN','10','10','2','1'}, [4,2,8,6,3,9,1,10,7,5], dbgM)
chk(inpM, 'NaN|\d+', 'NaN<num', 'ascend', fnh,...
	{'NaN','NaN','NaNNaN','NaNa','NaNb','NaNc','1','2','10','10'}, [3,9,6,8,2,4,5,7,1,10], dbgM)
chk(inpM, 'NaN|\d+', 'NaN<num', 'descend', fnh,...
	{'10','10','2','1','NaNc','NaNb','NaNa','NaNNaN','NaN','NaN'}, [1,10,7,5,4,2,8,6,3,9], dbgM)
%
%% Orientation %%
%
chk({}, fnh, {}, [], {}) % empty!
chk(cell(0,2,0), fnh, cell(0,2,0), nan(0,2,0)) % empty!
chk(cell(0,2,1), fnh, cell(0,2,1), nan(0,2,1)) % empty!
chk(cell(0,2,2), fnh, cell(0,2,2), nan(0,2,2)) % empty!
chk(cell(0,2,3), fnh, cell(0,2,3), nan(0,2,3)) % empty!
chk(cell(0,2,4), fnh, cell(0,2,4), nan(0,2,4)) % empty!
chk(cell(0,2,5), fnh, cell(0,2,5), nan(0,2,5)) % empty!
%
chk({''}, fnh, {''}, 1, cell(1,0))
chk({'hello'}, fnh, {'hello'}, 1, {'hello'})
chk({'world','hello'}, fnh, {'hello','world'}, [2,1], {'world';'hello'})
chk({'smile','world','hello'}, fnh, {'hello','smile','world'}, [3,1,2], {'smile';'world';'hello'})
%
chk({'1';'10';'20';'2'}, fnh,...
	{'1';'2';'10';'20'}, [1;4;2;3])
chk({'2','10','8';'#','a',' '}, fnh,...
	{'2','10','#';'8',' ','a'}, [1,3,2;5,6,4])
%
cfn = @(varargin) repmat({'x'},[varargin{:}]);
chk(cfn(3,2,1), fnh, cfn(3,2,1), reshape(1:6,3,2,1))
chk(cfn(3,1,2), fnh, cfn(3,1,2), reshape(1:6,3,1,2))
chk(cfn(2,3,1), fnh, cfn(2,3,1), reshape(1:6,2,3,1))
chk(cfn(2,1,3), fnh, cfn(2,1,3), reshape(1:6,2,1,3))
chk(cfn(1,3,2), fnh, cfn(1,3,2), reshape(1:6,1,3,2))
chk(cfn(1,2,3), fnh, cfn(1,2,3), reshape(1:6,1,2,3))
%
%% Index Stability %%
%
chk(cfn(3,2,1), [],  'ascend', fnh, cfn(3,2,1), reshape(1:6,3,2,1), cfn(6,1))
chk(cfn(3,1,2), [],  'ascend', fnh, cfn(3,1,2), reshape(1:6,3,1,2), cfn(6,1))
chk(cfn(2,3,1), [],  'ascend', fnh, cfn(2,3,1), reshape(1:6,2,3,1), cfn(6,1))
chk(cfn(2,1,3), [],  'ascend', fnh, cfn(2,1,3), reshape(1:6,2,1,3), cfn(6,1))
chk(cfn(1,3,2), [],  'ascend', fnh, cfn(1,3,2), reshape(1:6,1,3,2), cfn(6,1))
chk(cfn(1,2,3), [],  'ascend', fnh, cfn(1,2,3), reshape(1:6,1,2,3), cfn(6,1))
chk(cfn(3,2,1), [], 'descend', fnh, cfn(3,2,1), reshape(1:6,3,2,1), cfn(6,1))
chk(cfn(3,1,2), [], 'descend', fnh, cfn(3,1,2), reshape(1:6,3,1,2), cfn(6,1))
chk(cfn(2,3,1), [], 'descend', fnh, cfn(2,3,1), reshape(1:6,2,3,1), cfn(6,1))
chk(cfn(2,1,3), [], 'descend', fnh, cfn(2,1,3), reshape(1:6,2,1,3), cfn(6,1))
chk(cfn(1,3,2), [], 'descend', fnh, cfn(1,3,2), reshape(1:6,1,3,2), cfn(6,1))
chk(cfn(1,2,3), [], 'descend', fnh, cfn(1,2,3), reshape(1:6,1,2,3), cfn(6,1))
%
xfn = @(n) reshape(1:n,[],1);
chk(cfn(0,1), [],  'ascend', fnh, cfn(0,1), xfn(0),       {})
chk(cfn(1,1), [],  'ascend', fnh, cfn(1,1), xfn(1), cfn(1,1))
chk(cfn(2,1), [],  'ascend', fnh, cfn(2,1), xfn(2), cfn(2,1))
chk(cfn(3,1), [],  'ascend', fnh, cfn(3,1), xfn(3), cfn(3,1))
chk(cfn(4,1), [],  'ascend', fnh, cfn(4,1), xfn(4), cfn(4,1))
chk(cfn(5,1), [],  'ascend', fnh, cfn(5,1), xfn(5), cfn(5,1))
chk(cfn(0,1), [], 'descend', fnh, cfn(0,1), xfn(0),       {})
chk(cfn(1,1), [], 'descend', fnh, cfn(1,1), xfn(1), cfn(1,1))
chk(cfn(2,1), [], 'descend', fnh, cfn(2,1), xfn(2), cfn(2,1))
chk(cfn(3,1), [], 'descend', fnh, cfn(3,1), xfn(3), cfn(3,1))
chk(cfn(4,1), [], 'descend', fnh, cfn(4,1), xfn(4), cfn(4,1))
chk(cfn(5,1), [], 'descend', fnh, cfn(5,1), xfn(5), cfn(5,1))
%
chk({}              , fnh, {}              ,     [],        {})
chk({''}            , fnh, {''}            , xfn(1), cell(1,0))
chk({'';''}         , fnh, {'';''}         , xfn(2), cell(2,0))
chk({'';'';''}      , fnh, {'';'';''}      , xfn(3), cell(3,0))
chk({'';'';'';''}   , fnh, {'';'';'';''}   , xfn(4), cell(4,0))
chk({'';'';'';'';''}, fnh, {'';'';'';'';''}, xfn(5), cell(5,0))
%
U = {'2';'3';'2';'1';'2'};
chk(U, [], 'ascend', fnh,...
	{'1';'2';'2';'2';'3'}, [4;1;3;5;2])
chk(U, [], 'descend', fnh,...
	{'3';'2';'2';'2';'1'}, [2;1;3;5;4])
%
V = {'x';'z';'y';'';'z';'';'x';'y'};
chk(V, [], 'ascend', fnh,...
	{'';'';'x';'x';'y';'y';'z';'z'},[4;6;1;7;3;8;2;5])
chk(V, [], 'descend', fnh,...
	{'z';'z';'y';'y';'x';'x';'';''},[2;5;3;8;1;7;4;6])
%
W = {'2x';'2z';'2y';'2';'2z';'2';'2x';'2y'};
chk(W, [], 'ascend', fnh,...
	{'2';'2';'2x';'2x';'2y';'2y';'2z';'2z'},[4;6;1;7;3;8;2;5])
chk(W, [], 'descend', fnh,...
	{'2z';'2z';'2y';'2y';'2x';'2x';'2';'2'},[2;5;3;8;1;7;4;6])
%
%% Permutations %%
%
% The expected outputs were generated using a different algorithm.
%
Q = 'xy012';
P = num2cell(Q(sortrows(perms(1:numel(Q)))),2);
%
chk(P, '\d+', 'ascend', 'num<char', 'num<NaN', fnh, ...
	{'0x1y2';'0x2y1';'0x12y';'0x21y';'0xy12';'0xy21';'0y1x2';'0y2x1';'0y12x';'0y21x';'0yx12';'0yx21';'1x0y2';'01x2y';'1x02y';'1x2y0';'1x20y';'01xy2';'1xy02';'1xy20';'1y0x2';'01y2x';'1y02x';'1y2x0';'1y20x';'01yx2';'1yx02';'1yx20';'2x0y1';'02x1y';'2x01y';'2x1y0';'2x10y';'02xy1';'2xy01';'2xy10';'2y0x1';'02y1x';'2y01x';'2y1x0';'2y10x';'02yx1';'2yx01';'2yx10';'10x2y';'10xy2';'10y2x';'10yx2';'12x0y';'012xy';'12xy0';'12y0x';'012yx';'12yx0';'20x1y';'20xy1';'20y1x';'20yx1';'21x0y';'021xy';'21xy0';'21y0x';'021yx';'21yx0';'102xy';'102yx';'120xy';'120yx';'201xy';'201yx';'210xy';'210yx';'x0y12';'x0y21';'x01y2';'x1y02';'x1y20';'x02y1';'x2y01';'x2y10';'x10y2';'x012y';'x12y0';'x20y1';'x021y';'x21y0';'x102y';'x120y';'x201y';'x210y';'xy012';'xy021';'xy102';'xy120';'xy201';'xy210';'y0x12';'y0x21';'y01x2';'y1x02';'y1x20';'y02x1';'y2x01';'y2x10';'y10x2';'y012x';'y12x0';'y20x1';'y021x';'y21x0';'y102x';'y120x';'y201x';'y210x';'yx012';'yx021';'yx102';'yx120';'yx201';'yx210'}, ...
	[51;53;52;54;49;50;57;59;58;60;55;56;75;62;76;77;78;61;73;74;81;64;82;83;84;63;79;80;99;68;100;101;102;67;97;98;105;70;106;107;108;69;103;104;86;85;88;87;92;65;91;94;66;93;110;109;112;111;116;71;115;118;72;117;89;90;95;96;113;114;119;120;7;8;9;13;14;11;19;20;15;10;17;21;12;23;16;18;22;24;1;2;3;4;5;6;31;32;33;37;38;35;43;44;39;34;41;45;36;47;40;42;46;48;25;26;27;28;29;30])
chk(P, '\d+', 'descend', 'num<char', 'num<NaN', fnh, ...
	{'yx210';'yx201';'yx120';'yx102';'yx021';'yx012';'y210x';'y201x';'y120x';'y102x';'y21x0';'y021x';'y20x1';'y12x0';'y012x';'y10x2';'y2x10';'y02x1';'y2x01';'y1x20';'y01x2';'y1x02';'y0x21';'y0x12';'xy210';'xy201';'xy120';'xy102';'xy021';'xy012';'x210y';'x201y';'x120y';'x102y';'x21y0';'x021y';'x20y1';'x12y0';'x012y';'x10y2';'x2y10';'x02y1';'x2y01';'x1y20';'x01y2';'x1y02';'x0y21';'x0y12';'210yx';'210xy';'201yx';'201xy';'120yx';'120xy';'102yx';'102xy';'21yx0';'021yx';'21y0x';'21xy0';'021xy';'21x0y';'20yx1';'20y1x';'20xy1';'20x1y';'12yx0';'012yx';'12y0x';'12xy0';'012xy';'12x0y';'10yx2';'10y2x';'10xy2';'10x2y';'2yx10';'02yx1';'2yx01';'2y10x';'2y1x0';'02y1x';'2y01x';'2y0x1';'2xy10';'02xy1';'2xy01';'2x10y';'2x1y0';'02x1y';'2x01y';'2x0y1';'1yx20';'01yx2';'1yx02';'1y20x';'1y2x0';'01y2x';'1y02x';'1y0x2';'1xy20';'01xy2';'1xy02';'1x20y';'1x2y0';'01x2y';'1x02y';'1x0y2';'0yx21';'0yx12';'0y21x';'0y12x';'0y2x1';'0y1x2';'0xy21';'0xy12';'0x21y';'0x12y';'0x2y1';'0x1y2'}, ...
	[30;29;28;27;26;25;48;46;42;40;47;36;45;41;34;39;44;35;43;38;33;37;32;31;6;5;4;3;2;1;24;22;18;16;23;12;21;17;10;15;20;11;19;14;9;13;8;7;120;119;114;113;96;95;90;89;117;72;118;115;71;116;111;112;109;110;93;66;94;91;65;92;87;88;85;86;104;69;103;108;107;70;106;105;98;67;97;102;101;68;100;99;80;63;79;84;83;64;82;81;74;61;73;78;77;62;76;75;56;55;60;58;59;57;50;49;54;52;53;51])
chk(P, '\d+', 'ascend', 'char<num', 'num<NaN', fnh, ...
	{'xy012';'xy021';'xy102';'xy120';'xy201';'xy210';'x0y12';'x0y21';'x01y2';'x1y02';'x1y20';'x02y1';'x2y01';'x2y10';'x10y2';'x012y';'x12y0';'x20y1';'x021y';'x21y0';'x102y';'x120y';'x201y';'x210y';'yx012';'yx021';'yx102';'yx120';'yx201';'yx210';'y0x12';'y0x21';'y01x2';'y1x02';'y1x20';'y02x1';'y2x01';'y2x10';'y10x2';'y012x';'y12x0';'y20x1';'y021x';'y21x0';'y102x';'y120x';'y201x';'y210x';'0xy12';'0xy21';'0x1y2';'0x2y1';'0x12y';'0x21y';'0yx12';'0yx21';'0y1x2';'0y2x1';'0y12x';'0y21x';'01xy2';'1xy02';'1xy20';'1x0y2';'01x2y';'1x02y';'1x2y0';'1x20y';'01yx2';'1yx02';'1yx20';'1y0x2';'01y2x';'1y02x';'1y2x0';'1y20x';'02xy1';'2xy01';'2xy10';'2x0y1';'02x1y';'2x01y';'2x1y0';'2x10y';'02yx1';'2yx01';'2yx10';'2y0x1';'02y1x';'2y01x';'2y1x0';'2y10x';'10xy2';'10x2y';'10yx2';'10y2x';'012xy';'12xy0';'12x0y';'012yx';'12yx0';'12y0x';'20xy1';'20x1y';'20yx1';'20y1x';'021xy';'21xy0';'21x0y';'021yx';'21yx0';'21y0x';'102xy';'102yx';'120xy';'120yx';'201xy';'201yx';'210xy';'210yx'}, ...
	[1;2;3;4;5;6;7;8;9;13;14;11;19;20;15;10;17;21;12;23;16;18;22;24;25;26;27;28;29;30;31;32;33;37;38;35;43;44;39;34;41;45;36;47;40;42;46;48;49;50;51;53;52;54;55;56;57;59;58;60;61;73;74;75;62;76;77;78;63;79;80;81;64;82;83;84;67;97;98;99;68;100;101;102;69;103;104;105;70;106;107;108;85;86;87;88;65;91;92;66;93;94;109;110;111;112;71;115;116;72;117;118;89;90;95;96;113;114;119;120])
chk(P, '\d+', 'descend', 'char<num', 'num<NaN', fnh, ...
	{'210yx';'210xy';'201yx';'201xy';'120yx';'120xy';'102yx';'102xy';'21y0x';'21yx0';'021yx';'21x0y';'21xy0';'021xy';'20y1x';'20yx1';'20x1y';'20xy1';'12y0x';'12yx0';'012yx';'12x0y';'12xy0';'012xy';'10y2x';'10yx2';'10x2y';'10xy2';'2y10x';'2y1x0';'02y1x';'2y01x';'2y0x1';'2yx10';'02yx1';'2yx01';'2x10y';'2x1y0';'02x1y';'2x01y';'2x0y1';'2xy10';'02xy1';'2xy01';'1y20x';'1y2x0';'01y2x';'1y02x';'1y0x2';'1yx20';'01yx2';'1yx02';'1x20y';'1x2y0';'01x2y';'1x02y';'1x0y2';'1xy20';'01xy2';'1xy02';'0y21x';'0y12x';'0y2x1';'0y1x2';'0yx21';'0yx12';'0x21y';'0x12y';'0x2y1';'0x1y2';'0xy21';'0xy12';'y210x';'y201x';'y120x';'y102x';'y21x0';'y021x';'y20x1';'y12x0';'y012x';'y10x2';'y2x10';'y02x1';'y2x01';'y1x20';'y01x2';'y1x02';'y0x21';'y0x12';'yx210';'yx201';'yx120';'yx102';'yx021';'yx012';'x210y';'x201y';'x120y';'x102y';'x21y0';'x021y';'x20y1';'x12y0';'x012y';'x10y2';'x2y10';'x02y1';'x2y01';'x1y20';'x01y2';'x1y02';'x0y21';'x0y12';'xy210';'xy201';'xy120';'xy102';'xy021';'xy012'}, ...
	[120;119;114;113;96;95;90;89;118;117;72;116;115;71;112;111;110;109;94;93;66;92;91;65;88;87;86;85;108;107;70;106;105;104;69;103;102;101;68;100;99;98;67;97;84;83;64;82;81;80;63;79;78;77;62;76;75;74;61;73;60;58;59;57;56;55;54;52;53;51;50;49;48;46;42;40;47;36;45;41;34;39;44;35;43;38;33;37;32;31;30;29;28;27;26;25;24;22;18;16;23;12;21;17;10;15;20;11;19;14;9;13;8;7;6;5;4;3;2;1])
% As there are no NaNs these should give the same output:
chk(P, '\d+', 'ascend', 'num<char', 'NaN<num', fnh, ...
	{'0x1y2';'0x2y1';'0x12y';'0x21y';'0xy12';'0xy21';'0y1x2';'0y2x1';'0y12x';'0y21x';'0yx12';'0yx21';'1x0y2';'01x2y';'1x02y';'1x2y0';'1x20y';'01xy2';'1xy02';'1xy20';'1y0x2';'01y2x';'1y02x';'1y2x0';'1y20x';'01yx2';'1yx02';'1yx20';'2x0y1';'02x1y';'2x01y';'2x1y0';'2x10y';'02xy1';'2xy01';'2xy10';'2y0x1';'02y1x';'2y01x';'2y1x0';'2y10x';'02yx1';'2yx01';'2yx10';'10x2y';'10xy2';'10y2x';'10yx2';'12x0y';'012xy';'12xy0';'12y0x';'012yx';'12yx0';'20x1y';'20xy1';'20y1x';'20yx1';'21x0y';'021xy';'21xy0';'21y0x';'021yx';'21yx0';'102xy';'102yx';'120xy';'120yx';'201xy';'201yx';'210xy';'210yx';'x0y12';'x0y21';'x01y2';'x1y02';'x1y20';'x02y1';'x2y01';'x2y10';'x10y2';'x012y';'x12y0';'x20y1';'x021y';'x21y0';'x102y';'x120y';'x201y';'x210y';'xy012';'xy021';'xy102';'xy120';'xy201';'xy210';'y0x12';'y0x21';'y01x2';'y1x02';'y1x20';'y02x1';'y2x01';'y2x10';'y10x2';'y012x';'y12x0';'y20x1';'y021x';'y21x0';'y102x';'y120x';'y201x';'y210x';'yx012';'yx021';'yx102';'yx120';'yx201';'yx210'}, ...
	[51;53;52;54;49;50;57;59;58;60;55;56;75;62;76;77;78;61;73;74;81;64;82;83;84;63;79;80;99;68;100;101;102;67;97;98;105;70;106;107;108;69;103;104;86;85;88;87;92;65;91;94;66;93;110;109;112;111;116;71;115;118;72;117;89;90;95;96;113;114;119;120;7;8;9;13;14;11;19;20;15;10;17;21;12;23;16;18;22;24;1;2;3;4;5;6;31;32;33;37;38;35;43;44;39;34;41;45;36;47;40;42;46;48;25;26;27;28;29;30])
chk(P, '\d+', 'descend', 'num<char', 'NaN<num', fnh, ...
	{'yx210';'yx201';'yx120';'yx102';'yx021';'yx012';'y210x';'y201x';'y120x';'y102x';'y21x0';'y021x';'y20x1';'y12x0';'y012x';'y10x2';'y2x10';'y02x1';'y2x01';'y1x20';'y01x2';'y1x02';'y0x21';'y0x12';'xy210';'xy201';'xy120';'xy102';'xy021';'xy012';'x210y';'x201y';'x120y';'x102y';'x21y0';'x021y';'x20y1';'x12y0';'x012y';'x10y2';'x2y10';'x02y1';'x2y01';'x1y20';'x01y2';'x1y02';'x0y21';'x0y12';'210yx';'210xy';'201yx';'201xy';'120yx';'120xy';'102yx';'102xy';'21yx0';'021yx';'21y0x';'21xy0';'021xy';'21x0y';'20yx1';'20y1x';'20xy1';'20x1y';'12yx0';'012yx';'12y0x';'12xy0';'012xy';'12x0y';'10yx2';'10y2x';'10xy2';'10x2y';'2yx10';'02yx1';'2yx01';'2y10x';'2y1x0';'02y1x';'2y01x';'2y0x1';'2xy10';'02xy1';'2xy01';'2x10y';'2x1y0';'02x1y';'2x01y';'2x0y1';'1yx20';'01yx2';'1yx02';'1y20x';'1y2x0';'01y2x';'1y02x';'1y0x2';'1xy20';'01xy2';'1xy02';'1x20y';'1x2y0';'01x2y';'1x02y';'1x0y2';'0yx21';'0yx12';'0y21x';'0y12x';'0y2x1';'0y1x2';'0xy21';'0xy12';'0x21y';'0x12y';'0x2y1';'0x1y2'}, ...
	[30;29;28;27;26;25;48;46;42;40;47;36;45;41;34;39;44;35;43;38;33;37;32;31;6;5;4;3;2;1;24;22;18;16;23;12;21;17;10;15;20;11;19;14;9;13;8;7;120;119;114;113;96;95;90;89;117;72;118;115;71;116;111;112;109;110;93;66;94;91;65;92;87;88;85;86;104;69;103;108;107;70;106;105;98;67;97;102;101;68;100;99;80;63;79;84;83;64;82;81;74;61;73;78;77;62;76;75;56;55;60;58;59;57;50;49;54;52;53;51])
chk(P, '\d+', 'ascend', 'char<num', 'NaN<num', fnh, ...
	{'xy012';'xy021';'xy102';'xy120';'xy201';'xy210';'x0y12';'x0y21';'x01y2';'x1y02';'x1y20';'x02y1';'x2y01';'x2y10';'x10y2';'x012y';'x12y0';'x20y1';'x021y';'x21y0';'x102y';'x120y';'x201y';'x210y';'yx012';'yx021';'yx102';'yx120';'yx201';'yx210';'y0x12';'y0x21';'y01x2';'y1x02';'y1x20';'y02x1';'y2x01';'y2x10';'y10x2';'y012x';'y12x0';'y20x1';'y021x';'y21x0';'y102x';'y120x';'y201x';'y210x';'0xy12';'0xy21';'0x1y2';'0x2y1';'0x12y';'0x21y';'0yx12';'0yx21';'0y1x2';'0y2x1';'0y12x';'0y21x';'01xy2';'1xy02';'1xy20';'1x0y2';'01x2y';'1x02y';'1x2y0';'1x20y';'01yx2';'1yx02';'1yx20';'1y0x2';'01y2x';'1y02x';'1y2x0';'1y20x';'02xy1';'2xy01';'2xy10';'2x0y1';'02x1y';'2x01y';'2x1y0';'2x10y';'02yx1';'2yx01';'2yx10';'2y0x1';'02y1x';'2y01x';'2y1x0';'2y10x';'10xy2';'10x2y';'10yx2';'10y2x';'012xy';'12xy0';'12x0y';'012yx';'12yx0';'12y0x';'20xy1';'20x1y';'20yx1';'20y1x';'021xy';'21xy0';'21x0y';'021yx';'21yx0';'21y0x';'102xy';'102yx';'120xy';'120yx';'201xy';'201yx';'210xy';'210yx'}, ...
	[1;2;3;4;5;6;7;8;9;13;14;11;19;20;15;10;17;21;12;23;16;18;22;24;25;26;27;28;29;30;31;32;33;37;38;35;43;44;39;34;41;45;36;47;40;42;46;48;49;50;51;53;52;54;55;56;57;59;58;60;61;73;74;75;62;76;77;78;63;79;80;81;64;82;83;84;67;97;98;99;68;100;101;102;69;103;104;105;70;106;107;108;85;86;87;88;65;91;92;66;93;94;109;110;111;112;71;115;116;72;117;118;89;90;95;96;113;114;119;120])
chk(P, '\d+', 'descend', 'char<num', 'NaN<num', fnh, ...
	{'210yx';'210xy';'201yx';'201xy';'120yx';'120xy';'102yx';'102xy';'21y0x';'21yx0';'021yx';'21x0y';'21xy0';'021xy';'20y1x';'20yx1';'20x1y';'20xy1';'12y0x';'12yx0';'012yx';'12x0y';'12xy0';'012xy';'10y2x';'10yx2';'10x2y';'10xy2';'2y10x';'2y1x0';'02y1x';'2y01x';'2y0x1';'2yx10';'02yx1';'2yx01';'2x10y';'2x1y0';'02x1y';'2x01y';'2x0y1';'2xy10';'02xy1';'2xy01';'1y20x';'1y2x0';'01y2x';'1y02x';'1y0x2';'1yx20';'01yx2';'1yx02';'1x20y';'1x2y0';'01x2y';'1x02y';'1x0y2';'1xy20';'01xy2';'1xy02';'0y21x';'0y12x';'0y2x1';'0y1x2';'0yx21';'0yx12';'0x21y';'0x12y';'0x2y1';'0x1y2';'0xy21';'0xy12';'y210x';'y201x';'y120x';'y102x';'y21x0';'y021x';'y20x1';'y12x0';'y012x';'y10x2';'y2x10';'y02x1';'y2x01';'y1x20';'y01x2';'y1x02';'y0x21';'y0x12';'yx210';'yx201';'yx120';'yx102';'yx021';'yx012';'x210y';'x201y';'x120y';'x102y';'x21y0';'x021y';'x20y1';'x12y0';'x012y';'x10y2';'x2y10';'x02y1';'x2y01';'x1y20';'x01y2';'x1y02';'x0y21';'x0y12';'xy210';'xy201';'xy120';'xy102';'xy021';'xy012'}, ...
	[120;119;114;113;96;95;90;89;118;117;72;116;115;71;112;111;110;109;94;93;66;92;91;65;88;87;86;85;108;107;70;106;105;104;69;103;102;101;68;100;99;98;67;97;84;83;64;82;81;80;63;79;78;77;62;76;75;74;61;73;60;58;59;57;56;55;54;52;53;51;50;49;48;46;42;40;47;36;45;41;34;39;44;35;43;38;33;37;32;31;30;29;28;27;26;25;24;22;18;16;23;12;21;17;10;15;20;11;19;14;9;13;8;7;6;5;4;3;2;1])
%
Q = 'ann012';
P = num2cell(Q(sortrows(perms(1:numel(Q)))),2);
%
chk(P, 'NaN|\d+', 'ascend', 'num<char', 'num<NaN', fnh, ...
	{'0nan12';'0nan12';'0nan21';'0nan21';'0a1n2n';'0a1n2n';'0a1nn2';'0a1nn2';'0a2n1n';'0a2n1n';'0a2nn1';'0a2nn1';'0a12nn';'0a12nn';'0a21nn';'0a21nn';'0an1n2';'0an1n2';'0an2n1';'0an2n1';'0an12n';'0an12n';'0an21n';'0an21n';'0ann12';'0ann12';'0ann21';'0ann21';'0n1a2n';'0n1a2n';'0n1an2';'0n1an2';'0n1n2a';'0n1n2a';'0n1na2';'0n1na2';'0n2a1n';'0n2a1n';'0n2an1';'0n2an1';'0n2n1a';'0n2n1a';'0n2na1';'0n2na1';'0n12an';'0n12an';'0n12na';'0n12na';'0n21an';'0n21an';'0n21na';'0n21na';'0na1n2';'0na1n2';'0na2n1';'0na2n1';'0na12n';'0na12n';'0na21n';'0na21n';'0nn1a2';'0nn1a2';'0nn2a1';'0nn2a1';'0nn12a';'0nn12a';'0nn21a';'0nn21a';'0nna12';'0nna12';'0nna21';'0nna21';'01nan2';'01nan2';'1nan02';'1nan02';'1nan20';'1nan20';'1a0n2n';'1a0n2n';'1a0nn2';'1a0nn2';'1a2n0n';'1a2n0n';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a2nn0';'1a2nn0';'1a20nn';'1a20nn';'1an0n2';'1an0n2';'01an2n';'01an2n';'1an02n';'1an02n';'1an2n0';'1an2n0';'1an20n';'1an20n';'01ann2';'01ann2';'1ann02';'1ann02';'1ann20';'1ann20';'1n0a2n';'1n0a2n';'1n0an2';'1n0an2';'1n0n2a';'1n0n2a';'1n0na2';'1n0na2';'1n2a0n';'1n2a0n';'01n2an';'01n2an';'1n02an';'1n02an';'1n2an0';'1n2an0';'1n2n0a';'1n2n0a';'01n2na';'01n2na';'1n02na';'1n02na';'1n2na0';'1n2na0';'1n20an';'1n20an';'1n20na';'1n20na';'1na0n2';'1na0n2';'01na2n';'01na2n';'1na02n';'1na02n';'1na2n0';'1na2n0';'1na20n';'1na20n';'1nn0a2';'1nn0a2';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn2a0';'1nn2a0';'1nn20a';'1nn20a';'01nna2';'01nna2';'1nna02';'1nna02';'1nna20';'1nna20';'02nan1';'02nan1';'2nan01';'2nan01';'2nan10';'2nan10';'2a0n1n';'2a0n1n';'2a0nn1';'2a0nn1';'2a1n0n';'2a1n0n';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a1nn0';'2a1nn0';'2a10nn';'2a10nn';'2an0n1';'2an0n1';'02an1n';'02an1n';'2an01n';'2an01n';'2an1n0';'2an1n0';'2an10n';'2an10n';'02ann1';'02ann1';'2ann01';'2ann01';'2ann10';'2ann10';'2n0a1n';'2n0a1n';'2n0an1';'2n0an1';'2n0n1a';'2n0n1a';'2n0na1';'2n0na1';'2n1a0n';'2n1a0n';'02n1an';'02n1an';'2n01an';'2n01an';'2n1an0';'2n1an0';'2n1n0a';'2n1n0a';'02n1na';'02n1na';'2n01na';'2n01na';'2n1na0';'2n1na0';'2n10an';'2n10an';'2n10na';'2n10na';'2na0n1';'2na0n1';'02na1n';'02na1n';'2na01n';'2na01n';'2na1n0';'2na1n0';'2na10n';'2na10n';'2nn0a1';'2nn0a1';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn1a0';'2nn1a0';'2nn10a';'2nn10a';'02nna1';'02nna1';'2nna01';'2nna01';'2nna10';'2nna10';'10nan2';'10nan2';'10a2nn';'10a2nn';'10an2n';'10an2n';'10ann2';'10ann2';'10n2an';'10n2an';'10n2na';'10n2na';'10na2n';'10na2n';'10nn2a';'10nn2a';'10nna2';'10nna2';'012nan';'012nan';'12nan0';'12nan0';'12a0nn';'12a0nn';'12an0n';'12an0n';'012ann';'012ann';'12ann0';'12ann0';'12n0an';'12n0an';'12n0na';'12n0na';'12na0n';'12na0n';'12nn0a';'12nn0a';'012nna';'012nna';'12nna0';'12nna0';'20nan1';'20nan1';'20a1nn';'20a1nn';'20an1n';'20an1n';'20ann1';'20ann1';'20n1an';'20n1an';'20n1na';'20n1na';'20na1n';'20na1n';'20nn1a';'20nn1a';'20nna1';'20nna1';'021nan';'021nan';'21nan0';'21nan0';'21a0nn';'21a0nn';'21an0n';'21an0n';'021ann';'021ann';'21ann0';'21ann0';'21n0an';'21n0an';'21n0na';'21n0na';'21na0n';'21na0n';'21nn0a';'21nn0a';'021nna';'021nna';'21nna0';'21nna0';'102nan';'102nan';'102ann';'102ann';'102nna';'102nna';'120nan';'120nan';'120ann';'120ann';'120nna';'120nna';'201nan';'201nan';'201ann';'201ann';'201nna';'201nna';'210nan';'210nan';'210ann';'210ann';'210nna';'210nna';'nan012';'nan012';'nan021';'nan021';'nan102';'nan102';'nan120';'nan120';'nan201';'nan201';'nan210';'nan210';'a0n1n2';'a0n1n2';'a0n2n1';'a0n2n1';'a0n12n';'a0n12n';'a0n21n';'a0n21n';'a0nn12';'a0nn12';'a0nn21';'a0nn21';'a1n0n2';'a1n0n2';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n2n0';'a1n2n0';'a1n20n';'a1n20n';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a1nn20';'a1nn20';'a2n0n1';'a2n0n1';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n1n0';'a2n1n0';'a2n10n';'a2n10n';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a2nn10';'a2nn10';'a10n2n';'a10n2n';'a10nn2';'a10nn2';'a12n0n';'a12n0n';'a012nn';'a012nn';'a12nn0';'a12nn0';'a20n1n';'a20n1n';'a20nn1';'a20nn1';'a21n0n';'a21n0n';'a021nn';'a021nn';'a21nn0';'a21nn0';'a102nn';'a102nn';'a120nn';'a120nn';'a201nn';'a201nn';'a210nn';'a210nn';'an0n12';'an0n12';'an0n21';'an0n21';'an01n2';'an1n02';'an01n2';'an1n02';'an1n20';'an1n20';'an02n1';'an2n01';'an02n1';'an2n01';'an2n10';'an2n10';'an10n2';'an10n2';'an012n';'an012n';'an12n0';'an12n0';'an20n1';'an20n1';'an021n';'an021n';'an21n0';'an21n0';'an102n';'an102n';'an120n';'an120n';'an201n';'an201n';'an210n';'an210n';'ann012';'ann012';'ann021';'ann021';'ann102';'ann102';'ann120';'ann120';'ann201';'ann201';'ann210';'ann210';'n0a1n2';'n0a1n2';'n0a2n1';'n0a2n1';'n0a12n';'n0a12n';'n0a21n';'n0a21n';'n0an12';'n0an12';'n0an21';'n0an21';'n0n1a2';'n0n1a2';'n0n2a1';'n0n2a1';'n0n12a';'n0n12a';'n0n21a';'n0n21a';'n0na12';'n0na12';'n0na21';'n0na21';'n1a0n2';'n1a0n2';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a2n0';'n1a2n0';'n1a20n';'n1a20n';'n01an2';'n1an02';'n01an2';'n1an02';'n1an20';'n1an20';'n1n0a2';'n1n0a2';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n2a0';'n1n2a0';'n1n20a';'n1n20a';'n01na2';'n1na02';'n01na2';'n1na02';'n1na20';'n1na20';'n2a0n1';'n2a0n1';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a1n0';'n2a1n0';'n2a10n';'n2a10n';'n02an1';'n2an01';'n02an1';'n2an01';'n2an10';'n2an10';'n2n0a1';'n2n0a1';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n1a0';'n2n1a0';'n2n10a';'n2n10a';'n02na1';'n2na01';'n02na1';'n2na01';'n2na10';'n2na10';'n10a2n';'n10a2n';'n10an2';'n10an2';'n10n2a';'n10n2a';'n10na2';'n10na2';'n12a0n';'n12a0n';'n012an';'n012an';'n12an0';'n12an0';'n12n0a';'n12n0a';'n012na';'n012na';'n12na0';'n12na0';'n20a1n';'n20a1n';'n20an1';'n20an1';'n20n1a';'n20n1a';'n20na1';'n20na1';'n21a0n';'n21a0n';'n021an';'n021an';'n21an0';'n21an0';'n21n0a';'n21n0a';'n021na';'n021na';'n21na0';'n21na0';'n102an';'n102an';'n102na';'n102na';'n120an';'n120an';'n120na';'n120na';'n201an';'n201an';'n201na';'n201na';'n210an';'n210an';'n210na';'n210na';'na0n12';'na0n12';'na0n21';'na0n21';'na01n2';'na1n02';'na01n2';'na1n02';'na1n20';'na1n20';'na02n1';'na2n01';'na02n1';'na2n01';'na2n10';'na2n10';'na10n2';'na10n2';'na012n';'na012n';'na12n0';'na12n0';'na20n1';'na20n1';'na021n';'na021n';'na21n0';'na21n0';'na102n';'na102n';'na120n';'na120n';'na201n';'na201n';'na210n';'na210n';'nn0a12';'nn0a12';'nn0a21';'nn0a21';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn1a20';'nn1a20';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn2a10';'nn2a10';'nn10a2';'nn10a2';'nn012a';'nn012a';'nn12a0';'nn12a0';'nn20a1';'nn20a1';'nn021a';'nn021a';'nn21a0';'nn21a0';'nn102a';'nn102a';'nn120a';'nn120a';'nn201a';'nn201a';'nn210a';'nn210a';'nna012';'nna012';'nna021';'nna021';'nna102';'nna102';'nna120';'nna120';'nna201';'nna201';'nna210';'nna210'}, ...
	[385;409;386;410;374;376;373;375;380;382;379;381;377;378;383;384;363;369;365;371;364;370;366;372;361;367;362;368;398;422;397;421;400;424;399;423;404;428;403;427;406;430;405;429;401;425;402;426;407;431;408;432;387;411;389;413;388;412;390;414;393;417;395;419;394;418;396;420;391;415;392;416;439;445;505;529;506;530;494;496;493;495;500;502;437;438;497;498;499;501;503;504;483;489;434;436;484;490;485;491;486;492;433;435;481;487;482;488;518;542;517;541;520;544;519;543;524;548;443;449;521;545;523;547;526;550;444;450;522;546;525;549;527;551;528;552;507;531;440;446;508;532;509;533;510;534;513;537;442;448;514;538;515;539;516;540;441;447;511;535;512;536;463;469;625;649;626;650;614;616;613;615;620;622;461;462;617;618;619;621;623;624;603;609;458;460;604;610;605;611;606;612;457;459;601;607;602;608;638;662;637;661;640;664;639;663;644;668;467;473;641;665;643;667;646;670;468;474;642;666;645;669;647;671;648;672;627;651;464;470;628;652;629;653;630;654;633;657;466;472;634;658;635;659;636;660;465;471;631;655;632;656;559;565;557;558;554;556;553;555;563;569;564;570;560;566;562;568;561;567;453;455;583;589;581;582;578;580;451;452;577;579;587;593;588;594;584;590;586;592;454;456;585;591;679;685;677;678;674;676;673;675;683;689;684;690;680;686;682;688;681;687;477;479;703;709;701;702;698;700;475;476;697;699;707;713;708;714;704;710;706;712;478;480;705;711;573;575;571;572;574;576;597;599;595;596;598;600;693;695;691;692;694;696;717;719;715;716;718;720;121;241;122;242;123;243;124;244;125;245;126;246;51;57;53;59;52;58;54;60;49;55;50;56;75;81;62;64;76;82;77;83;78;84;61;63;73;79;74;80;99;105;68;70;100;106;101;107;102;108;67;69;97;103;98;104;86;88;85;87;92;94;65;66;91;93;110;112;109;111;116;118;71;72;115;117;89;90;95;96;113;114;119;120;7;31;8;32;9;13;33;37;14;38;11;19;35;43;20;44;15;39;10;34;17;41;21;45;12;36;23;47;16;40;18;42;22;46;24;48;1;25;2;26;3;27;4;28;5;29;6;30;171;291;173;293;172;292;174;294;169;289;170;290;177;297;179;299;178;298;180;300;175;295;176;296;195;315;182;196;302;316;197;317;198;318;181;193;301;313;194;314;201;321;184;202;304;322;203;323;204;324;183;199;303;319;200;320;219;339;188;220;308;340;221;341;222;342;187;217;307;337;218;338;225;345;190;226;310;346;227;347;228;348;189;223;309;343;224;344;206;326;205;325;208;328;207;327;212;332;185;305;211;331;214;334;186;306;213;333;230;350;229;349;232;352;231;351;236;356;191;311;235;355;238;358;192;312;237;357;209;329;210;330;215;335;216;336;233;353;234;354;239;359;240;360;127;247;128;248;129;133;249;253;134;254;131;139;251;259;140;260;135;255;130;250;137;257;141;261;132;252;143;263;136;256;138;258;142;262;144;264;151;271;152;272;153;157;273;277;158;278;155;163;275;283;164;284;159;279;154;274;161;281;165;285;156;276;167;287;160;280;162;282;166;286;168;288;145;265;146;266;147;267;148;268;149;269;150;270])
chk(P, 'NaN|\d+', 'descend', 'num<char', 'num<NaN', fnh, ...
	{'nna210';'nna210';'nna201';'nna201';'nna120';'nna120';'nna102';'nna102';'nna021';'nna021';'nna012';'nna012';'nn210a';'nn210a';'nn201a';'nn201a';'nn120a';'nn120a';'nn102a';'nn102a';'nn21a0';'nn21a0';'nn021a';'nn021a';'nn20a1';'nn20a1';'nn12a0';'nn12a0';'nn012a';'nn012a';'nn10a2';'nn10a2';'nn2a10';'nn2a10';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn1a20';'nn1a20';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn0a21';'nn0a21';'nn0a12';'nn0a12';'na210n';'na210n';'na201n';'na201n';'na120n';'na120n';'na102n';'na102n';'na21n0';'na21n0';'na021n';'na021n';'na20n1';'na20n1';'na12n0';'na12n0';'na012n';'na012n';'na10n2';'na10n2';'na2n10';'na2n10';'na02n1';'na2n01';'na02n1';'na2n01';'na1n20';'na1n20';'na01n2';'na1n02';'na01n2';'na1n02';'na0n21';'na0n21';'na0n12';'na0n12';'n210na';'n210na';'n210an';'n210an';'n201na';'n201na';'n201an';'n201an';'n120na';'n120na';'n120an';'n120an';'n102na';'n102na';'n102an';'n102an';'n21na0';'n21na0';'n021na';'n021na';'n21n0a';'n21n0a';'n21an0';'n21an0';'n021an';'n021an';'n21a0n';'n21a0n';'n20na1';'n20na1';'n20n1a';'n20n1a';'n20an1';'n20an1';'n20a1n';'n20a1n';'n12na0';'n12na0';'n012na';'n012na';'n12n0a';'n12n0a';'n12an0';'n12an0';'n012an';'n012an';'n12a0n';'n12a0n';'n10na2';'n10na2';'n10n2a';'n10n2a';'n10an2';'n10an2';'n10a2n';'n10a2n';'n2na10';'n2na10';'n02na1';'n2na01';'n02na1';'n2na01';'n2n10a';'n2n10a';'n2n1a0';'n2n1a0';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n0a1';'n2n0a1';'n2an10';'n2an10';'n02an1';'n2an01';'n02an1';'n2an01';'n2a10n';'n2a10n';'n2a1n0';'n2a1n0';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a0n1';'n2a0n1';'n1na20';'n1na20';'n01na2';'n1na02';'n01na2';'n1na02';'n1n20a';'n1n20a';'n1n2a0';'n1n2a0';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n0a2';'n1n0a2';'n1an20';'n1an20';'n01an2';'n1an02';'n01an2';'n1an02';'n1a20n';'n1a20n';'n1a2n0';'n1a2n0';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a0n2';'n1a0n2';'n0na21';'n0na21';'n0na12';'n0na12';'n0n21a';'n0n21a';'n0n12a';'n0n12a';'n0n2a1';'n0n2a1';'n0n1a2';'n0n1a2';'n0an21';'n0an21';'n0an12';'n0an12';'n0a21n';'n0a21n';'n0a12n';'n0a12n';'n0a2n1';'n0a2n1';'n0a1n2';'n0a1n2';'ann210';'ann210';'ann201';'ann201';'ann120';'ann120';'ann102';'ann102';'ann021';'ann021';'ann012';'ann012';'an210n';'an210n';'an201n';'an201n';'an120n';'an120n';'an102n';'an102n';'an21n0';'an21n0';'an021n';'an021n';'an20n1';'an20n1';'an12n0';'an12n0';'an012n';'an012n';'an10n2';'an10n2';'an2n10';'an2n10';'an02n1';'an2n01';'an02n1';'an2n01';'an1n20';'an1n20';'an01n2';'an1n02';'an01n2';'an1n02';'an0n21';'an0n21';'an0n12';'an0n12';'a210nn';'a210nn';'a201nn';'a201nn';'a120nn';'a120nn';'a102nn';'a102nn';'a21nn0';'a21nn0';'a021nn';'a021nn';'a21n0n';'a21n0n';'a20nn1';'a20nn1';'a20n1n';'a20n1n';'a12nn0';'a12nn0';'a012nn';'a012nn';'a12n0n';'a12n0n';'a10nn2';'a10nn2';'a10n2n';'a10n2n';'a2nn10';'a2nn10';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a2n10n';'a2n10n';'a2n1n0';'a2n1n0';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n0n1';'a2n0n1';'a1nn20';'a1nn20';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a1n20n';'a1n20n';'a1n2n0';'a1n2n0';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n0n2';'a1n0n2';'a0nn21';'a0nn21';'a0nn12';'a0nn12';'a0n21n';'a0n21n';'a0n12n';'a0n12n';'a0n2n1';'a0n2n1';'a0n1n2';'a0n1n2';'nan210';'nan210';'nan201';'nan201';'nan120';'nan120';'nan102';'nan102';'nan021';'nan021';'nan012';'nan012';'210nna';'210nna';'210ann';'210ann';'210nan';'210nan';'201nna';'201nna';'201ann';'201ann';'201nan';'201nan';'120nna';'120nna';'120ann';'120ann';'120nan';'120nan';'102nna';'102nna';'102ann';'102ann';'102nan';'102nan';'21nna0';'21nna0';'021nna';'021nna';'21nn0a';'21nn0a';'21na0n';'21na0n';'21n0na';'21n0na';'21n0an';'21n0an';'21ann0';'21ann0';'021ann';'021ann';'21an0n';'21an0n';'21a0nn';'21a0nn';'21nan0';'21nan0';'021nan';'021nan';'20nna1';'20nna1';'20nn1a';'20nn1a';'20na1n';'20na1n';'20n1na';'20n1na';'20n1an';'20n1an';'20ann1';'20ann1';'20an1n';'20an1n';'20a1nn';'20a1nn';'20nan1';'20nan1';'12nna0';'12nna0';'012nna';'012nna';'12nn0a';'12nn0a';'12na0n';'12na0n';'12n0na';'12n0na';'12n0an';'12n0an';'12ann0';'12ann0';'012ann';'012ann';'12an0n';'12an0n';'12a0nn';'12a0nn';'12nan0';'12nan0';'012nan';'012nan';'10nna2';'10nna2';'10nn2a';'10nn2a';'10na2n';'10na2n';'10n2na';'10n2na';'10n2an';'10n2an';'10ann2';'10ann2';'10an2n';'10an2n';'10a2nn';'10a2nn';'10nan2';'10nan2';'2nna10';'2nna10';'02nna1';'02nna1';'2nna01';'2nna01';'2nn10a';'2nn10a';'2nn1a0';'2nn1a0';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn0a1';'2nn0a1';'2na10n';'2na10n';'2na1n0';'2na1n0';'02na1n';'02na1n';'2na01n';'2na01n';'2na0n1';'2na0n1';'2n10na';'2n10na';'2n10an';'2n10an';'2n1na0';'2n1na0';'02n1na';'02n1na';'2n01na';'2n01na';'2n1n0a';'2n1n0a';'2n1an0';'2n1an0';'02n1an';'02n1an';'2n01an';'2n01an';'2n1a0n';'2n1a0n';'2n0na1';'2n0na1';'2n0n1a';'2n0n1a';'2n0an1';'2n0an1';'2n0a1n';'2n0a1n';'2ann10';'2ann10';'02ann1';'02ann1';'2ann01';'2ann01';'2an10n';'2an10n';'2an1n0';'2an1n0';'02an1n';'02an1n';'2an01n';'2an01n';'2an0n1';'2an0n1';'2a10nn';'2a10nn';'2a1nn0';'2a1nn0';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a1n0n';'2a1n0n';'2a0nn1';'2a0nn1';'2a0n1n';'2a0n1n';'2nan10';'2nan10';'02nan1';'02nan1';'2nan01';'2nan01';'1nna20';'1nna20';'01nna2';'01nna2';'1nna02';'1nna02';'1nn20a';'1nn20a';'1nn2a0';'1nn2a0';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn0a2';'1nn0a2';'1na20n';'1na20n';'1na2n0';'1na2n0';'01na2n';'01na2n';'1na02n';'1na02n';'1na0n2';'1na0n2';'1n20na';'1n20na';'1n20an';'1n20an';'1n2na0';'1n2na0';'01n2na';'01n2na';'1n02na';'1n02na';'1n2n0a';'1n2n0a';'1n2an0';'1n2an0';'01n2an';'01n2an';'1n02an';'1n02an';'1n2a0n';'1n2a0n';'1n0na2';'1n0na2';'1n0n2a';'1n0n2a';'1n0an2';'1n0an2';'1n0a2n';'1n0a2n';'1ann20';'1ann20';'01ann2';'01ann2';'1ann02';'1ann02';'1an20n';'1an20n';'1an2n0';'1an2n0';'01an2n';'01an2n';'1an02n';'1an02n';'1an0n2';'1an0n2';'1a20nn';'1a20nn';'1a2nn0';'1a2nn0';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a2n0n';'1a2n0n';'1a0nn2';'1a0nn2';'1a0n2n';'1a0n2n';'1nan20';'1nan20';'01nan2';'01nan2';'1nan02';'1nan02';'0nna21';'0nna21';'0nna12';'0nna12';'0nn21a';'0nn21a';'0nn12a';'0nn12a';'0nn2a1';'0nn2a1';'0nn1a2';'0nn1a2';'0na21n';'0na21n';'0na12n';'0na12n';'0na2n1';'0na2n1';'0na1n2';'0na1n2';'0n21na';'0n21na';'0n21an';'0n21an';'0n12na';'0n12na';'0n12an';'0n12an';'0n2na1';'0n2na1';'0n2n1a';'0n2n1a';'0n2an1';'0n2an1';'0n2a1n';'0n2a1n';'0n1na2';'0n1na2';'0n1n2a';'0n1n2a';'0n1an2';'0n1an2';'0n1a2n';'0n1a2n';'0ann21';'0ann21';'0ann12';'0ann12';'0an21n';'0an21n';'0an12n';'0an12n';'0an2n1';'0an2n1';'0an1n2';'0an1n2';'0a21nn';'0a21nn';'0a12nn';'0a12nn';'0a2nn1';'0a2nn1';'0a2n1n';'0a2n1n';'0a1nn2';'0a1nn2';'0a1n2n';'0a1n2n';'0nan21';'0nan21';'0nan12';'0nan12'}, ...
	[150;270;149;269;148;268;147;267;146;266;145;265;168;288;166;286;162;282;160;280;167;287;156;276;165;285;161;281;154;274;159;279;164;284;155;163;275;283;158;278;153;157;273;277;152;272;151;271;144;264;142;262;138;258;136;256;143;263;132;252;141;261;137;257;130;250;135;255;140;260;131;139;251;259;134;254;129;133;249;253;128;248;127;247;240;360;239;359;234;354;233;353;216;336;215;335;210;330;209;329;237;357;192;312;238;358;235;355;191;311;236;356;231;351;232;352;229;349;230;350;213;333;186;306;214;334;211;331;185;305;212;332;207;327;208;328;205;325;206;326;224;344;189;223;309;343;228;348;227;347;190;226;310;346;225;345;218;338;187;217;307;337;222;342;221;341;188;220;308;340;219;339;200;320;183;199;303;319;204;324;203;323;184;202;304;322;201;321;194;314;181;193;301;313;198;318;197;317;182;196;302;316;195;315;176;296;175;295;180;300;178;298;179;299;177;297;170;290;169;289;174;294;172;292;173;293;171;291;6;30;5;29;4;28;3;27;2;26;1;25;24;48;22;46;18;42;16;40;23;47;12;36;21;45;17;41;10;34;15;39;20;44;11;19;35;43;14;38;9;13;33;37;8;32;7;31;119;120;113;114;95;96;89;90;115;117;71;72;116;118;109;111;110;112;91;93;65;66;92;94;85;87;86;88;98;104;67;69;97;103;102;108;101;107;68;70;100;106;99;105;74;80;61;63;73;79;78;84;77;83;62;64;76;82;75;81;50;56;49;55;54;60;52;58;53;59;51;57;126;246;125;245;124;244;123;243;122;242;121;241;718;720;715;716;717;719;694;696;691;692;693;695;598;600;595;596;597;599;574;576;571;572;573;575;705;711;478;480;706;712;704;710;708;714;707;713;697;699;475;476;698;700;701;702;703;709;477;479;681;687;682;688;680;686;684;690;683;689;673;675;674;676;677;678;679;685;585;591;454;456;586;592;584;590;588;594;587;593;577;579;451;452;578;580;581;582;583;589;453;455;561;567;562;568;560;566;564;570;563;569;553;555;554;556;557;558;559;565;632;656;465;471;631;655;636;660;635;659;466;472;634;658;633;657;630;654;629;653;464;470;628;652;627;651;648;672;647;671;645;669;468;474;642;666;646;670;643;667;467;473;641;665;644;668;639;663;640;664;637;661;638;662;602;608;457;459;601;607;606;612;605;611;458;460;604;610;603;609;623;624;619;621;461;462;617;618;620;622;613;615;614;616;626;650;463;469;625;649;512;536;441;447;511;535;516;540;515;539;442;448;514;538;513;537;510;534;509;533;440;446;508;532;507;531;528;552;527;551;525;549;444;450;522;546;526;550;523;547;443;449;521;545;524;548;519;543;520;544;517;541;518;542;482;488;433;435;481;487;486;492;485;491;434;436;484;490;483;489;503;504;499;501;437;438;497;498;500;502;493;495;494;496;506;530;439;445;505;529;392;416;391;415;396;420;394;418;395;419;393;417;390;414;388;412;389;413;387;411;408;432;407;431;402;426;401;425;405;429;406;430;403;427;404;428;399;423;400;424;397;421;398;422;362;368;361;367;366;372;364;370;365;371;363;369;383;384;377;378;379;381;380;382;373;375;374;376;386;410;385;409])
chk(P, 'NaN|\d+', 'ascend', 'char<num', 'num<NaN', fnh, ...
	{'ann012';'ann012';'ann021';'ann021';'ann102';'ann102';'ann120';'ann120';'ann201';'ann201';'ann210';'ann210';'an0n12';'an0n12';'an0n21';'an0n21';'an01n2';'an1n02';'an01n2';'an1n02';'an1n20';'an1n20';'an02n1';'an2n01';'an02n1';'an2n01';'an2n10';'an2n10';'an10n2';'an10n2';'an012n';'an012n';'an12n0';'an12n0';'an20n1';'an20n1';'an021n';'an021n';'an21n0';'an21n0';'an102n';'an102n';'an120n';'an120n';'an201n';'an201n';'an210n';'an210n';'a0nn12';'a0nn12';'a0nn21';'a0nn21';'a0n1n2';'a0n1n2';'a0n2n1';'a0n2n1';'a0n12n';'a0n12n';'a0n21n';'a0n21n';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a1nn20';'a1nn20';'a1n0n2';'a1n0n2';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n2n0';'a1n2n0';'a1n20n';'a1n20n';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a2nn10';'a2nn10';'a2n0n1';'a2n0n1';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n1n0';'a2n1n0';'a2n10n';'a2n10n';'a10nn2';'a10nn2';'a10n2n';'a10n2n';'a012nn';'a012nn';'a12nn0';'a12nn0';'a12n0n';'a12n0n';'a20nn1';'a20nn1';'a20n1n';'a20n1n';'a021nn';'a021nn';'a21nn0';'a21nn0';'a21n0n';'a21n0n';'a102nn';'a102nn';'a120nn';'a120nn';'a201nn';'a201nn';'a210nn';'a210nn';'na0n12';'na0n12';'na0n21';'na0n21';'na01n2';'na1n02';'na01n2';'na1n02';'na1n20';'na1n20';'na02n1';'na2n01';'na02n1';'na2n01';'na2n10';'na2n10';'na10n2';'na10n2';'na012n';'na012n';'na12n0';'na12n0';'na20n1';'na20n1';'na021n';'na021n';'na21n0';'na21n0';'na102n';'na102n';'na120n';'na120n';'na201n';'na201n';'na210n';'na210n';'nna012';'nna012';'nna021';'nna021';'nna102';'nna102';'nna120';'nna120';'nna201';'nna201';'nna210';'nna210';'nn0a12';'nn0a12';'nn0a21';'nn0a21';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn1a20';'nn1a20';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn2a10';'nn2a10';'nn10a2';'nn10a2';'nn012a';'nn012a';'nn12a0';'nn12a0';'nn20a1';'nn20a1';'nn021a';'nn021a';'nn21a0';'nn21a0';'nn102a';'nn102a';'nn120a';'nn120a';'nn201a';'nn201a';'nn210a';'nn210a';'n0an12';'n0an12';'n0an21';'n0an21';'n0a1n2';'n0a1n2';'n0a2n1';'n0a2n1';'n0a12n';'n0a12n';'n0a21n';'n0a21n';'n0na12';'n0na12';'n0na21';'n0na21';'n0n1a2';'n0n1a2';'n0n2a1';'n0n2a1';'n0n12a';'n0n12a';'n0n21a';'n0n21a';'n01an2';'n1an02';'n01an2';'n1an02';'n1an20';'n1an20';'n1a0n2';'n1a0n2';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a2n0';'n1a2n0';'n1a20n';'n1a20n';'n01na2';'n1na02';'n01na2';'n1na02';'n1na20';'n1na20';'n1n0a2';'n1n0a2';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n2a0';'n1n2a0';'n1n20a';'n1n20a';'n02an1';'n2an01';'n02an1';'n2an01';'n2an10';'n2an10';'n2a0n1';'n2a0n1';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a1n0';'n2a1n0';'n2a10n';'n2a10n';'n02na1';'n2na01';'n02na1';'n2na01';'n2na10';'n2na10';'n2n0a1';'n2n0a1';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n1a0';'n2n1a0';'n2n10a';'n2n10a';'n10an2';'n10an2';'n10a2n';'n10a2n';'n10na2';'n10na2';'n10n2a';'n10n2a';'n012an';'n012an';'n12an0';'n12an0';'n12a0n';'n12a0n';'n012na';'n012na';'n12na0';'n12na0';'n12n0a';'n12n0a';'n20an1';'n20an1';'n20a1n';'n20a1n';'n20na1';'n20na1';'n20n1a';'n20n1a';'n021an';'n021an';'n21an0';'n21an0';'n21a0n';'n21a0n';'n021na';'n021na';'n21na0';'n21na0';'n21n0a';'n21n0a';'n102an';'n102an';'n102na';'n102na';'n120an';'n120an';'n120na';'n120na';'n201an';'n201an';'n201na';'n201na';'n210an';'n210an';'n210na';'n210na';'0ann12';'0ann12';'0ann21';'0ann21';'0an1n2';'0an1n2';'0an2n1';'0an2n1';'0an12n';'0an12n';'0an21n';'0an21n';'0a1nn2';'0a1nn2';'0a1n2n';'0a1n2n';'0a2nn1';'0a2nn1';'0a2n1n';'0a2n1n';'0a12nn';'0a12nn';'0a21nn';'0a21nn';'0na1n2';'0na1n2';'0na2n1';'0na2n1';'0na12n';'0na12n';'0na21n';'0na21n';'0nna12';'0nna12';'0nna21';'0nna21';'0nn1a2';'0nn1a2';'0nn2a1';'0nn2a1';'0nn12a';'0nn12a';'0nn21a';'0nn21a';'0n1an2';'0n1an2';'0n1a2n';'0n1a2n';'0n1na2';'0n1na2';'0n1n2a';'0n1n2a';'0n2an1';'0n2an1';'0n2a1n';'0n2a1n';'0n2na1';'0n2na1';'0n2n1a';'0n2n1a';'0n12an';'0n12an';'0n12na';'0n12na';'0n21an';'0n21an';'0n21na';'0n21na';'0nan12';'0nan12';'0nan21';'0nan21';'01ann2';'01ann2';'1ann02';'1ann02';'1ann20';'1ann20';'1an0n2';'1an0n2';'01an2n';'01an2n';'1an02n';'1an02n';'1an2n0';'1an2n0';'1an20n';'1an20n';'1a0nn2';'1a0nn2';'1a0n2n';'1a0n2n';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a2nn0';'1a2nn0';'1a2n0n';'1a2n0n';'1a20nn';'1a20nn';'1na0n2';'1na0n2';'01na2n';'01na2n';'1na02n';'1na02n';'1na2n0';'1na2n0';'1na20n';'1na20n';'01nna2';'01nna2';'1nna02';'1nna02';'1nna20';'1nna20';'1nn0a2';'1nn0a2';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn2a0';'1nn2a0';'1nn20a';'1nn20a';'1n0an2';'1n0an2';'1n0a2n';'1n0a2n';'1n0na2';'1n0na2';'1n0n2a';'1n0n2a';'01n2an';'01n2an';'1n02an';'1n02an';'1n2an0';'1n2an0';'1n2a0n';'1n2a0n';'01n2na';'01n2na';'1n02na';'1n02na';'1n2na0';'1n2na0';'1n2n0a';'1n2n0a';'1n20an';'1n20an';'1n20na';'1n20na';'01nan2';'01nan2';'1nan02';'1nan02';'1nan20';'1nan20';'02ann1';'02ann1';'2ann01';'2ann01';'2ann10';'2ann10';'2an0n1';'2an0n1';'02an1n';'02an1n';'2an01n';'2an01n';'2an1n0';'2an1n0';'2an10n';'2an10n';'2a0nn1';'2a0nn1';'2a0n1n';'2a0n1n';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a1nn0';'2a1nn0';'2a1n0n';'2a1n0n';'2a10nn';'2a10nn';'2na0n1';'2na0n1';'02na1n';'02na1n';'2na01n';'2na01n';'2na1n0';'2na1n0';'2na10n';'2na10n';'02nna1';'02nna1';'2nna01';'2nna01';'2nna10';'2nna10';'2nn0a1';'2nn0a1';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn1a0';'2nn1a0';'2nn10a';'2nn10a';'2n0an1';'2n0an1';'2n0a1n';'2n0a1n';'2n0na1';'2n0na1';'2n0n1a';'2n0n1a';'02n1an';'02n1an';'2n01an';'2n01an';'2n1an0';'2n1an0';'2n1a0n';'2n1a0n';'02n1na';'02n1na';'2n01na';'2n01na';'2n1na0';'2n1na0';'2n1n0a';'2n1n0a';'2n10an';'2n10an';'2n10na';'2n10na';'02nan1';'02nan1';'2nan01';'2nan01';'2nan10';'2nan10';'10ann2';'10ann2';'10an2n';'10an2n';'10a2nn';'10a2nn';'10na2n';'10na2n';'10nna2';'10nna2';'10nn2a';'10nn2a';'10n2an';'10n2an';'10n2na';'10n2na';'10nan2';'10nan2';'012ann';'012ann';'12ann0';'12ann0';'12an0n';'12an0n';'12a0nn';'12a0nn';'12na0n';'12na0n';'012nna';'012nna';'12nna0';'12nna0';'12nn0a';'12nn0a';'12n0an';'12n0an';'12n0na';'12n0na';'012nan';'012nan';'12nan0';'12nan0';'20ann1';'20ann1';'20an1n';'20an1n';'20a1nn';'20a1nn';'20na1n';'20na1n';'20nna1';'20nna1';'20nn1a';'20nn1a';'20n1an';'20n1an';'20n1na';'20n1na';'20nan1';'20nan1';'021ann';'021ann';'21ann0';'21ann0';'21an0n';'21an0n';'21a0nn';'21a0nn';'21na0n';'21na0n';'021nna';'021nna';'21nna0';'21nna0';'21nn0a';'21nn0a';'21n0an';'21n0an';'21n0na';'21n0na';'021nan';'021nan';'21nan0';'21nan0';'102ann';'102ann';'102nna';'102nna';'102nan';'102nan';'120ann';'120ann';'120nna';'120nna';'120nan';'120nan';'201ann';'201ann';'201nna';'201nna';'201nan';'201nan';'210ann';'210ann';'210nna';'210nna';'210nan';'210nan';'nan012';'nan012';'nan021';'nan021';'nan102';'nan102';'nan120';'nan120';'nan201';'nan201';'nan210';'nan210'}, ...
	[1;25;2;26;3;27;4;28;5;29;6;30;7;31;8;32;9;13;33;37;14;38;11;19;35;43;20;44;15;39;10;34;17;41;21;45;12;36;23;47;16;40;18;42;22;46;24;48;49;55;50;56;51;57;53;59;52;58;54;60;61;63;73;79;74;80;75;81;62;64;76;82;77;83;78;84;67;69;97;103;98;104;99;105;68;70;100;106;101;107;102;108;85;87;86;88;65;66;91;93;92;94;109;111;110;112;71;72;115;117;116;118;89;90;95;96;113;114;119;120;127;247;128;248;129;133;249;253;134;254;131;139;251;259;140;260;135;255;130;250;137;257;141;261;132;252;143;263;136;256;138;258;142;262;144;264;145;265;146;266;147;267;148;268;149;269;150;270;151;271;152;272;153;157;273;277;158;278;155;163;275;283;164;284;159;279;154;274;161;281;165;285;156;276;167;287;160;280;162;282;166;286;168;288;169;289;170;290;171;291;173;293;172;292;174;294;175;295;176;296;177;297;179;299;178;298;180;300;181;193;301;313;194;314;195;315;182;196;302;316;197;317;198;318;183;199;303;319;200;320;201;321;184;202;304;322;203;323;204;324;187;217;307;337;218;338;219;339;188;220;308;340;221;341;222;342;189;223;309;343;224;344;225;345;190;226;310;346;227;347;228;348;205;325;206;326;207;327;208;328;185;305;211;331;212;332;186;306;213;333;214;334;229;349;230;350;231;351;232;352;191;311;235;355;236;356;192;312;237;357;238;358;209;329;210;330;215;335;216;336;233;353;234;354;239;359;240;360;361;367;362;368;363;369;365;371;364;370;366;372;373;375;374;376;379;381;380;382;377;378;383;384;387;411;389;413;388;412;390;414;391;415;392;416;393;417;395;419;394;418;396;420;397;421;398;422;399;423;400;424;403;427;404;428;405;429;406;430;401;425;402;426;407;431;408;432;385;409;386;410;433;435;481;487;482;488;483;489;434;436;484;490;485;491;486;492;493;495;494;496;437;438;497;498;499;501;500;502;503;504;507;531;440;446;508;532;509;533;510;534;441;447;511;535;512;536;513;537;442;448;514;538;515;539;516;540;517;541;518;542;519;543;520;544;443;449;521;545;523;547;524;548;444;450;522;546;525;549;526;550;527;551;528;552;439;445;505;529;506;530;457;459;601;607;602;608;603;609;458;460;604;610;605;611;606;612;613;615;614;616;461;462;617;618;619;621;620;622;623;624;627;651;464;470;628;652;629;653;630;654;465;471;631;655;632;656;633;657;466;472;634;658;635;659;636;660;637;661;638;662;639;663;640;664;467;473;641;665;643;667;644;668;468;474;642;666;645;669;646;670;647;671;648;672;463;469;625;649;626;650;553;555;554;556;557;558;560;566;561;567;562;568;563;569;564;570;559;565;451;452;577;579;578;580;581;582;584;590;454;456;585;591;586;592;587;593;588;594;453;455;583;589;673;675;674;676;677;678;680;686;681;687;682;688;683;689;684;690;679;685;475;476;697;699;698;700;701;702;704;710;478;480;705;711;706;712;707;713;708;714;477;479;703;709;571;572;574;576;573;575;595;596;598;600;597;599;691;692;694;696;693;695;715;716;718;720;717;719;121;241;122;242;123;243;124;244;125;245;126;246])
chk(P, 'NaN|\d+', 'descend', 'char<num', 'num<NaN', fnh, ...
	{'nan210';'nan210';'nan201';'nan201';'nan120';'nan120';'nan102';'nan102';'nan021';'nan021';'nan012';'nan012';'210nan';'210nan';'210nna';'210nna';'210ann';'210ann';'201nan';'201nan';'201nna';'201nna';'201ann';'201ann';'120nan';'120nan';'120nna';'120nna';'120ann';'120ann';'102nan';'102nan';'102nna';'102nna';'102ann';'102ann';'21nan0';'21nan0';'021nan';'021nan';'21n0na';'21n0na';'21n0an';'21n0an';'21nn0a';'21nn0a';'21nna0';'21nna0';'021nna';'021nna';'21na0n';'21na0n';'21a0nn';'21a0nn';'21an0n';'21an0n';'21ann0';'21ann0';'021ann';'021ann';'20nan1';'20nan1';'20n1na';'20n1na';'20n1an';'20n1an';'20nn1a';'20nn1a';'20nna1';'20nna1';'20na1n';'20na1n';'20a1nn';'20a1nn';'20an1n';'20an1n';'20ann1';'20ann1';'12nan0';'12nan0';'012nan';'012nan';'12n0na';'12n0na';'12n0an';'12n0an';'12nn0a';'12nn0a';'12nna0';'12nna0';'012nna';'012nna';'12na0n';'12na0n';'12a0nn';'12a0nn';'12an0n';'12an0n';'12ann0';'12ann0';'012ann';'012ann';'10nan2';'10nan2';'10n2na';'10n2na';'10n2an';'10n2an';'10nn2a';'10nn2a';'10nna2';'10nna2';'10na2n';'10na2n';'10a2nn';'10a2nn';'10an2n';'10an2n';'10ann2';'10ann2';'2nan10';'2nan10';'02nan1';'02nan1';'2nan01';'2nan01';'2n10na';'2n10na';'2n10an';'2n10an';'2n1n0a';'2n1n0a';'2n1na0';'2n1na0';'02n1na';'02n1na';'2n01na';'2n01na';'2n1a0n';'2n1a0n';'2n1an0';'2n1an0';'02n1an';'02n1an';'2n01an';'2n01an';'2n0n1a';'2n0n1a';'2n0na1';'2n0na1';'2n0a1n';'2n0a1n';'2n0an1';'2n0an1';'2nn10a';'2nn10a';'2nn1a0';'2nn1a0';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn0a1';'2nn0a1';'2nna10';'2nna10';'02nna1';'02nna1';'2nna01';'2nna01';'2na10n';'2na10n';'2na1n0';'2na1n0';'02na1n';'02na1n';'2na01n';'2na01n';'2na0n1';'2na0n1';'2a10nn';'2a10nn';'2a1n0n';'2a1n0n';'2a1nn0';'2a1nn0';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a0n1n';'2a0n1n';'2a0nn1';'2a0nn1';'2an10n';'2an10n';'2an1n0';'2an1n0';'02an1n';'02an1n';'2an01n';'2an01n';'2an0n1';'2an0n1';'2ann10';'2ann10';'02ann1';'02ann1';'2ann01';'2ann01';'1nan20';'1nan20';'01nan2';'01nan2';'1nan02';'1nan02';'1n20na';'1n20na';'1n20an';'1n20an';'1n2n0a';'1n2n0a';'1n2na0';'1n2na0';'01n2na';'01n2na';'1n02na';'1n02na';'1n2a0n';'1n2a0n';'1n2an0';'1n2an0';'01n2an';'01n2an';'1n02an';'1n02an';'1n0n2a';'1n0n2a';'1n0na2';'1n0na2';'1n0a2n';'1n0a2n';'1n0an2';'1n0an2';'1nn20a';'1nn20a';'1nn2a0';'1nn2a0';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn0a2';'1nn0a2';'1nna20';'1nna20';'01nna2';'01nna2';'1nna02';'1nna02';'1na20n';'1na20n';'1na2n0';'1na2n0';'01na2n';'01na2n';'1na02n';'1na02n';'1na0n2';'1na0n2';'1a20nn';'1a20nn';'1a2n0n';'1a2n0n';'1a2nn0';'1a2nn0';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a0n2n';'1a0n2n';'1a0nn2';'1a0nn2';'1an20n';'1an20n';'1an2n0';'1an2n0';'01an2n';'01an2n';'1an02n';'1an02n';'1an0n2';'1an0n2';'1ann20';'1ann20';'01ann2';'01ann2';'1ann02';'1ann02';'0nan21';'0nan21';'0nan12';'0nan12';'0n21na';'0n21na';'0n21an';'0n21an';'0n12na';'0n12na';'0n12an';'0n12an';'0n2n1a';'0n2n1a';'0n2na1';'0n2na1';'0n2a1n';'0n2a1n';'0n2an1';'0n2an1';'0n1n2a';'0n1n2a';'0n1na2';'0n1na2';'0n1a2n';'0n1a2n';'0n1an2';'0n1an2';'0nn21a';'0nn21a';'0nn12a';'0nn12a';'0nn2a1';'0nn2a1';'0nn1a2';'0nn1a2';'0nna21';'0nna21';'0nna12';'0nna12';'0na21n';'0na21n';'0na12n';'0na12n';'0na2n1';'0na2n1';'0na1n2';'0na1n2';'0a21nn';'0a21nn';'0a12nn';'0a12nn';'0a2n1n';'0a2n1n';'0a2nn1';'0a2nn1';'0a1n2n';'0a1n2n';'0a1nn2';'0a1nn2';'0an21n';'0an21n';'0an12n';'0an12n';'0an2n1';'0an2n1';'0an1n2';'0an1n2';'0ann21';'0ann21';'0ann12';'0ann12';'n210na';'n210na';'n210an';'n210an';'n201na';'n201na';'n201an';'n201an';'n120na';'n120na';'n120an';'n120an';'n102na';'n102na';'n102an';'n102an';'n21n0a';'n21n0a';'n21na0';'n21na0';'n021na';'n021na';'n21a0n';'n21a0n';'n21an0';'n21an0';'n021an';'n021an';'n20n1a';'n20n1a';'n20na1';'n20na1';'n20a1n';'n20a1n';'n20an1';'n20an1';'n12n0a';'n12n0a';'n12na0';'n12na0';'n012na';'n012na';'n12a0n';'n12a0n';'n12an0';'n12an0';'n012an';'n012an';'n10n2a';'n10n2a';'n10na2';'n10na2';'n10a2n';'n10a2n';'n10an2';'n10an2';'n2n10a';'n2n10a';'n2n1a0';'n2n1a0';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n0a1';'n2n0a1';'n2na10';'n2na10';'n02na1';'n2na01';'n02na1';'n2na01';'n2a10n';'n2a10n';'n2a1n0';'n2a1n0';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a0n1';'n2a0n1';'n2an10';'n2an10';'n02an1';'n2an01';'n02an1';'n2an01';'n1n20a';'n1n20a';'n1n2a0';'n1n2a0';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n0a2';'n1n0a2';'n1na20';'n1na20';'n01na2';'n1na02';'n01na2';'n1na02';'n1a20n';'n1a20n';'n1a2n0';'n1a2n0';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a0n2';'n1a0n2';'n1an20';'n1an20';'n01an2';'n1an02';'n01an2';'n1an02';'n0n21a';'n0n21a';'n0n12a';'n0n12a';'n0n2a1';'n0n2a1';'n0n1a2';'n0n1a2';'n0na21';'n0na21';'n0na12';'n0na12';'n0a21n';'n0a21n';'n0a12n';'n0a12n';'n0a2n1';'n0a2n1';'n0a1n2';'n0a1n2';'n0an21';'n0an21';'n0an12';'n0an12';'nn210a';'nn210a';'nn201a';'nn201a';'nn120a';'nn120a';'nn102a';'nn102a';'nn21a0';'nn21a0';'nn021a';'nn021a';'nn20a1';'nn20a1';'nn12a0';'nn12a0';'nn012a';'nn012a';'nn10a2';'nn10a2';'nn2a10';'nn2a10';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn1a20';'nn1a20';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn0a21';'nn0a21';'nn0a12';'nn0a12';'nna210';'nna210';'nna201';'nna201';'nna120';'nna120';'nna102';'nna102';'nna021';'nna021';'nna012';'nna012';'na210n';'na210n';'na201n';'na201n';'na120n';'na120n';'na102n';'na102n';'na21n0';'na21n0';'na021n';'na021n';'na20n1';'na20n1';'na12n0';'na12n0';'na012n';'na012n';'na10n2';'na10n2';'na2n10';'na2n10';'na02n1';'na2n01';'na02n1';'na2n01';'na1n20';'na1n20';'na01n2';'na1n02';'na01n2';'na1n02';'na0n21';'na0n21';'na0n12';'na0n12';'a210nn';'a210nn';'a201nn';'a201nn';'a120nn';'a120nn';'a102nn';'a102nn';'a21n0n';'a21n0n';'a21nn0';'a21nn0';'a021nn';'a021nn';'a20n1n';'a20n1n';'a20nn1';'a20nn1';'a12n0n';'a12n0n';'a12nn0';'a12nn0';'a012nn';'a012nn';'a10n2n';'a10n2n';'a10nn2';'a10nn2';'a2n10n';'a2n10n';'a2n1n0';'a2n1n0';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n0n1';'a2n0n1';'a2nn10';'a2nn10';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a1n20n';'a1n20n';'a1n2n0';'a1n2n0';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n0n2';'a1n0n2';'a1nn20';'a1nn20';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a0n21n';'a0n21n';'a0n12n';'a0n12n';'a0n2n1';'a0n2n1';'a0n1n2';'a0n1n2';'a0nn21';'a0nn21';'a0nn12';'a0nn12';'an210n';'an210n';'an201n';'an201n';'an120n';'an120n';'an102n';'an102n';'an21n0';'an21n0';'an021n';'an021n';'an20n1';'an20n1';'an12n0';'an12n0';'an012n';'an012n';'an10n2';'an10n2';'an2n10';'an2n10';'an02n1';'an2n01';'an02n1';'an2n01';'an1n20';'an1n20';'an01n2';'an1n02';'an01n2';'an1n02';'an0n21';'an0n21';'an0n12';'an0n12';'ann210';'ann210';'ann201';'ann201';'ann120';'ann120';'ann102';'ann102';'ann021';'ann021';'ann012';'ann012'}, ...
	[126;246;125;245;124;244;123;243;122;242;121;241;717;719;718;720;715;716;693;695;694;696;691;692;597;599;598;600;595;596;573;575;574;576;571;572;703;709;477;479;708;714;707;713;706;712;705;711;478;480;704;710;701;702;698;700;697;699;475;476;679;685;684;690;683;689;682;688;681;687;680;686;677;678;674;676;673;675;583;589;453;455;588;594;587;593;586;592;585;591;454;456;584;590;581;582;578;580;577;579;451;452;559;565;564;570;563;569;562;568;561;567;560;566;557;558;554;556;553;555;626;650;463;469;625;649;648;672;647;671;646;670;645;669;468;474;642;666;644;668;643;667;467;473;641;665;640;664;639;663;638;662;637;661;636;660;635;659;466;472;634;658;633;657;632;656;465;471;631;655;630;654;629;653;464;470;628;652;627;651;623;624;620;622;619;621;461;462;617;618;614;616;613;615;606;612;605;611;458;460;604;610;603;609;602;608;457;459;601;607;506;530;439;445;505;529;528;552;527;551;526;550;525;549;444;450;522;546;524;548;523;547;443;449;521;545;520;544;519;543;518;542;517;541;516;540;515;539;442;448;514;538;513;537;512;536;441;447;511;535;510;534;509;533;440;446;508;532;507;531;503;504;500;502;499;501;437;438;497;498;494;496;493;495;486;492;485;491;434;436;484;490;483;489;482;488;433;435;481;487;386;410;385;409;408;432;407;431;402;426;401;425;406;430;405;429;404;428;403;427;400;424;399;423;398;422;397;421;396;420;394;418;395;419;393;417;392;416;391;415;390;414;388;412;389;413;387;411;383;384;377;378;380;382;379;381;374;376;373;375;366;372;364;370;365;371;363;369;362;368;361;367;240;360;239;359;234;354;233;353;216;336;215;335;210;330;209;329;238;358;237;357;192;312;236;356;235;355;191;311;232;352;231;351;230;350;229;349;214;334;213;333;186;306;212;332;211;331;185;305;208;328;207;327;206;326;205;325;228;348;227;347;190;226;310;346;225;345;224;344;189;223;309;343;222;342;221;341;188;220;308;340;219;339;218;338;187;217;307;337;204;324;203;323;184;202;304;322;201;321;200;320;183;199;303;319;198;318;197;317;182;196;302;316;195;315;194;314;181;193;301;313;180;300;178;298;179;299;177;297;176;296;175;295;174;294;172;292;173;293;171;291;170;290;169;289;168;288;166;286;162;282;160;280;167;287;156;276;165;285;161;281;154;274;159;279;164;284;155;163;275;283;158;278;153;157;273;277;152;272;151;271;150;270;149;269;148;268;147;267;146;266;145;265;144;264;142;262;138;258;136;256;143;263;132;252;141;261;137;257;130;250;135;255;140;260;131;139;251;259;134;254;129;133;249;253;128;248;127;247;119;120;113;114;95;96;89;90;116;118;115;117;71;72;110;112;109;111;92;94;91;93;65;66;86;88;85;87;102;108;101;107;68;70;100;106;99;105;98;104;67;69;97;103;78;84;77;83;62;64;76;82;75;81;74;80;61;63;73;79;54;60;52;58;53;59;51;57;50;56;49;55;24;48;22;46;18;42;16;40;23;47;12;36;21;45;17;41;10;34;15;39;20;44;11;19;35;43;14;38;9;13;33;37;8;32;7;31;6;30;5;29;4;28;3;27;2;26;1;25])
% The random NaNs will give different outputs:
chk(P, 'NaN|\d+', 'ascend', 'num<char', 'NaN<num', fnh, ...
	{'nan012';'nan012';'nan021';'nan021';'nan102';'nan102';'nan120';'nan120';'nan201';'nan201';'nan210';'nan210';'0nan12';'0nan12';'0nan21';'0nan21';'0a1n2n';'0a1n2n';'0a1nn2';'0a1nn2';'0a2n1n';'0a2n1n';'0a2nn1';'0a2nn1';'0a12nn';'0a12nn';'0a21nn';'0a21nn';'0an1n2';'0an1n2';'0an2n1';'0an2n1';'0an12n';'0an12n';'0an21n';'0an21n';'0ann12';'0ann12';'0ann21';'0ann21';'0n1a2n';'0n1a2n';'0n1an2';'0n1an2';'0n1n2a';'0n1n2a';'0n1na2';'0n1na2';'0n2a1n';'0n2a1n';'0n2an1';'0n2an1';'0n2n1a';'0n2n1a';'0n2na1';'0n2na1';'0n12an';'0n12an';'0n12na';'0n12na';'0n21an';'0n21an';'0n21na';'0n21na';'0na1n2';'0na1n2';'0na2n1';'0na2n1';'0na12n';'0na12n';'0na21n';'0na21n';'0nn1a2';'0nn1a2';'0nn2a1';'0nn2a1';'0nn12a';'0nn12a';'0nn21a';'0nn21a';'0nna12';'0nna12';'0nna21';'0nna21';'01nan2';'01nan2';'1nan02';'1nan02';'1nan20';'1nan20';'1a0n2n';'1a0n2n';'1a0nn2';'1a0nn2';'1a2n0n';'1a2n0n';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a2nn0';'1a2nn0';'1a20nn';'1a20nn';'1an0n2';'1an0n2';'01an2n';'01an2n';'1an02n';'1an02n';'1an2n0';'1an2n0';'1an20n';'1an20n';'01ann2';'01ann2';'1ann02';'1ann02';'1ann20';'1ann20';'1n0a2n';'1n0a2n';'1n0an2';'1n0an2';'1n0n2a';'1n0n2a';'1n0na2';'1n0na2';'1n2a0n';'1n2a0n';'01n2an';'01n2an';'1n02an';'1n02an';'1n2an0';'1n2an0';'1n2n0a';'1n2n0a';'01n2na';'01n2na';'1n02na';'1n02na';'1n2na0';'1n2na0';'1n20an';'1n20an';'1n20na';'1n20na';'1na0n2';'1na0n2';'01na2n';'01na2n';'1na02n';'1na02n';'1na2n0';'1na2n0';'1na20n';'1na20n';'1nn0a2';'1nn0a2';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn2a0';'1nn2a0';'1nn20a';'1nn20a';'01nna2';'01nna2';'1nna02';'1nna02';'1nna20';'1nna20';'02nan1';'02nan1';'2nan01';'2nan01';'2nan10';'2nan10';'2a0n1n';'2a0n1n';'2a0nn1';'2a0nn1';'2a1n0n';'2a1n0n';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a1nn0';'2a1nn0';'2a10nn';'2a10nn';'2an0n1';'2an0n1';'02an1n';'02an1n';'2an01n';'2an01n';'2an1n0';'2an1n0';'2an10n';'2an10n';'02ann1';'02ann1';'2ann01';'2ann01';'2ann10';'2ann10';'2n0a1n';'2n0a1n';'2n0an1';'2n0an1';'2n0n1a';'2n0n1a';'2n0na1';'2n0na1';'2n1a0n';'2n1a0n';'02n1an';'02n1an';'2n01an';'2n01an';'2n1an0';'2n1an0';'2n1n0a';'2n1n0a';'02n1na';'02n1na';'2n01na';'2n01na';'2n1na0';'2n1na0';'2n10an';'2n10an';'2n10na';'2n10na';'2na0n1';'2na0n1';'02na1n';'02na1n';'2na01n';'2na01n';'2na1n0';'2na1n0';'2na10n';'2na10n';'2nn0a1';'2nn0a1';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn1a0';'2nn1a0';'2nn10a';'2nn10a';'02nna1';'02nna1';'2nna01';'2nna01';'2nna10';'2nna10';'10nan2';'10nan2';'10a2nn';'10a2nn';'10an2n';'10an2n';'10ann2';'10ann2';'10n2an';'10n2an';'10n2na';'10n2na';'10na2n';'10na2n';'10nn2a';'10nn2a';'10nna2';'10nna2';'012nan';'012nan';'12nan0';'12nan0';'12a0nn';'12a0nn';'12an0n';'12an0n';'012ann';'012ann';'12ann0';'12ann0';'12n0an';'12n0an';'12n0na';'12n0na';'12na0n';'12na0n';'12nn0a';'12nn0a';'012nna';'012nna';'12nna0';'12nna0';'20nan1';'20nan1';'20a1nn';'20a1nn';'20an1n';'20an1n';'20ann1';'20ann1';'20n1an';'20n1an';'20n1na';'20n1na';'20na1n';'20na1n';'20nn1a';'20nn1a';'20nna1';'20nna1';'021nan';'021nan';'21nan0';'21nan0';'21a0nn';'21a0nn';'21an0n';'21an0n';'021ann';'021ann';'21ann0';'21ann0';'21n0an';'21n0an';'21n0na';'21n0na';'21na0n';'21na0n';'21nn0a';'21nn0a';'021nna';'021nna';'21nna0';'21nna0';'102nan';'102nan';'102ann';'102ann';'102nna';'102nna';'120nan';'120nan';'120ann';'120ann';'120nna';'120nna';'201nan';'201nan';'201ann';'201ann';'201nna';'201nna';'210nan';'210nan';'210ann';'210ann';'210nna';'210nna';'a0n1n2';'a0n1n2';'a0n2n1';'a0n2n1';'a0n12n';'a0n12n';'a0n21n';'a0n21n';'a0nn12';'a0nn12';'a0nn21';'a0nn21';'a1n0n2';'a1n0n2';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n2n0';'a1n2n0';'a1n20n';'a1n20n';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a1nn20';'a1nn20';'a2n0n1';'a2n0n1';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n1n0';'a2n1n0';'a2n10n';'a2n10n';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a2nn10';'a2nn10';'a10n2n';'a10n2n';'a10nn2';'a10nn2';'a12n0n';'a12n0n';'a012nn';'a012nn';'a12nn0';'a12nn0';'a20n1n';'a20n1n';'a20nn1';'a20nn1';'a21n0n';'a21n0n';'a021nn';'a021nn';'a21nn0';'a21nn0';'a102nn';'a102nn';'a120nn';'a120nn';'a201nn';'a201nn';'a210nn';'a210nn';'an0n12';'an0n12';'an0n21';'an0n21';'an01n2';'an1n02';'an01n2';'an1n02';'an1n20';'an1n20';'an02n1';'an2n01';'an02n1';'an2n01';'an2n10';'an2n10';'an10n2';'an10n2';'an012n';'an012n';'an12n0';'an12n0';'an20n1';'an20n1';'an021n';'an021n';'an21n0';'an21n0';'an102n';'an102n';'an120n';'an120n';'an201n';'an201n';'an210n';'an210n';'ann012';'ann012';'ann021';'ann021';'ann102';'ann102';'ann120';'ann120';'ann201';'ann201';'ann210';'ann210';'n0a1n2';'n0a1n2';'n0a2n1';'n0a2n1';'n0a12n';'n0a12n';'n0a21n';'n0a21n';'n0an12';'n0an12';'n0an21';'n0an21';'n0n1a2';'n0n1a2';'n0n2a1';'n0n2a1';'n0n12a';'n0n12a';'n0n21a';'n0n21a';'n0na12';'n0na12';'n0na21';'n0na21';'n1a0n2';'n1a0n2';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a2n0';'n1a2n0';'n1a20n';'n1a20n';'n01an2';'n1an02';'n01an2';'n1an02';'n1an20';'n1an20';'n1n0a2';'n1n0a2';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n2a0';'n1n2a0';'n1n20a';'n1n20a';'n01na2';'n1na02';'n01na2';'n1na02';'n1na20';'n1na20';'n2a0n1';'n2a0n1';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a1n0';'n2a1n0';'n2a10n';'n2a10n';'n02an1';'n2an01';'n02an1';'n2an01';'n2an10';'n2an10';'n2n0a1';'n2n0a1';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n1a0';'n2n1a0';'n2n10a';'n2n10a';'n02na1';'n2na01';'n02na1';'n2na01';'n2na10';'n2na10';'n10a2n';'n10a2n';'n10an2';'n10an2';'n10n2a';'n10n2a';'n10na2';'n10na2';'n12a0n';'n12a0n';'n012an';'n012an';'n12an0';'n12an0';'n12n0a';'n12n0a';'n012na';'n012na';'n12na0';'n12na0';'n20a1n';'n20a1n';'n20an1';'n20an1';'n20n1a';'n20n1a';'n20na1';'n20na1';'n21a0n';'n21a0n';'n021an';'n021an';'n21an0';'n21an0';'n21n0a';'n21n0a';'n021na';'n021na';'n21na0';'n21na0';'n102an';'n102an';'n102na';'n102na';'n120an';'n120an';'n120na';'n120na';'n201an';'n201an';'n201na';'n201na';'n210an';'n210an';'n210na';'n210na';'na0n12';'na0n12';'na0n21';'na0n21';'na01n2';'na1n02';'na01n2';'na1n02';'na1n20';'na1n20';'na02n1';'na2n01';'na02n1';'na2n01';'na2n10';'na2n10';'na10n2';'na10n2';'na012n';'na012n';'na12n0';'na12n0';'na20n1';'na20n1';'na021n';'na021n';'na21n0';'na21n0';'na102n';'na102n';'na120n';'na120n';'na201n';'na201n';'na210n';'na210n';'nn0a12';'nn0a12';'nn0a21';'nn0a21';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn1a20';'nn1a20';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn2a10';'nn2a10';'nn10a2';'nn10a2';'nn012a';'nn012a';'nn12a0';'nn12a0';'nn20a1';'nn20a1';'nn021a';'nn021a';'nn21a0';'nn21a0';'nn102a';'nn102a';'nn120a';'nn120a';'nn201a';'nn201a';'nn210a';'nn210a';'nna012';'nna012';'nna021';'nna021';'nna102';'nna102';'nna120';'nna120';'nna201';'nna201';'nna210';'nna210'}, ...
	[121;241;122;242;123;243;124;244;125;245;126;246;385;409;386;410;374;376;373;375;380;382;379;381;377;378;383;384;363;369;365;371;364;370;366;372;361;367;362;368;398;422;397;421;400;424;399;423;404;428;403;427;406;430;405;429;401;425;402;426;407;431;408;432;387;411;389;413;388;412;390;414;393;417;395;419;394;418;396;420;391;415;392;416;439;445;505;529;506;530;494;496;493;495;500;502;437;438;497;498;499;501;503;504;483;489;434;436;484;490;485;491;486;492;433;435;481;487;482;488;518;542;517;541;520;544;519;543;524;548;443;449;521;545;523;547;526;550;444;450;522;546;525;549;527;551;528;552;507;531;440;446;508;532;509;533;510;534;513;537;442;448;514;538;515;539;516;540;441;447;511;535;512;536;463;469;625;649;626;650;614;616;613;615;620;622;461;462;617;618;619;621;623;624;603;609;458;460;604;610;605;611;606;612;457;459;601;607;602;608;638;662;637;661;640;664;639;663;644;668;467;473;641;665;643;667;646;670;468;474;642;666;645;669;647;671;648;672;627;651;464;470;628;652;629;653;630;654;633;657;466;472;634;658;635;659;636;660;465;471;631;655;632;656;559;565;557;558;554;556;553;555;563;569;564;570;560;566;562;568;561;567;453;455;583;589;581;582;578;580;451;452;577;579;587;593;588;594;584;590;586;592;454;456;585;591;679;685;677;678;674;676;673;675;683;689;684;690;680;686;682;688;681;687;477;479;703;709;701;702;698;700;475;476;697;699;707;713;708;714;704;710;706;712;478;480;705;711;573;575;571;572;574;576;597;599;595;596;598;600;693;695;691;692;694;696;717;719;715;716;718;720;51;57;53;59;52;58;54;60;49;55;50;56;75;81;62;64;76;82;77;83;78;84;61;63;73;79;74;80;99;105;68;70;100;106;101;107;102;108;67;69;97;103;98;104;86;88;85;87;92;94;65;66;91;93;110;112;109;111;116;118;71;72;115;117;89;90;95;96;113;114;119;120;7;31;8;32;9;13;33;37;14;38;11;19;35;43;20;44;15;39;10;34;17;41;21;45;12;36;23;47;16;40;18;42;22;46;24;48;1;25;2;26;3;27;4;28;5;29;6;30;171;291;173;293;172;292;174;294;169;289;170;290;177;297;179;299;178;298;180;300;175;295;176;296;195;315;182;196;302;316;197;317;198;318;181;193;301;313;194;314;201;321;184;202;304;322;203;323;204;324;183;199;303;319;200;320;219;339;188;220;308;340;221;341;222;342;187;217;307;337;218;338;225;345;190;226;310;346;227;347;228;348;189;223;309;343;224;344;206;326;205;325;208;328;207;327;212;332;185;305;211;331;214;334;186;306;213;333;230;350;229;349;232;352;231;351;236;356;191;311;235;355;238;358;192;312;237;357;209;329;210;330;215;335;216;336;233;353;234;354;239;359;240;360;127;247;128;248;129;133;249;253;134;254;131;139;251;259;140;260;135;255;130;250;137;257;141;261;132;252;143;263;136;256;138;258;142;262;144;264;151;271;152;272;153;157;273;277;158;278;155;163;275;283;164;284;159;279;154;274;161;281;165;285;156;276;167;287;160;280;162;282;166;286;168;288;145;265;146;266;147;267;148;268;149;269;150;270])
chk(P, 'NaN|\d+', 'descend', 'num<char', 'NaN<num', fnh, ...
	{'nna210';'nna210';'nna201';'nna201';'nna120';'nna120';'nna102';'nna102';'nna021';'nna021';'nna012';'nna012';'nn210a';'nn210a';'nn201a';'nn201a';'nn120a';'nn120a';'nn102a';'nn102a';'nn21a0';'nn21a0';'nn021a';'nn021a';'nn20a1';'nn20a1';'nn12a0';'nn12a0';'nn012a';'nn012a';'nn10a2';'nn10a2';'nn2a10';'nn2a10';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn1a20';'nn1a20';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn0a21';'nn0a21';'nn0a12';'nn0a12';'na210n';'na210n';'na201n';'na201n';'na120n';'na120n';'na102n';'na102n';'na21n0';'na21n0';'na021n';'na021n';'na20n1';'na20n1';'na12n0';'na12n0';'na012n';'na012n';'na10n2';'na10n2';'na2n10';'na2n10';'na02n1';'na2n01';'na02n1';'na2n01';'na1n20';'na1n20';'na01n2';'na1n02';'na01n2';'na1n02';'na0n21';'na0n21';'na0n12';'na0n12';'n210na';'n210na';'n210an';'n210an';'n201na';'n201na';'n201an';'n201an';'n120na';'n120na';'n120an';'n120an';'n102na';'n102na';'n102an';'n102an';'n21na0';'n21na0';'n021na';'n021na';'n21n0a';'n21n0a';'n21an0';'n21an0';'n021an';'n021an';'n21a0n';'n21a0n';'n20na1';'n20na1';'n20n1a';'n20n1a';'n20an1';'n20an1';'n20a1n';'n20a1n';'n12na0';'n12na0';'n012na';'n012na';'n12n0a';'n12n0a';'n12an0';'n12an0';'n012an';'n012an';'n12a0n';'n12a0n';'n10na2';'n10na2';'n10n2a';'n10n2a';'n10an2';'n10an2';'n10a2n';'n10a2n';'n2na10';'n2na10';'n02na1';'n2na01';'n02na1';'n2na01';'n2n10a';'n2n10a';'n2n1a0';'n2n1a0';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n0a1';'n2n0a1';'n2an10';'n2an10';'n02an1';'n2an01';'n02an1';'n2an01';'n2a10n';'n2a10n';'n2a1n0';'n2a1n0';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a0n1';'n2a0n1';'n1na20';'n1na20';'n01na2';'n1na02';'n01na2';'n1na02';'n1n20a';'n1n20a';'n1n2a0';'n1n2a0';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n0a2';'n1n0a2';'n1an20';'n1an20';'n01an2';'n1an02';'n01an2';'n1an02';'n1a20n';'n1a20n';'n1a2n0';'n1a2n0';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a0n2';'n1a0n2';'n0na21';'n0na21';'n0na12';'n0na12';'n0n21a';'n0n21a';'n0n12a';'n0n12a';'n0n2a1';'n0n2a1';'n0n1a2';'n0n1a2';'n0an21';'n0an21';'n0an12';'n0an12';'n0a21n';'n0a21n';'n0a12n';'n0a12n';'n0a2n1';'n0a2n1';'n0a1n2';'n0a1n2';'ann210';'ann210';'ann201';'ann201';'ann120';'ann120';'ann102';'ann102';'ann021';'ann021';'ann012';'ann012';'an210n';'an210n';'an201n';'an201n';'an120n';'an120n';'an102n';'an102n';'an21n0';'an21n0';'an021n';'an021n';'an20n1';'an20n1';'an12n0';'an12n0';'an012n';'an012n';'an10n2';'an10n2';'an2n10';'an2n10';'an02n1';'an2n01';'an02n1';'an2n01';'an1n20';'an1n20';'an01n2';'an1n02';'an01n2';'an1n02';'an0n21';'an0n21';'an0n12';'an0n12';'a210nn';'a210nn';'a201nn';'a201nn';'a120nn';'a120nn';'a102nn';'a102nn';'a21nn0';'a21nn0';'a021nn';'a021nn';'a21n0n';'a21n0n';'a20nn1';'a20nn1';'a20n1n';'a20n1n';'a12nn0';'a12nn0';'a012nn';'a012nn';'a12n0n';'a12n0n';'a10nn2';'a10nn2';'a10n2n';'a10n2n';'a2nn10';'a2nn10';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a2n10n';'a2n10n';'a2n1n0';'a2n1n0';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n0n1';'a2n0n1';'a1nn20';'a1nn20';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a1n20n';'a1n20n';'a1n2n0';'a1n2n0';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n0n2';'a1n0n2';'a0nn21';'a0nn21';'a0nn12';'a0nn12';'a0n21n';'a0n21n';'a0n12n';'a0n12n';'a0n2n1';'a0n2n1';'a0n1n2';'a0n1n2';'210nna';'210nna';'210ann';'210ann';'210nan';'210nan';'201nna';'201nna';'201ann';'201ann';'201nan';'201nan';'120nna';'120nna';'120ann';'120ann';'120nan';'120nan';'102nna';'102nna';'102ann';'102ann';'102nan';'102nan';'21nna0';'21nna0';'021nna';'021nna';'21nn0a';'21nn0a';'21na0n';'21na0n';'21n0na';'21n0na';'21n0an';'21n0an';'21ann0';'21ann0';'021ann';'021ann';'21an0n';'21an0n';'21a0nn';'21a0nn';'21nan0';'21nan0';'021nan';'021nan';'20nna1';'20nna1';'20nn1a';'20nn1a';'20na1n';'20na1n';'20n1na';'20n1na';'20n1an';'20n1an';'20ann1';'20ann1';'20an1n';'20an1n';'20a1nn';'20a1nn';'20nan1';'20nan1';'12nna0';'12nna0';'012nna';'012nna';'12nn0a';'12nn0a';'12na0n';'12na0n';'12n0na';'12n0na';'12n0an';'12n0an';'12ann0';'12ann0';'012ann';'012ann';'12an0n';'12an0n';'12a0nn';'12a0nn';'12nan0';'12nan0';'012nan';'012nan';'10nna2';'10nna2';'10nn2a';'10nn2a';'10na2n';'10na2n';'10n2na';'10n2na';'10n2an';'10n2an';'10ann2';'10ann2';'10an2n';'10an2n';'10a2nn';'10a2nn';'10nan2';'10nan2';'2nna10';'2nna10';'02nna1';'02nna1';'2nna01';'2nna01';'2nn10a';'2nn10a';'2nn1a0';'2nn1a0';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn0a1';'2nn0a1';'2na10n';'2na10n';'2na1n0';'2na1n0';'02na1n';'02na1n';'2na01n';'2na01n';'2na0n1';'2na0n1';'2n10na';'2n10na';'2n10an';'2n10an';'2n1na0';'2n1na0';'02n1na';'02n1na';'2n01na';'2n01na';'2n1n0a';'2n1n0a';'2n1an0';'2n1an0';'02n1an';'02n1an';'2n01an';'2n01an';'2n1a0n';'2n1a0n';'2n0na1';'2n0na1';'2n0n1a';'2n0n1a';'2n0an1';'2n0an1';'2n0a1n';'2n0a1n';'2ann10';'2ann10';'02ann1';'02ann1';'2ann01';'2ann01';'2an10n';'2an10n';'2an1n0';'2an1n0';'02an1n';'02an1n';'2an01n';'2an01n';'2an0n1';'2an0n1';'2a10nn';'2a10nn';'2a1nn0';'2a1nn0';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a1n0n';'2a1n0n';'2a0nn1';'2a0nn1';'2a0n1n';'2a0n1n';'2nan10';'2nan10';'02nan1';'02nan1';'2nan01';'2nan01';'1nna20';'1nna20';'01nna2';'01nna2';'1nna02';'1nna02';'1nn20a';'1nn20a';'1nn2a0';'1nn2a0';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn0a2';'1nn0a2';'1na20n';'1na20n';'1na2n0';'1na2n0';'01na2n';'01na2n';'1na02n';'1na02n';'1na0n2';'1na0n2';'1n20na';'1n20na';'1n20an';'1n20an';'1n2na0';'1n2na0';'01n2na';'01n2na';'1n02na';'1n02na';'1n2n0a';'1n2n0a';'1n2an0';'1n2an0';'01n2an';'01n2an';'1n02an';'1n02an';'1n2a0n';'1n2a0n';'1n0na2';'1n0na2';'1n0n2a';'1n0n2a';'1n0an2';'1n0an2';'1n0a2n';'1n0a2n';'1ann20';'1ann20';'01ann2';'01ann2';'1ann02';'1ann02';'1an20n';'1an20n';'1an2n0';'1an2n0';'01an2n';'01an2n';'1an02n';'1an02n';'1an0n2';'1an0n2';'1a20nn';'1a20nn';'1a2nn0';'1a2nn0';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a2n0n';'1a2n0n';'1a0nn2';'1a0nn2';'1a0n2n';'1a0n2n';'1nan20';'1nan20';'01nan2';'01nan2';'1nan02';'1nan02';'0nna21';'0nna21';'0nna12';'0nna12';'0nn21a';'0nn21a';'0nn12a';'0nn12a';'0nn2a1';'0nn2a1';'0nn1a2';'0nn1a2';'0na21n';'0na21n';'0na12n';'0na12n';'0na2n1';'0na2n1';'0na1n2';'0na1n2';'0n21na';'0n21na';'0n21an';'0n21an';'0n12na';'0n12na';'0n12an';'0n12an';'0n2na1';'0n2na1';'0n2n1a';'0n2n1a';'0n2an1';'0n2an1';'0n2a1n';'0n2a1n';'0n1na2';'0n1na2';'0n1n2a';'0n1n2a';'0n1an2';'0n1an2';'0n1a2n';'0n1a2n';'0ann21';'0ann21';'0ann12';'0ann12';'0an21n';'0an21n';'0an12n';'0an12n';'0an2n1';'0an2n1';'0an1n2';'0an1n2';'0a21nn';'0a21nn';'0a12nn';'0a12nn';'0a2nn1';'0a2nn1';'0a2n1n';'0a2n1n';'0a1nn2';'0a1nn2';'0a1n2n';'0a1n2n';'0nan21';'0nan21';'0nan12';'0nan12';'nan210';'nan210';'nan201';'nan201';'nan120';'nan120';'nan102';'nan102';'nan021';'nan021';'nan012';'nan012'}, ...
	[150;270;149;269;148;268;147;267;146;266;145;265;168;288;166;286;162;282;160;280;167;287;156;276;165;285;161;281;154;274;159;279;164;284;155;163;275;283;158;278;153;157;273;277;152;272;151;271;144;264;142;262;138;258;136;256;143;263;132;252;141;261;137;257;130;250;135;255;140;260;131;139;251;259;134;254;129;133;249;253;128;248;127;247;240;360;239;359;234;354;233;353;216;336;215;335;210;330;209;329;237;357;192;312;238;358;235;355;191;311;236;356;231;351;232;352;229;349;230;350;213;333;186;306;214;334;211;331;185;305;212;332;207;327;208;328;205;325;206;326;224;344;189;223;309;343;228;348;227;347;190;226;310;346;225;345;218;338;187;217;307;337;222;342;221;341;188;220;308;340;219;339;200;320;183;199;303;319;204;324;203;323;184;202;304;322;201;321;194;314;181;193;301;313;198;318;197;317;182;196;302;316;195;315;176;296;175;295;180;300;178;298;179;299;177;297;170;290;169;289;174;294;172;292;173;293;171;291;6;30;5;29;4;28;3;27;2;26;1;25;24;48;22;46;18;42;16;40;23;47;12;36;21;45;17;41;10;34;15;39;20;44;11;19;35;43;14;38;9;13;33;37;8;32;7;31;119;120;113;114;95;96;89;90;115;117;71;72;116;118;109;111;110;112;91;93;65;66;92;94;85;87;86;88;98;104;67;69;97;103;102;108;101;107;68;70;100;106;99;105;74;80;61;63;73;79;78;84;77;83;62;64;76;82;75;81;50;56;49;55;54;60;52;58;53;59;51;57;718;720;715;716;717;719;694;696;691;692;693;695;598;600;595;596;597;599;574;576;571;572;573;575;705;711;478;480;706;712;704;710;708;714;707;713;697;699;475;476;698;700;701;702;703;709;477;479;681;687;682;688;680;686;684;690;683;689;673;675;674;676;677;678;679;685;585;591;454;456;586;592;584;590;588;594;587;593;577;579;451;452;578;580;581;582;583;589;453;455;561;567;562;568;560;566;564;570;563;569;553;555;554;556;557;558;559;565;632;656;465;471;631;655;636;660;635;659;466;472;634;658;633;657;630;654;629;653;464;470;628;652;627;651;648;672;647;671;645;669;468;474;642;666;646;670;643;667;467;473;641;665;644;668;639;663;640;664;637;661;638;662;602;608;457;459;601;607;606;612;605;611;458;460;604;610;603;609;623;624;619;621;461;462;617;618;620;622;613;615;614;616;626;650;463;469;625;649;512;536;441;447;511;535;516;540;515;539;442;448;514;538;513;537;510;534;509;533;440;446;508;532;507;531;528;552;527;551;525;549;444;450;522;546;526;550;523;547;443;449;521;545;524;548;519;543;520;544;517;541;518;542;482;488;433;435;481;487;486;492;485;491;434;436;484;490;483;489;503;504;499;501;437;438;497;498;500;502;493;495;494;496;506;530;439;445;505;529;392;416;391;415;396;420;394;418;395;419;393;417;390;414;388;412;389;413;387;411;408;432;407;431;402;426;401;425;405;429;406;430;403;427;404;428;399;423;400;424;397;421;398;422;362;368;361;367;366;372;364;370;365;371;363;369;383;384;377;378;379;381;380;382;373;375;374;376;386;410;385;409;126;246;125;245;124;244;123;243;122;242;121;241])
chk(P, 'NaN|\d+', 'ascend', 'char<num', 'NaN<num', fnh, ...
	{'ann012';'ann012';'ann021';'ann021';'ann102';'ann102';'ann120';'ann120';'ann201';'ann201';'ann210';'ann210';'an0n12';'an0n12';'an0n21';'an0n21';'an01n2';'an1n02';'an01n2';'an1n02';'an1n20';'an1n20';'an02n1';'an2n01';'an02n1';'an2n01';'an2n10';'an2n10';'an10n2';'an10n2';'an012n';'an012n';'an12n0';'an12n0';'an20n1';'an20n1';'an021n';'an021n';'an21n0';'an21n0';'an102n';'an102n';'an120n';'an120n';'an201n';'an201n';'an210n';'an210n';'a0nn12';'a0nn12';'a0nn21';'a0nn21';'a0n1n2';'a0n1n2';'a0n2n1';'a0n2n1';'a0n12n';'a0n12n';'a0n21n';'a0n21n';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a1nn20';'a1nn20';'a1n0n2';'a1n0n2';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n2n0';'a1n2n0';'a1n20n';'a1n20n';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a2nn10';'a2nn10';'a2n0n1';'a2n0n1';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n1n0';'a2n1n0';'a2n10n';'a2n10n';'a10nn2';'a10nn2';'a10n2n';'a10n2n';'a012nn';'a012nn';'a12nn0';'a12nn0';'a12n0n';'a12n0n';'a20nn1';'a20nn1';'a20n1n';'a20n1n';'a021nn';'a021nn';'a21nn0';'a21nn0';'a21n0n';'a21n0n';'a102nn';'a102nn';'a120nn';'a120nn';'a201nn';'a201nn';'a210nn';'a210nn';'na0n12';'na0n12';'na0n21';'na0n21';'na01n2';'na1n02';'na01n2';'na1n02';'na1n20';'na1n20';'na02n1';'na2n01';'na02n1';'na2n01';'na2n10';'na2n10';'na10n2';'na10n2';'na012n';'na012n';'na12n0';'na12n0';'na20n1';'na20n1';'na021n';'na021n';'na21n0';'na21n0';'na102n';'na102n';'na120n';'na120n';'na201n';'na201n';'na210n';'na210n';'nna012';'nna012';'nna021';'nna021';'nna102';'nna102';'nna120';'nna120';'nna201';'nna201';'nna210';'nna210';'nn0a12';'nn0a12';'nn0a21';'nn0a21';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn1a20';'nn1a20';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn2a10';'nn2a10';'nn10a2';'nn10a2';'nn012a';'nn012a';'nn12a0';'nn12a0';'nn20a1';'nn20a1';'nn021a';'nn021a';'nn21a0';'nn21a0';'nn102a';'nn102a';'nn120a';'nn120a';'nn201a';'nn201a';'nn210a';'nn210a';'n0an12';'n0an12';'n0an21';'n0an21';'n0a1n2';'n0a1n2';'n0a2n1';'n0a2n1';'n0a12n';'n0a12n';'n0a21n';'n0a21n';'n0na12';'n0na12';'n0na21';'n0na21';'n0n1a2';'n0n1a2';'n0n2a1';'n0n2a1';'n0n12a';'n0n12a';'n0n21a';'n0n21a';'n01an2';'n1an02';'n01an2';'n1an02';'n1an20';'n1an20';'n1a0n2';'n1a0n2';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a2n0';'n1a2n0';'n1a20n';'n1a20n';'n01na2';'n1na02';'n01na2';'n1na02';'n1na20';'n1na20';'n1n0a2';'n1n0a2';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n2a0';'n1n2a0';'n1n20a';'n1n20a';'n02an1';'n2an01';'n02an1';'n2an01';'n2an10';'n2an10';'n2a0n1';'n2a0n1';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a1n0';'n2a1n0';'n2a10n';'n2a10n';'n02na1';'n2na01';'n02na1';'n2na01';'n2na10';'n2na10';'n2n0a1';'n2n0a1';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n1a0';'n2n1a0';'n2n10a';'n2n10a';'n10an2';'n10an2';'n10a2n';'n10a2n';'n10na2';'n10na2';'n10n2a';'n10n2a';'n012an';'n012an';'n12an0';'n12an0';'n12a0n';'n12a0n';'n012na';'n012na';'n12na0';'n12na0';'n12n0a';'n12n0a';'n20an1';'n20an1';'n20a1n';'n20a1n';'n20na1';'n20na1';'n20n1a';'n20n1a';'n021an';'n021an';'n21an0';'n21an0';'n21a0n';'n21a0n';'n021na';'n021na';'n21na0';'n21na0';'n21n0a';'n21n0a';'n102an';'n102an';'n102na';'n102na';'n120an';'n120an';'n120na';'n120na';'n201an';'n201an';'n201na';'n201na';'n210an';'n210an';'n210na';'n210na';'nan012';'nan012';'nan021';'nan021';'nan102';'nan102';'nan120';'nan120';'nan201';'nan201';'nan210';'nan210';'0ann12';'0ann12';'0ann21';'0ann21';'0an1n2';'0an1n2';'0an2n1';'0an2n1';'0an12n';'0an12n';'0an21n';'0an21n';'0a1nn2';'0a1nn2';'0a1n2n';'0a1n2n';'0a2nn1';'0a2nn1';'0a2n1n';'0a2n1n';'0a12nn';'0a12nn';'0a21nn';'0a21nn';'0na1n2';'0na1n2';'0na2n1';'0na2n1';'0na12n';'0na12n';'0na21n';'0na21n';'0nna12';'0nna12';'0nna21';'0nna21';'0nn1a2';'0nn1a2';'0nn2a1';'0nn2a1';'0nn12a';'0nn12a';'0nn21a';'0nn21a';'0n1an2';'0n1an2';'0n1a2n';'0n1a2n';'0n1na2';'0n1na2';'0n1n2a';'0n1n2a';'0n2an1';'0n2an1';'0n2a1n';'0n2a1n';'0n2na1';'0n2na1';'0n2n1a';'0n2n1a';'0n12an';'0n12an';'0n12na';'0n12na';'0n21an';'0n21an';'0n21na';'0n21na';'0nan12';'0nan12';'0nan21';'0nan21';'01ann2';'01ann2';'1ann02';'1ann02';'1ann20';'1ann20';'1an0n2';'1an0n2';'01an2n';'01an2n';'1an02n';'1an02n';'1an2n0';'1an2n0';'1an20n';'1an20n';'1a0nn2';'1a0nn2';'1a0n2n';'1a0n2n';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a2nn0';'1a2nn0';'1a2n0n';'1a2n0n';'1a20nn';'1a20nn';'1na0n2';'1na0n2';'01na2n';'01na2n';'1na02n';'1na02n';'1na2n0';'1na2n0';'1na20n';'1na20n';'01nna2';'01nna2';'1nna02';'1nna02';'1nna20';'1nna20';'1nn0a2';'1nn0a2';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn2a0';'1nn2a0';'1nn20a';'1nn20a';'1n0an2';'1n0an2';'1n0a2n';'1n0a2n';'1n0na2';'1n0na2';'1n0n2a';'1n0n2a';'01n2an';'01n2an';'1n02an';'1n02an';'1n2an0';'1n2an0';'1n2a0n';'1n2a0n';'01n2na';'01n2na';'1n02na';'1n02na';'1n2na0';'1n2na0';'1n2n0a';'1n2n0a';'1n20an';'1n20an';'1n20na';'1n20na';'01nan2';'01nan2';'1nan02';'1nan02';'1nan20';'1nan20';'02ann1';'02ann1';'2ann01';'2ann01';'2ann10';'2ann10';'2an0n1';'2an0n1';'02an1n';'02an1n';'2an01n';'2an01n';'2an1n0';'2an1n0';'2an10n';'2an10n';'2a0nn1';'2a0nn1';'2a0n1n';'2a0n1n';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a1nn0';'2a1nn0';'2a1n0n';'2a1n0n';'2a10nn';'2a10nn';'2na0n1';'2na0n1';'02na1n';'02na1n';'2na01n';'2na01n';'2na1n0';'2na1n0';'2na10n';'2na10n';'02nna1';'02nna1';'2nna01';'2nna01';'2nna10';'2nna10';'2nn0a1';'2nn0a1';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn1a0';'2nn1a0';'2nn10a';'2nn10a';'2n0an1';'2n0an1';'2n0a1n';'2n0a1n';'2n0na1';'2n0na1';'2n0n1a';'2n0n1a';'02n1an';'02n1an';'2n01an';'2n01an';'2n1an0';'2n1an0';'2n1a0n';'2n1a0n';'02n1na';'02n1na';'2n01na';'2n01na';'2n1na0';'2n1na0';'2n1n0a';'2n1n0a';'2n10an';'2n10an';'2n10na';'2n10na';'02nan1';'02nan1';'2nan01';'2nan01';'2nan10';'2nan10';'10ann2';'10ann2';'10an2n';'10an2n';'10a2nn';'10a2nn';'10na2n';'10na2n';'10nna2';'10nna2';'10nn2a';'10nn2a';'10n2an';'10n2an';'10n2na';'10n2na';'10nan2';'10nan2';'012ann';'012ann';'12ann0';'12ann0';'12an0n';'12an0n';'12a0nn';'12a0nn';'12na0n';'12na0n';'012nna';'012nna';'12nna0';'12nna0';'12nn0a';'12nn0a';'12n0an';'12n0an';'12n0na';'12n0na';'012nan';'012nan';'12nan0';'12nan0';'20ann1';'20ann1';'20an1n';'20an1n';'20a1nn';'20a1nn';'20na1n';'20na1n';'20nna1';'20nna1';'20nn1a';'20nn1a';'20n1an';'20n1an';'20n1na';'20n1na';'20nan1';'20nan1';'021ann';'021ann';'21ann0';'21ann0';'21an0n';'21an0n';'21a0nn';'21a0nn';'21na0n';'21na0n';'021nna';'021nna';'21nna0';'21nna0';'21nn0a';'21nn0a';'21n0an';'21n0an';'21n0na';'21n0na';'021nan';'021nan';'21nan0';'21nan0';'102ann';'102ann';'102nna';'102nna';'102nan';'102nan';'120ann';'120ann';'120nna';'120nna';'120nan';'120nan';'201ann';'201ann';'201nna';'201nna';'201nan';'201nan';'210ann';'210ann';'210nna';'210nna';'210nan';'210nan'}, ...
	[1;25;2;26;3;27;4;28;5;29;6;30;7;31;8;32;9;13;33;37;14;38;11;19;35;43;20;44;15;39;10;34;17;41;21;45;12;36;23;47;16;40;18;42;22;46;24;48;49;55;50;56;51;57;53;59;52;58;54;60;61;63;73;79;74;80;75;81;62;64;76;82;77;83;78;84;67;69;97;103;98;104;99;105;68;70;100;106;101;107;102;108;85;87;86;88;65;66;91;93;92;94;109;111;110;112;71;72;115;117;116;118;89;90;95;96;113;114;119;120;127;247;128;248;129;133;249;253;134;254;131;139;251;259;140;260;135;255;130;250;137;257;141;261;132;252;143;263;136;256;138;258;142;262;144;264;145;265;146;266;147;267;148;268;149;269;150;270;151;271;152;272;153;157;273;277;158;278;155;163;275;283;164;284;159;279;154;274;161;281;165;285;156;276;167;287;160;280;162;282;166;286;168;288;169;289;170;290;171;291;173;293;172;292;174;294;175;295;176;296;177;297;179;299;178;298;180;300;181;193;301;313;194;314;195;315;182;196;302;316;197;317;198;318;183;199;303;319;200;320;201;321;184;202;304;322;203;323;204;324;187;217;307;337;218;338;219;339;188;220;308;340;221;341;222;342;189;223;309;343;224;344;225;345;190;226;310;346;227;347;228;348;205;325;206;326;207;327;208;328;185;305;211;331;212;332;186;306;213;333;214;334;229;349;230;350;231;351;232;352;191;311;235;355;236;356;192;312;237;357;238;358;209;329;210;330;215;335;216;336;233;353;234;354;239;359;240;360;121;241;122;242;123;243;124;244;125;245;126;246;361;367;362;368;363;369;365;371;364;370;366;372;373;375;374;376;379;381;380;382;377;378;383;384;387;411;389;413;388;412;390;414;391;415;392;416;393;417;395;419;394;418;396;420;397;421;398;422;399;423;400;424;403;427;404;428;405;429;406;430;401;425;402;426;407;431;408;432;385;409;386;410;433;435;481;487;482;488;483;489;434;436;484;490;485;491;486;492;493;495;494;496;437;438;497;498;499;501;500;502;503;504;507;531;440;446;508;532;509;533;510;534;441;447;511;535;512;536;513;537;442;448;514;538;515;539;516;540;517;541;518;542;519;543;520;544;443;449;521;545;523;547;524;548;444;450;522;546;525;549;526;550;527;551;528;552;439;445;505;529;506;530;457;459;601;607;602;608;603;609;458;460;604;610;605;611;606;612;613;615;614;616;461;462;617;618;619;621;620;622;623;624;627;651;464;470;628;652;629;653;630;654;465;471;631;655;632;656;633;657;466;472;634;658;635;659;636;660;637;661;638;662;639;663;640;664;467;473;641;665;643;667;644;668;468;474;642;666;645;669;646;670;647;671;648;672;463;469;625;649;626;650;553;555;554;556;557;558;560;566;561;567;562;568;563;569;564;570;559;565;451;452;577;579;578;580;581;582;584;590;454;456;585;591;586;592;587;593;588;594;453;455;583;589;673;675;674;676;677;678;680;686;681;687;682;688;683;689;684;690;679;685;475;476;697;699;698;700;701;702;704;710;478;480;705;711;706;712;707;713;708;714;477;479;703;709;571;572;574;576;573;575;595;596;598;600;597;599;691;692;694;696;693;695;715;716;718;720;717;719])
chk(P, 'NaN|\d+', 'descend', 'char<num', 'NaN<num', fnh, ...
	{'210nan';'210nan';'210nna';'210nna';'210ann';'210ann';'201nan';'201nan';'201nna';'201nna';'201ann';'201ann';'120nan';'120nan';'120nna';'120nna';'120ann';'120ann';'102nan';'102nan';'102nna';'102nna';'102ann';'102ann';'21nan0';'21nan0';'021nan';'021nan';'21n0na';'21n0na';'21n0an';'21n0an';'21nn0a';'21nn0a';'21nna0';'21nna0';'021nna';'021nna';'21na0n';'21na0n';'21a0nn';'21a0nn';'21an0n';'21an0n';'21ann0';'21ann0';'021ann';'021ann';'20nan1';'20nan1';'20n1na';'20n1na';'20n1an';'20n1an';'20nn1a';'20nn1a';'20nna1';'20nna1';'20na1n';'20na1n';'20a1nn';'20a1nn';'20an1n';'20an1n';'20ann1';'20ann1';'12nan0';'12nan0';'012nan';'012nan';'12n0na';'12n0na';'12n0an';'12n0an';'12nn0a';'12nn0a';'12nna0';'12nna0';'012nna';'012nna';'12na0n';'12na0n';'12a0nn';'12a0nn';'12an0n';'12an0n';'12ann0';'12ann0';'012ann';'012ann';'10nan2';'10nan2';'10n2na';'10n2na';'10n2an';'10n2an';'10nn2a';'10nn2a';'10nna2';'10nna2';'10na2n';'10na2n';'10a2nn';'10a2nn';'10an2n';'10an2n';'10ann2';'10ann2';'2nan10';'2nan10';'02nan1';'02nan1';'2nan01';'2nan01';'2n10na';'2n10na';'2n10an';'2n10an';'2n1n0a';'2n1n0a';'2n1na0';'2n1na0';'02n1na';'02n1na';'2n01na';'2n01na';'2n1a0n';'2n1a0n';'2n1an0';'2n1an0';'02n1an';'02n1an';'2n01an';'2n01an';'2n0n1a';'2n0n1a';'2n0na1';'2n0na1';'2n0a1n';'2n0a1n';'2n0an1';'2n0an1';'2nn10a';'2nn10a';'2nn1a0';'2nn1a0';'02nn1a';'02nn1a';'2nn01a';'2nn01a';'2nn0a1';'2nn0a1';'2nna10';'2nna10';'02nna1';'02nna1';'2nna01';'2nna01';'2na10n';'2na10n';'2na1n0';'2na1n0';'02na1n';'02na1n';'2na01n';'2na01n';'2na0n1';'2na0n1';'2a10nn';'2a10nn';'2a1n0n';'2a1n0n';'2a1nn0';'2a1nn0';'02a1nn';'02a1nn';'2a01nn';'2a01nn';'2a0n1n';'2a0n1n';'2a0nn1';'2a0nn1';'2an10n';'2an10n';'2an1n0';'2an1n0';'02an1n';'02an1n';'2an01n';'2an01n';'2an0n1';'2an0n1';'2ann10';'2ann10';'02ann1';'02ann1';'2ann01';'2ann01';'1nan20';'1nan20';'01nan2';'01nan2';'1nan02';'1nan02';'1n20na';'1n20na';'1n20an';'1n20an';'1n2n0a';'1n2n0a';'1n2na0';'1n2na0';'01n2na';'01n2na';'1n02na';'1n02na';'1n2a0n';'1n2a0n';'1n2an0';'1n2an0';'01n2an';'01n2an';'1n02an';'1n02an';'1n0n2a';'1n0n2a';'1n0na2';'1n0na2';'1n0a2n';'1n0a2n';'1n0an2';'1n0an2';'1nn20a';'1nn20a';'1nn2a0';'1nn2a0';'01nn2a';'01nn2a';'1nn02a';'1nn02a';'1nn0a2';'1nn0a2';'1nna20';'1nna20';'01nna2';'01nna2';'1nna02';'1nna02';'1na20n';'1na20n';'1na2n0';'1na2n0';'01na2n';'01na2n';'1na02n';'1na02n';'1na0n2';'1na0n2';'1a20nn';'1a20nn';'1a2n0n';'1a2n0n';'1a2nn0';'1a2nn0';'01a2nn';'01a2nn';'1a02nn';'1a02nn';'1a0n2n';'1a0n2n';'1a0nn2';'1a0nn2';'1an20n';'1an20n';'1an2n0';'1an2n0';'01an2n';'01an2n';'1an02n';'1an02n';'1an0n2';'1an0n2';'1ann20';'1ann20';'01ann2';'01ann2';'1ann02';'1ann02';'0nan21';'0nan21';'0nan12';'0nan12';'0n21na';'0n21na';'0n21an';'0n21an';'0n12na';'0n12na';'0n12an';'0n12an';'0n2n1a';'0n2n1a';'0n2na1';'0n2na1';'0n2a1n';'0n2a1n';'0n2an1';'0n2an1';'0n1n2a';'0n1n2a';'0n1na2';'0n1na2';'0n1a2n';'0n1a2n';'0n1an2';'0n1an2';'0nn21a';'0nn21a';'0nn12a';'0nn12a';'0nn2a1';'0nn2a1';'0nn1a2';'0nn1a2';'0nna21';'0nna21';'0nna12';'0nna12';'0na21n';'0na21n';'0na12n';'0na12n';'0na2n1';'0na2n1';'0na1n2';'0na1n2';'0a21nn';'0a21nn';'0a12nn';'0a12nn';'0a2n1n';'0a2n1n';'0a2nn1';'0a2nn1';'0a1n2n';'0a1n2n';'0a1nn2';'0a1nn2';'0an21n';'0an21n';'0an12n';'0an12n';'0an2n1';'0an2n1';'0an1n2';'0an1n2';'0ann21';'0ann21';'0ann12';'0ann12';'nan210';'nan210';'nan201';'nan201';'nan120';'nan120';'nan102';'nan102';'nan021';'nan021';'nan012';'nan012';'n210na';'n210na';'n210an';'n210an';'n201na';'n201na';'n201an';'n201an';'n120na';'n120na';'n120an';'n120an';'n102na';'n102na';'n102an';'n102an';'n21n0a';'n21n0a';'n21na0';'n21na0';'n021na';'n021na';'n21a0n';'n21a0n';'n21an0';'n21an0';'n021an';'n021an';'n20n1a';'n20n1a';'n20na1';'n20na1';'n20a1n';'n20a1n';'n20an1';'n20an1';'n12n0a';'n12n0a';'n12na0';'n12na0';'n012na';'n012na';'n12a0n';'n12a0n';'n12an0';'n12an0';'n012an';'n012an';'n10n2a';'n10n2a';'n10na2';'n10na2';'n10a2n';'n10a2n';'n10an2';'n10an2';'n2n10a';'n2n10a';'n2n1a0';'n2n1a0';'n02n1a';'n2n01a';'n02n1a';'n2n01a';'n2n0a1';'n2n0a1';'n2na10';'n2na10';'n02na1';'n2na01';'n02na1';'n2na01';'n2a10n';'n2a10n';'n2a1n0';'n2a1n0';'n02a1n';'n2a01n';'n02a1n';'n2a01n';'n2a0n1';'n2a0n1';'n2an10';'n2an10';'n02an1';'n2an01';'n02an1';'n2an01';'n1n20a';'n1n20a';'n1n2a0';'n1n2a0';'n01n2a';'n1n02a';'n01n2a';'n1n02a';'n1n0a2';'n1n0a2';'n1na20';'n1na20';'n01na2';'n1na02';'n01na2';'n1na02';'n1a20n';'n1a20n';'n1a2n0';'n1a2n0';'n01a2n';'n1a02n';'n01a2n';'n1a02n';'n1a0n2';'n1a0n2';'n1an20';'n1an20';'n01an2';'n1an02';'n01an2';'n1an02';'n0n21a';'n0n21a';'n0n12a';'n0n12a';'n0n2a1';'n0n2a1';'n0n1a2';'n0n1a2';'n0na21';'n0na21';'n0na12';'n0na12';'n0a21n';'n0a21n';'n0a12n';'n0a12n';'n0a2n1';'n0a2n1';'n0a1n2';'n0a1n2';'n0an21';'n0an21';'n0an12';'n0an12';'nn210a';'nn210a';'nn201a';'nn201a';'nn120a';'nn120a';'nn102a';'nn102a';'nn21a0';'nn21a0';'nn021a';'nn021a';'nn20a1';'nn20a1';'nn12a0';'nn12a0';'nn012a';'nn012a';'nn10a2';'nn10a2';'nn2a10';'nn2a10';'nn02a1';'nn2a01';'nn02a1';'nn2a01';'nn1a20';'nn1a20';'nn01a2';'nn1a02';'nn01a2';'nn1a02';'nn0a21';'nn0a21';'nn0a12';'nn0a12';'nna210';'nna210';'nna201';'nna201';'nna120';'nna120';'nna102';'nna102';'nna021';'nna021';'nna012';'nna012';'na210n';'na210n';'na201n';'na201n';'na120n';'na120n';'na102n';'na102n';'na21n0';'na21n0';'na021n';'na021n';'na20n1';'na20n1';'na12n0';'na12n0';'na012n';'na012n';'na10n2';'na10n2';'na2n10';'na2n10';'na02n1';'na2n01';'na02n1';'na2n01';'na1n20';'na1n20';'na01n2';'na1n02';'na01n2';'na1n02';'na0n21';'na0n21';'na0n12';'na0n12';'a210nn';'a210nn';'a201nn';'a201nn';'a120nn';'a120nn';'a102nn';'a102nn';'a21n0n';'a21n0n';'a21nn0';'a21nn0';'a021nn';'a021nn';'a20n1n';'a20n1n';'a20nn1';'a20nn1';'a12n0n';'a12n0n';'a12nn0';'a12nn0';'a012nn';'a012nn';'a10n2n';'a10n2n';'a10nn2';'a10nn2';'a2n10n';'a2n10n';'a2n1n0';'a2n1n0';'a02n1n';'a02n1n';'a2n01n';'a2n01n';'a2n0n1';'a2n0n1';'a2nn10';'a2nn10';'a02nn1';'a02nn1';'a2nn01';'a2nn01';'a1n20n';'a1n20n';'a1n2n0';'a1n2n0';'a01n2n';'a01n2n';'a1n02n';'a1n02n';'a1n0n2';'a1n0n2';'a1nn20';'a1nn20';'a01nn2';'a01nn2';'a1nn02';'a1nn02';'a0n21n';'a0n21n';'a0n12n';'a0n12n';'a0n2n1';'a0n2n1';'a0n1n2';'a0n1n2';'a0nn21';'a0nn21';'a0nn12';'a0nn12';'an210n';'an210n';'an201n';'an201n';'an120n';'an120n';'an102n';'an102n';'an21n0';'an21n0';'an021n';'an021n';'an20n1';'an20n1';'an12n0';'an12n0';'an012n';'an012n';'an10n2';'an10n2';'an2n10';'an2n10';'an02n1';'an2n01';'an02n1';'an2n01';'an1n20';'an1n20';'an01n2';'an1n02';'an01n2';'an1n02';'an0n21';'an0n21';'an0n12';'an0n12';'ann210';'ann210';'ann201';'ann201';'ann120';'ann120';'ann102';'ann102';'ann021';'ann021';'ann012';'ann012'}, ...
	[717;719;718;720;715;716;693;695;694;696;691;692;597;599;598;600;595;596;573;575;574;576;571;572;703;709;477;479;708;714;707;713;706;712;705;711;478;480;704;710;701;702;698;700;697;699;475;476;679;685;684;690;683;689;682;688;681;687;680;686;677;678;674;676;673;675;583;589;453;455;588;594;587;593;586;592;585;591;454;456;584;590;581;582;578;580;577;579;451;452;559;565;564;570;563;569;562;568;561;567;560;566;557;558;554;556;553;555;626;650;463;469;625;649;648;672;647;671;646;670;645;669;468;474;642;666;644;668;643;667;467;473;641;665;640;664;639;663;638;662;637;661;636;660;635;659;466;472;634;658;633;657;632;656;465;471;631;655;630;654;629;653;464;470;628;652;627;651;623;624;620;622;619;621;461;462;617;618;614;616;613;615;606;612;605;611;458;460;604;610;603;609;602;608;457;459;601;607;506;530;439;445;505;529;528;552;527;551;526;550;525;549;444;450;522;546;524;548;523;547;443;449;521;545;520;544;519;543;518;542;517;541;516;540;515;539;442;448;514;538;513;537;512;536;441;447;511;535;510;534;509;533;440;446;508;532;507;531;503;504;500;502;499;501;437;438;497;498;494;496;493;495;486;492;485;491;434;436;484;490;483;489;482;488;433;435;481;487;386;410;385;409;408;432;407;431;402;426;401;425;406;430;405;429;404;428;403;427;400;424;399;423;398;422;397;421;396;420;394;418;395;419;393;417;392;416;391;415;390;414;388;412;389;413;387;411;383;384;377;378;380;382;379;381;374;376;373;375;366;372;364;370;365;371;363;369;362;368;361;367;126;246;125;245;124;244;123;243;122;242;121;241;240;360;239;359;234;354;233;353;216;336;215;335;210;330;209;329;238;358;237;357;192;312;236;356;235;355;191;311;232;352;231;351;230;350;229;349;214;334;213;333;186;306;212;332;211;331;185;305;208;328;207;327;206;326;205;325;228;348;227;347;190;226;310;346;225;345;224;344;189;223;309;343;222;342;221;341;188;220;308;340;219;339;218;338;187;217;307;337;204;324;203;323;184;202;304;322;201;321;200;320;183;199;303;319;198;318;197;317;182;196;302;316;195;315;194;314;181;193;301;313;180;300;178;298;179;299;177;297;176;296;175;295;174;294;172;292;173;293;171;291;170;290;169;289;168;288;166;286;162;282;160;280;167;287;156;276;165;285;161;281;154;274;159;279;164;284;155;163;275;283;158;278;153;157;273;277;152;272;151;271;150;270;149;269;148;268;147;267;146;266;145;265;144;264;142;262;138;258;136;256;143;263;132;252;141;261;137;257;130;250;135;255;140;260;131;139;251;259;134;254;129;133;249;253;128;248;127;247;119;120;113;114;95;96;89;90;116;118;115;117;71;72;110;112;109;111;92;94;91;93;65;66;86;88;85;87;102;108;101;107;68;70;100;106;99;105;98;104;67;69;97;103;78;84;77;83;62;64;76;82;75;81;74;80;61;63;73;79;54;60;52;58;53;59;51;57;50;56;49;55;24;48;22;46;18;42;16;40;23;47;12;36;21;45;17;41;10;34;15;39;20;44;11;19;35;43;14;38;9;13;33;37;8;32;7;31;6;30;5;29;4;28;3;27;2;26;1;25])
%
%% Other Implementation Examples %%
%
% <https://code.activestate.com/recipes/285264-natural-string-sorting/>
chk({'Team 11','Team 3','Team 1'}, fnh,...
	{'Team 1','Team 3','Team 11'})
chk({'ver-1.3.12','ver-1.3.3','ver-1.2.5','ver-1.2.15','ver-1.2.3','ver-1.2.1'}, fnh,...
	{'ver-1.2.1','ver-1.2.3','ver-1.2.5','ver-1.2.15','ver-1.3.3','ver-1.3.12'})
chk({'C1H2','C1H4','C2H2','C2H6','C2N','C3H6'}, fnh,...
	{'C1H2','C1H4','C2H2','C2H6','C2N','C3H6'})
chk({'Team 101','Team 58','Team 30','Team 1'}, fnh,...
	{'Team 1','Team 30','Team 58','Team 101'})
chk({'a5','A7','a15','a9','A8'}, fnh,...
	{'a5','A7','A8','a9','a15'})
%
% <http://www.davekoelle.com/alphanum.html>
chk({'1000X Radonius Maximus','10X Radonius','200X Radonius','20X Radonius','20X Radonius Prime','30X Radonius','40X Radonius','Allegia 50 Clasteron','Allegia 500 Clasteron','Allegia 50B Clasteron','Allegia 51 Clasteron','Allegia 6R Clasteron','Alpha 100','Alpha 2','Alpha 200','Alpha 2A','Alpha 2A-8000','Alpha 2A-900','Callisto Morphamax','Callisto Morphamax 500','Callisto Morphamax 5000','Callisto Morphamax 600','Callisto Morphamax 6000 SE','Callisto Morphamax 6000 SE2','Callisto Morphamax 700','Callisto Morphamax 7000','Xiph Xlater 10000','Xiph Xlater 2000','Xiph Xlater 300','Xiph Xlater 40','Xiph Xlater 5','Xiph Xlater 50','Xiph Xlater 500','Xiph Xlater 5000','Xiph Xlater 58'}, fnh,...
	{'10X Radonius','20X Radonius','20X Radonius Prime','30X Radonius','40X Radonius','200X Radonius','1000X Radonius Maximus','Allegia 6R Clasteron','Allegia 50 Clasteron','Allegia 50B Clasteron','Allegia 51 Clasteron','Allegia 500 Clasteron','Alpha 2','Alpha 2A','Alpha 2A-900','Alpha 2A-8000','Alpha 100','Alpha 200','Callisto Morphamax','Callisto Morphamax 500','Callisto Morphamax 600','Callisto Morphamax 700','Callisto Morphamax 5000','Callisto Morphamax 6000 SE','Callisto Morphamax 6000 SE2','Callisto Morphamax 7000','Xiph Xlater 5','Xiph Xlater 40','Xiph Xlater 50','Xiph Xlater 58','Xiph Xlater 300','Xiph Xlater 500','Xiph Xlater 2000','Xiph Xlater 5000','Xiph Xlater 10000'})
%
% <https://natsort.readthedocs.io/en/master/examples.html>
chk({'2 ft 7 in','1 ft 5 in','10 ft 2 in','2 ft 11 in','7 ft 6 in'}, fnh,...
	{'1 ft 5 in','2 ft 7 in','2 ft 11 in','7 ft 6 in','10 ft 2 in'})
chk({'version-1.9','version-2.0','version-1.11','version-1.10'}, fnh,...
	{'version-1.9','version-1.10','version-1.11','version-2.0'})
chk({'position5.10.data','position-3.data','position5.3.data','position2.data'}, '(+|-)?\d+\.?\d*', fnh,...
	{'position-3.data','position2.data','position5.10.data','position5.3.data'})
chk({'1.2','1.2rc1','1.2beta2','1.2beta1','1.2alpha','1.2.1','1.1','1.3'}, fnh,...
	{'1.1','1.2','1.2.1','1.2alpha','1.2beta1','1.2beta2','1.2rc1','1.3'})
a =                                  {'a50','a51.','a+50.4','a5.034e1','a+50.300'};
chk(a, '\d+\.?\d*(E\d+)?',      fnh, {'a50','a5.034e1','a51.','a+50.300','a+50.4'}) % no sign
chk(a, '(+|-)?\d+\.?\d*(E\d+)?', fnh, {'a50','a+50.300','a5.034e1','a+50.4','a51.'})
chk(a, '(+|-)?\d+\.?\d*',        fnh, {'a5.034e1','a50','a+50.300','a+50.4','a51.'}) % no exp
a =                        {'a2','a9','a1','a4','a10'};
chk(a,                fnh, {'a1','a2','a4','a9','a10'}, [3,1,4,2,5])
chk(a, [], 'descend', fnh, {'a10','a9','a4','a2','a1'})
%
%% Display Summary %%
%
chk()
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%natsort_test