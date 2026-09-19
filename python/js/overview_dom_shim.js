// DOM shim for the viewer page's overview renderer
const calls = {circles: 0, texts: 0, lines: 0, figures: 0};
class El {
  constructor(tag){ this.tagName=(tag||'').toUpperCase(); this.children=[]; this.attrs={}; this.dataset={}; this.style={};
    this._html=''; this._text=''; this.classList={ _s:new Set(),
      toggle:(c,on)=>{on?this.classList._s.add(c):this.classList._s.delete(c);},
      add:c=>this.classList._s.add(c), remove:c=>this.classList._s.delete(c) }; }
  set innerHTML(v){ this._html=v; if(v==='') this.children=[]; }
  get innerHTML(){ return this._html; }
  set textContent(v){ this._text=v; } get textContent(){ return this._text; }
  setAttribute(k,v){ this.attrs[k]=v; } getAttribute(k){ return this.attrs[k]; }
  append(...c){ this.children.push(...c); if(this.tagName==='FIGURE') calls.figures++; }
  appendChild(c){ this.children.push(c); return c; }
  addEventListener(type, fn){ listeners.count++;
    (this._h = this._h || {})[type] = (this._h[type] || []).concat(fn); }
  fire(type, ev){ for (const fn of ((this._h || {})[type] || [])) fn(ev || {}); }
  getBoundingClientRect(){ return {left:0,top:0,width:300,height:300}; }
  setPointerCapture(){}
  insertAdjacentHTML(pos, html){ this._html += html; }
  querySelectorAll(){ return []; }
  get lastChild(){ return this.children[this.children.length-1]; }
}
const reg = {};
// net-span is created by insertAdjacentHTML, which this shim does not parse
// into elements, so it is registered up front
['tracking','track-view','track-chain','track-meta','side-tracking',
 'net-span'].forEach(id=>{
  const e=new El('div'); e.id=id; reg[id]=e; });
reg['track-view'].value='overview';
const listeners = { count: 0 };
global.document = {
  body: new El('body'),
  createElement:(t)=>new El(t),
  createElementNS:(ns,t)=>{ if(t==='circle')calls.circles++; if(t==='text')calls.texts++;
    if(t==='line')calls.lines++; return new El(t); },
  getElementById:(id)=>reg[id]||null,
  appendChild:(c)=>c,
  querySelectorAll:()=>[],
};
// themeColour() resolves CSS variables off the document element
const VARS = {'--plot-wt':'#2c7fb8','--plot-het':'#7b3294','--plot-ko':'#d95f0e',
              '--plot-other':'#6b7280','--plot-off':'#98a0a8','--plot-sel':'#d62728'};
global.document.documentElement = new El('html');
global.getComputedStyle = () => ({ getPropertyValue: n => VARS[n] || '' });
global.$ = id => reg[id] || null;
module.exports = { calls, reg, listeners };
