% Test matlab plotting using painters / opengl 

numRandPoints = 100000;

figure;
x_vals = rand(numRandPoints, 1);
y_vals = rand(numRandPoints, 1);
scatter(x_vals, y_vals)

figFileNameAuto = 'testAuto.svg';
figFileNamePainter = 'testPainter.svg';

saveas(gcf, figFileNameAuto);
print('-painters', '-dsvg', figFileNamePainter); 
