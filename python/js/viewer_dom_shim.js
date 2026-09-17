// Minimal DOM/canvas shim: enough to run the viewer's render path and surface
// any exception it throws. Not a rendering check — a "does it execute" check.
const calls = {createElement: 0, ns: 0, images: 0, putImageData: 0, arcs: 0};
class El {
  constructor(tag){ this.tagName=(tag||'').toUpperCase(); this.children=[]; this.style={};
    this.attrs={}; this.dataset={}; this._html=''; this._text=''; this.width=0; this.height=0;
    this.style={}; this.classList={ _s:new Set(), add(c){this._s.add(c);},
      remove(c){this._s.delete(c);}, toggle(c,on){on?this._s.add(c):this._s.delete(c);} }; }
  set innerHTML(v){ this._html=v; if(v==='') this.children=[]; }
  get innerHTML(){ return this._html; }
  set textContent(v){ this._text=v; } get textContent(){ return this._text; }
  setAttribute(k,v){ this.attrs[k]=v; } getAttribute(k){ return this.attrs[k]; }
  append(...c){ this.children.push(...c); }
  addEventListener(type, fn){ (this._h = this._h || {})[type] = fn; }
  dispatch(type, ev){ if (this._h && this._h[type]) this._h[type](ev || {target:this}); }
  insertAdjacentHTML(){} scrollIntoView(){}
  getBoundingClientRect(){ return {left:0, top:0, width:300, height:300}; }
  getContext(){ return {
    setTransform(){}, clearRect(){}, drawImage(){}, beginPath(){},
    fillRect(){}, imageSmoothingEnabled: true,
    arc(){ calls.arcs++; }, stroke(){}, fill(){}, moveTo(){}, lineTo(){},
    createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),
    putImageData(){ calls.putImageData++; },
  }; }
  querySelector(){ return null; }
}
const registry = {};
function mk(id){ const e=new El('div'); e.id=id; registry['#'+id]=e; return e; }
['fov','list','search','showall','hdr','days','traces','strips',
 'reset','zoom','bg'].forEach(mk);
registry['#search'].value='';
registry['#showall'].checked=true;
registry['#bg'].value='mean';
global.document = {
  getElementById:(id)=>registry['#'+id]||null,
  createElement:(t)=>{ calls.createElement++; return new El(t); },
  createElementNS:(ns,t)=>{ calls.ns++; return new El(t); },
  querySelector:(s)=>registry[s]||null,
  addEventListener(){}, body:Object.assign(new El('body'), {appendChild(c){return c;}}),
};
global.getComputedStyle = () => ({ getPropertyValue: () => '#000000' });
const winH = {};
global.window = { devicePixelRatio: 2,
  addEventListener(t, fn){ winH[t] = fn; },
  matchMedia: () => ({matches: false}),
  __TRACK__: null };
global.__fire = (t) => winH[t] && winH[t]();
global.Image = class { constructor(){ calls.images++; } set src(v){ if(this.onload) this.onload(); } };
global.atob = (s) => Buffer.from(s, 'base64').toString('binary');
module.exports = { calls, registry };
