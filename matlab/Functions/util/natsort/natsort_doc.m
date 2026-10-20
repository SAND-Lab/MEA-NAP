%% |NATSORT| Examples
% The function <https://www.mathworks.com/matlabcentral/fileexchange/34464
% |NATSORT|> sorts the elements of a text array |A| (cell/string/...)
% taking into account number values within the text. This is known as
% _natural order_ or _alphanumeric order_. Note that MATLAB's inbuilt
% <https://www.mathworks.com/help/matlab/ref/sort.html |SORT|> function
% sorts text by character code, as does |SORT| in most programming languages.
%
% Other useful text sorting functions:
%
% * Alphanumeric sort of filenames, foldernames, and filepaths:
% <https://www.mathworks.com/matlabcentral/fileexchange/47434 |NATSORTFILES|>
% * Alphanumeric sort the rows of a string/cell/table/etc array:
% <https://www.mathworks.com/matlabcentral/fileexchange/47433 |NATSORTROWS|>
% * Sort text into the order of arbitrary/custom text sequences:
% <https://www.mathworks.com/matlabcentral/fileexchange/132263 |ARBSORT|>
%
% Both |NATSORTFILES| and |NATSORTROWS| call |NATSORT|.
%% Basic Usage: Integer Numbers
% By default |NATSORT| interprets consecutive digits in |A| as being
% part of a single integer, any remaining substrings are treated as text:
Aa = ["a2", "a10", "a1"];
sort(Aa) % for comparison
natsort(Aa)
Ab = ["v9.10", "v9.5", "v9.2", "v9.10.20", "v9.10.8"];
sort(Ab) % for comparison
natsort(Ab)
%% Input 1: Array to Sort
% The first input |A| must be one of the following array types:
%
% * a cell array of character row vectors,
% * a <https://www.mathworks.com/help/matlab/matlab_prog/create-string-arrays.html string array>,
% * a <https://www.mathworks.com/help/matlab/categorical-arrays.html categorical array>,
% * a <https://www.mathworks.com/help/matlab/ref/datetime.html datetime array>,
% * any other array type that can be converted by 
%   <https://www.mathworks.com/help/matlab/ref/cellstr.html |CELLSTR|>
%
% The sorted array is returned as the first output, for example:
Ac = categorical({'a2','a10','a1'});
natsort(Ac) % see also REORDERCATS below!
%% Input 2: Regular Expression
% The optional second input argument |rgx| is a regular expression which
% specifies the number matching (see "Regular Expression" sections below
% for more examples of regular expressions for matching common numbers):
Ad = ["1.3", "1.10", "1.2"];
natsort(Ad) % by default match integers.
natsort(Ad, '\d+\.?\d*') % match decimal fractions.
%% Input 3+: Case Sensitivity
% By default |NATSORT| provides a case-insensitive sort of the array elements.
% An optional input argument selects case-sensitive/insensitive sorting:
Ae = ["a2", "A20", "A1", "a", "A", "a10", "A2", "a1"];
natsort(Ae, [], 'ignorecase') % default
natsort(Ae, [], 'matchcase')
%% Input 3+: Sort Direction
% By default |NATSORT| provides an ascending sort of the array elements.
% An optional input argument selects the sort direction (note that
% characters and numbers are either both ascending or both descending):
Af = ["2", "a", "", "10", "B", "1"];
natsort(Af, [], 'ascend') % default
natsort(Af, [], 'descend')
%% Input 3+: Char/Number Order
% By default |NATSORT| sorts characters after numbers.
% An optional input argument selects if characters are treated as
% _greater-than_ or _less-than_ numbers:
natsort(Af, [], 'num<char') % default
natsort(Af, [], 'char<num')
%% Input 3+: NaN/Number Order
% By default |NATSORT| sorts NaN after all other numbers.
% An optional input argument selects if NaN are treated as
% _greater-than_ or _less-than_ numbers:
Ag = ["10", "1", "NaN", "2"];
natsort(Ag, 'NaN|\d+', 'num<NaN') % default
natsort(Ag, 'NaN|\d+', 'NaN<num')
%% Input 3+: |SSCANF| Format String (Floating Point, Hexadecimal, Octal, Binary, 64 Bit Integer)
% The default format string |'%f'| will correctly parse many common number
% formats, including decimal integers, decimal fractions, |NaN|, |Inf|,
% and numbers written in E-notation. For hexadecimal, octal, binary, and
% 64-bit integers the format string must be specified as an input argument.
% Supported <https://www.mathworks.com/help/matlab/ref/sscanf.html
% |SSCANF|> formats are shown in this table:
%
% <html>
% <table>
%  <tr><th>Format String</th><th>Number Types</th></tr>
%  <tr><td>%e, %f, %g</td>   <td>floating point numbers</td></tr>
%  <tr><td>%d</td>           <td>signed integer decimal</td></tr>
%  <tr><td>%i</td>           <td>signed integer decimal, octal, or hexadecimal</td></tr>
%  <tr><td>%ld, %li</td>     <td>signed integer 64 bit, decimal, octal, or hexadecimal</td></tr>
%  <tr><td>%u</td>           <td>unsigned integer decimal</td></tr>
%  <tr><td>%o</td>           <td>unsigned integer octal</td></tr>
%  <tr><td>%x</td>           <td>unsigned integer hexadecimal</td></tr>
%  <tr><td>%lu, %lo, %lx</td><td>unsigned integer 64-bit decimal, octal, or hexadecimal</td></tr>
%  <tr><td>%b</td>           <td>unsigned binary integer (custom parsing, not SSCANF)</td></tr>
% </table>
% </html>
%
% For example large
% integers can be converted to 64-bit numerics, with their full precision:
Ah = ["18446744073709551614", "18446744073709551615", "18446744073709551613"];
natsort(Ah, [], '%lu')
%% Input 3+: Text Sorting Function
% A text sorting function may provide an arbitrary/custom sequence sort,
% e.g. <https://www.mathworks.com/matlabcentral/fileexchange/132263
% |ARBSORT|> may be used to sort text into alphabetical order for many
% languages: refer to the |ARBSORT| help for more information on how to
% specify the custom text sequence order, handle diacritics, etc. Note
% that the sort direction, case sensitivity, etc. of the text sorting
% function must be appropriately parameterized as required:
% <https://www.mathworks.com/help/matlab/math/parameterizing-functions.html>.
%
% An example using |ARBSORT| to sort into Spanish alphabetical order:
Ap = ["ña_2", "ño", "os", "ña_10", "ni", "ña_1"];
alfabeto = num2cell(['A':'N','Ñ','O':'Z']); % Spanish alphabet
natsort(Ap, [], @(t)arbsort(t,alfabeto)) % download ARBSORT from FEX 132263.
%% Output 2: Sort Index
% The second output |ndx| is a numeric array of the sort indices,
% in general such that |B = A(ndx)| where |B = natsort(A,...)|.
% Note that |NATSORT| provides a _stable sort:_
Ak = ["abc2xyz", "abc10xyz", "abc2xyz", "abc1xyz"];
[out,ndx] = natsort(Ak)
%% Output 3: Debugging Array
% The third output |dbg| is a cell array which contains all matched numbers
% (after converting to numeric using the specified |SSCANF| format) and
% all non-number substrings of |A|. The cell array is intended for visually
% confirming that the numbers of |A| are being correctly identified by the
% regular expression. Note that the rows of the debugging cell array are
% <https://www.mathworks.com/company/newsletters/articles/matrix-indexing-in-matlab.html
% linearly indexed> from |A|, whereas the number of columns
% depends on how many numbers were identified within the text of |A|.
[~,~,dbg] = natsort(Ak)
%% Regular Expression: Decimal Fractions, E-notation, +/- Sign
% |NATSORT| relies on <https://www.mathworks.com/help/matlab/ref/regexpi.html
% |REGEXPI|> to detect numbers in the strings. In order to match
% the required number format (e.g. decimal fractions, exponents,
% or a positive/negative sign, etc.) simply provide a suitable
% <https://www.mathworks.com/help/matlab/matlab_prog/regular-expressions.html
% regular expression> as the second input argument:
Am = ["x+NaN", "x11.5", "x-1.4", "x", "x-Inf", "x+0.3"];
sort(Am) % for comparison
natsort(Am, '(+|-)?(NaN|Inf|\d+\.?\d*)')
An = ["0.56e007", "", "43E-2", "10000", "9.8"];
sort(An) % for comparison
natsort(An, '(+|-)?\d+\.?\d*(E(+|-)?\d+)?')
%% Regular Expression: Hexadecimal, Octal, Binary Integers
% Integers encoded in hexadecimal, octal, or binary may also be parsed and
% sorted correctly. This requires both an appropriate regular expression
% to detect the integers and also a suitable |SSCANF| format string for
% converting the detected number string into numeric:
Ao = ["a0X7C4z", "a0X5z", "a0X18z", "a0XFz"];
sort(Ao) % for comparison
natsort(Ao, '0X[0-9A-F]+', '%x') % hexadecimal
Ap = ["a11111000100z", "a101z", "a000000000011000z", "a1111z"];
sort(Ap) % for comparison
natsort(Ap, '[01]+', '%b') % binary
%% Regular Expression: Ignore Leading and/or Trailing Whitespace
% Sometimes it may be useful to match numbers _ignoring_ any leading
% and/or trailing whitespace. This can be achieved by appending/prepending 
% |'\s*'| as required to the regular expression, for example:
Aq = [' 9';'23';'10';' 0';'5 '] % character matrix.
natsort(Aq) % default matches only digits, whitespace is significant.
natsort(Aq,'\s*\d+\s*') % match and ignore whitespace.
%% Example: Categorical Categories
% These examples show how to create categories in alphanumeric order, and
% how to use |REORDERCATS| to change the category order of such an array:
Ar = ["a2", "a10", "a1"];
% default categories order is not alphanumeric order:
P = categorical(Ar)
categories(P)
% reorder categories of an existing categorical array:
P = reordercats(P,natsort(categories(P)))
categories(P)
% alternatively create the categories in the required order:
P = categorical(Ar,natsort(unique(Ar)))
categories(P)
%% Example: Decimal Comma and Decimal Point
% Many languages use a decimal comma instead of a decimal point.
% |NATSORT| parses both the decimal comma and the decimal point, e.g.:
As = ["1,3", "1,10", "1,2"];
natsort(As, '\d+,?\d*') % match optional decimal comma
%% Bonus: Interactive Regular Expression Tool
% Regular expressions are powerful and compact, but getting them right is
% not always easy. One assistance is to download my interactive tool
% <https://www.mathworks.com/matlabcentral/fileexchange/48930 |IREGEXP|>,
% which lets you quickly try different regular expressions and see all of
% <https://www.mathworks.com/help/matlab/ref/regexp.html |REGEXP|>'s
% outputs displayed and updated as you type:
iregexp('x1.23y45.6789z','(\d+)\.?(\d*)') % download IREGEXP from FEX 48930.