/* Responsive map camera; basemap is fetched only after gestures settle. */
const MAP_CHINA=[104.1954,35.8617],mapImages=new Map(),mapControllers=new WeakMap(),liveMapControllers=new Set();
let nationalPrefetch=null;
async function prefetchNationalMap(wid){
 const key='3:'+MAP_CHINA.join(',');if(mapImages.has(key)||nationalPrefetch)return;
 nationalPrefetch=(async()=>{const url='/api/workspaces/'+wid+'/map-image?'+new URLSearchParams({base:'true',zoom:'3',lng:String(MAP_CHINA[0]),lat:String(MAP_CHINA[1])});const r=await fetch(url,{credentials:'same-origin',cache:'force-cache'});if(!r.ok)return;const blob=await r.blob(),objectURL=URL.createObjectURL(blob),bitmap=new Image();try{bitmap.src=objectURL;await bitmap.decode()}finally{URL.revokeObjectURL(objectURL)}mapImages.set(key,{bitmap,world:mapWorld(...MAP_CHINA),zoom:3,width:bitmap.naturalWidth,height:bitmap.naturalHeight});while(mapImages.size>24)mapImages.delete(mapImages.keys().next().value)})().catch(()=>{}).finally(()=>{nationalPrefetch=null});
}
function validMapPoint(p){const xy=String(p.location||'').split(',').map(Number);return xy.length===2&&xy.every(Number.isFinite)&&Math.abs(xy[0])<=180&&Math.abs(xy[1])<=85}
function interactiveMapHTML(points,day='',focus=''){
 const roads=!workspace.plan?.stale?(workspace.plan?.days||[]).filter(d=>!day||d.date===day).flatMap(d=>(d.events||[]).flatMap(e=>e.route?.polylines||[])):[];
 const ps=points.filter(validMapPoint),key=workspace.id+':'+day+':'+focus,fit=ps.length?fitMapZoom(ps):3,original=ps.length?mapFitCenter(ps):MAP_CHINA,zoom=mapZooms.get(key)??fit,center=mapCenters.get(key)||original;
 return `<div class="location-map" data-map-key="${esc(key)}" data-map-fit="${fit}" data-map-zoom="${zoom}" data-map-center="${esc(JSON.stringify(center))}" data-map-fit-center="${esc(JSON.stringify(original))}" data-map-roads="${esc(JSON.stringify(roads))}" data-map-points="${esc(JSON.stringify(ps.map(p=>({id:p.id,name:p.name,location:p.location,kind:p.kind}))))}" data-map-day="${esc(day)}" data-map-focus="${esc(focus)}" data-map-workspace="${esc(workspace.id)}"><div class="map-controls" aria-label="地图操作"><button class="ghost" data-map-zoom-action="out" aria-label="缩小地图">−</button><span class="map-zoom-level">${mapPercentage(zoom,fit)}</span><button class="ghost" data-map-zoom-action="in" aria-label="放大地图">＋</button><button class="ghost" data-map-zoom-action="center">重置中心点</button><button class="ghost" data-map-zoom-action="nation">全国</button><button class="ghost" data-map-zoom-action="reset">显示全部</button></div><p class="map-gesture-hint">拖动查看 · 滚轮缩放 · 双击放大</p><div class="map-stage" tabindex="0" role="application" aria-label="交互地图，可拖动和缩放"><canvas class="map-base" width="800" height="440"></canvas><span class="map-attribution">${link('https://www.amap.com/','高德地图')} · 地图数据 © 高德</span></div><div class="map-update"><span class="map-update-text" role="status">正在加载底图，可先拖动或缩放</span><button class="text-button" data-map-retry hidden>重试底图</button></div><p class="map-caption">${roads.length?'红色实线为已查询的高德通行路线；缺失路段未绘制，出行时请使用实时导航。':day&&!focus?roads.length?'实线为已查询的高德通行路线；缺失路段未绘制，出行时请使用实时导航。':'按当日游览顺序连线，属于地点顺序示意，不代表道路导航路线。':'真实坐标位置 · 可自由查看全国范围'}</p><div class="map-legend">${ps.map((p,i)=>`<div><button data-open-candidate="${esc(p.id)}" class="ghost"><b>${i+1}</b>${esc(p.name)}<small>${({hotel:'住宿',food:'餐饮',spot:'景点'})[p.kind]||''}</small></button>${link(`https://uri.amap.com/marker?position=${p.location}&name=${encodeURIComponent(p.name)}`,'打开地图 ↗')}</div>`).join('')}</div></div>`;
}
function worldDelta(x){return x-Math.round(x)}
class TravelMap {
 constructor(root){
  this.root=root;this.stage=root.querySelector('.map-stage');this.canvas=root.querySelector('canvas');this.ctx=this.canvas.getContext('2d');this.zoom=Number(root.dataset.mapZoom);this.center=JSON.parse(root.dataset.mapCenter);this.original=JSON.parse(root.dataset.mapFitCenter);this.fit=Number(root.dataset.mapFit);this.points=JSON.parse(root.dataset.mapPoints);this.roads=JSON.parse(root.dataset.mapRoads||'[]').map(line=>String(line).split(';').map(x=>x.split(',').map(Number)).filter(x=>x.length===2&&x.every(Number.isFinite)&&Math.abs(x[0])<=180&&Math.abs(x[1])<=85).map(x=>mapWorld(...x)));this.token=0;this.drag=null;this.snapshot=null;this.timer=null;this.frame=null;this.controller=null;this.disposed=false;
  this.findSnapshot();this.sync();this.paint();this.install();this.schedule(0);liveMapControllers.add(this);
 }
 findSnapshot(){let best=Infinity;const c=mapWorld(...this.center),scale=MAP_WORLD_PIXELS*Math.pow(2,this.zoom);for(const image of mapImages.values()){const dx=worldDelta(image.world[0]-c[0])*scale,dy=(image.world[1]-c[1])*scale,d=Math.hypot(dx,dy)+Math.abs(image.zoom-this.zoom)*100;if(d<best&&d<1500){best=d;this.snapshot=image}}}
 sync(){const r=this.root;mapZooms.set(r.dataset.mapKey,this.zoom);mapCenters.set(r.dataset.mapKey,this.center);r.dataset.mapZoom=this.zoom;r.dataset.mapCenter=JSON.stringify(this.center);r.querySelector('.map-zoom-level').textContent=mapPercentage(this.zoom,this.fit);r.querySelector('[data-map-zoom-action="out"]').disabled=this.zoom<=1;r.querySelector('[data-map-zoom-action="in"]').disabled=this.zoom>=17}
 status(text,error=false){const el=this.root.querySelector('.map-update-text');if(el.textContent!==text)el.textContent=text;this.root.querySelector('[data-map-retry]').hidden=!error}
 drawSoon(){if(this.frame===null)this.frame=requestAnimationFrame(()=>{this.frame=null;if(!this.disposed)this.paint()})}
 paint(){
  const ctx=this.ctx,dpr=Math.min(2,devicePixelRatio||1);if(this.canvas.width!==800*dpr){this.canvas.width=800*dpr;this.canvas.height=440*dpr}ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#edf2f7';ctx.fillRect(0,0,800,440);ctx.strokeStyle='#e3eaf2';ctx.lineWidth=1;for(let x=0;x<800;x+=40){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,440);ctx.stroke()}for(let y=0;y<440;y+=40){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(800,y);ctx.stroke()}
  const c=mapWorld(...this.center),size=MAP_WORLD_PIXELS*Math.pow(2,this.zoom);
  if(this.snapshot){const image=this.snapshot,factor=Math.pow(2,this.zoom-image.zoom),x=400+worldDelta(image.world[0]-c[0])*size,y=220+(image.world[1]-c[1])*size;ctx.imageSmoothingEnabled=true;ctx.drawImage(image.bitmap,x-image.width*factor/2,y-image.height*factor/2,image.width*factor,image.height*factor)}
  const projected=this.points.map(p=>{const w=mapWorld(...p.location.split(',').map(Number));return {p,x:400+worldDelta(w[0]-c[0])*size,y:220+(w[1]-c[1])*size}});this.projected=projected;
  if(this.roads.length){ctx.strokeStyle='#db4e54';ctx.lineWidth=3;for(const line of this.roads){ctx.beginPath();line.forEach((w,i)=>{const x=400+worldDelta(w[0]-c[0])*size,y=220+(w[1]-c[1])*size;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}}
  if(!this.roads.length&&this.root.dataset.mapDay&&!this.root.dataset.mapFocus&&projected.length>1){ctx.beginPath();projected.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.strokeStyle='#db4e54';ctx.lineWidth=3;ctx.setLineDash([7,4]);ctx.stroke();ctx.setLineDash([])}
  const markerUnit=800/(this.stage.getBoundingClientRect().width||800);this.markerUnit=markerUnit;
  ctx.textAlign='center';ctx.textBaseline='middle';projected.map((p,i)=>({...p,index:i})).sort((a,b)=>(a.p.id===this.root.dataset.mapFocus?1:0)-(b.p.id===this.root.dataset.mapFocus?1:0)).forEach(p=>{
   const active=p.p.id===this.root.dataset.mapFocus,r=(active?17:12)*markerUnit,headY=p.y-2*r;
   if(p.x<-r||p.x>800+r||p.y<-r||headY>440+r)return;
   const color=active?'#dc445a':p.p.kind==='hotel'?'#b58528':p.p.kind==='food'?'#a76196':'#4a68af';
   // The pin tip is the geographical anchor; its head remains above that coordinate.
   ctx.save();ctx.beginPath();ctx.moveTo(p.x,p.y);
   ctx.bezierCurveTo(p.x-r*.25,p.y-r*.6,p.x-r,p.y-r*1.3,p.x-r,headY);
   ctx.arc(p.x,headY,r,Math.PI,2*Math.PI);
   ctx.bezierCurveTo(p.x+r,p.y-r*1.3,p.x+r*.25,p.y-r*.6,p.x,p.y);ctx.closePath();
   ctx.fillStyle=color;ctx.shadowColor='#26324935';ctx.shadowBlur=5*markerUnit;ctx.shadowOffsetY=2*markerUnit;ctx.fill();
   ctx.shadowColor='transparent';ctx.lineWidth=2*markerUnit;ctx.strokeStyle='#fff';ctx.stroke();
   ctx.beginPath();ctx.arc(p.x,headY,r*.58,0,2*Math.PI);ctx.fillStyle='#fff';ctx.fill();
   ctx.fillStyle=color;ctx.font=`bold ${(active?12:10)*markerUnit}px sans-serif`;ctx.fillText(String(p.index+1),p.x,headY);ctx.restore();
  });this.root.dataset.mapMarkerShape='pin';this.root.dataset.mapPaint=String(performance.now());
 }
 invalidate(){this.token++;this.controller?.abort();clearTimeout(this.timer);this.sync();this.drawSoon()}
 zoomAt(delta,offset=null){const old=this.zoom,next=Math.max(1,Math.min(17,old+delta));if(next===old)return;const w=mapWorld(...this.center);if(offset){const difference=1/(MAP_WORLD_PIXELS*Math.pow(2,old))-1/(MAP_WORLD_PIXELS*Math.pow(2,next));this.center=mapCoordinate(w[0]+offset[0]*difference,w[1]+offset[1]*difference)}this.zoom=next;this.invalidate();this.schedule(240)}
 command(action){if(action==='in'||action==='out'){this.zoomAt(action==='in'?1:-1);return}if(action==='center')this.center=[...this.original];if(action==='reset'){this.center=[...this.original];this.zoom=this.fit}if(action==='nation'){this.center=[...MAP_CHINA];this.zoom=3}this.invalidate();this.findSnapshot();this.drawSoon();this.schedule(0)}
 schedule(delay=220){clearTimeout(this.timer);this.timer=setTimeout(()=>this.fetchImage(),delay)}
 async fetchImage(){
  if(this.disposed||!this.root.isConnected)return;const zoom=Math.round(this.zoom),center=this.center.map(n=>Number(n.toFixed(6))),cacheKey=zoom+':'+center.join(',');let image=mapImages.get(cacheKey);
  if(image){mapImages.delete(cacheKey);mapImages.set(cacheKey,image);this.snapshot=image;this.status('');this.drawSoon();return}
  this.controller?.abort();const controller=new AbortController();this.controller=controller;const token=++this.token;this.status(this.snapshot?'正在补充清晰底图，可继续操作':'正在加载底图，可先拖动或缩放');
  const params=new URLSearchParams({base:'true',zoom:String(zoom),lng:String(center[0]),lat:String(center[1])});const url='/api/workspaces/'+this.root.dataset.mapWorkspace+'/map-image?'+params;this.root.dataset.mapRequest=url;
  try{
   const response=await fetch(url,{signal:controller.signal,credentials:'same-origin',cache:'force-cache'});if(!response.ok)throw Error('map');const blob=await response.blob();const objectURL=URL.createObjectURL(blob),bitmap=new Image();try{bitmap.src=objectURL;await bitmap.decode()}finally{URL.revokeObjectURL(objectURL)}
   image={bitmap,world:mapWorld(...center),zoom,width:bitmap.naturalWidth,height:bitmap.naturalHeight};mapImages.set(cacheKey,image);while(mapImages.size>24)mapImages.delete(mapImages.keys().next().value);
   if(this.disposed||token!==this.token)return;this.snapshot=image;this.status('');this.drawSoon();prefetchNationalMap(this.root.dataset.mapWorkspace);
  }catch(e){if(e.name==='AbortError'||this.disposed||token!==this.token)return;this.status('底图更新暂未完成，仍可拖动缩放，或稍后重试。',true)}
 }
 install(){
  const stage=this.stage;
  stage.addEventListener('wheel',e=>{if(e.ctrlKey||!e.deltaY)return;e.preventDefault();this.zoomAt(-Math.sign(e.deltaY),mapPointerOffset(stage,e))},{passive:false});
  stage.addEventListener('dblclick',e=>{if(e.target.closest('a'))return;clearTimeout(this.markerTimer);e.preventDefault();this.zoomAt(1,mapPointerOffset(stage,e))});
  stage.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('a'))return;e.preventDefault();clearTimeout(this.markerTimer);this.drag={id:e.pointerId,x:e.clientX,y:e.clientY,world:mapWorld(...this.center),zoom:this.zoom,moved:false};stage.setPointerCapture(e.pointerId);stage.classList.add('dragging');clearTimeout(this.timer);this.controller?.abort()});
  stage.addEventListener('pointermove',e=>{const d=this.drag;if(!d||d.id!==e.pointerId)return;const r=stage.getBoundingClientRect(),dx=(e.clientX-d.x)*800/r.width,dy=(e.clientY-d.y)*440/r.height;if(Math.abs(dx)+Math.abs(dy)>4)d.moved=true;const size=MAP_WORLD_PIXELS*Math.pow(2,d.zoom);this.center=mapCoordinate(d.world[0]-dx/size,d.world[1]-dy/size);this.invalidate()});
  const finish=e=>{const d=this.drag;if(!d||d.id!==e.pointerId)return;this.drag=null;stage.classList.remove('dragging');if(stage.hasPointerCapture(e.pointerId))stage.releasePointerCapture(e.pointerId);this.schedule();if(!d.moved&&e.type==='pointerup'){const offset=mapPointerOffset(stage,e),unit=this.markerUnit||1,hit=this.projected?.slice().sort((a,b)=>(b.p.id===this.root.dataset.mapFocus?1:0)-(a.p.id===this.root.dataset.mapFocus?1:0)).find(p=>{const r=(p.p.id===this.root.dataset.mapFocus?17:12)*unit,dx=Math.abs(p.x-(400+offset[0])),y=220+offset[1];return dx<r+4*unit&&y>=p.y-3*r-4*unit&&y<=p.y+5*unit});if(hit)this.markerTimer=setTimeout(()=>{if(!this.disposed)openCandidate(hit.p.id)},230)}};
  stage.addEventListener('pointerup',finish);stage.addEventListener('pointercancel',finish);
  stage.addEventListener('keydown',e=>{const direction={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(!direction)return;e.preventDefault();const w=mapWorld(...this.center),size=MAP_WORLD_PIXELS*Math.pow(2,this.zoom);this.center=mapCoordinate(w[0]+direction[0]*100/size,w[1]+direction[1]*100/size);this.invalidate();this.schedule()});
 }
 dispose(){this.disposed=true;this.controller?.abort();clearTimeout(this.timer);clearTimeout(this.markerTimer);if(this.frame!==null)cancelAnimationFrame(this.frame);this.snapshot=null;liveMapControllers.delete(this)}
}
function mountMaps(){for(const controller of liveMapControllers)if(!controller.root.isConnected)controller.dispose();for(const root of document.querySelectorAll('.location-map:has(.map-stage)'))if(!mapControllers.has(root))mapControllers.set(root,new TravelMap(root))}
let mapMountFrame=null;new MutationObserver(()=>{if(mapMountFrame===null)mapMountFrame=requestAnimationFrame(()=>{mapMountFrame=null;mountMaps()})}).observe(document.body,{childList:true,subtree:true});
document.addEventListener('click',e=>{const button=e.target.closest('[data-map-zoom-action],[data-map-retry]');if(!button||button.disabled)return;const root=button.closest('.location-map'),map=mapControllers.get(root);if(!map)return;if(button.hasAttribute('data-map-retry'))map.schedule(0);else map.command(button.dataset.mapZoomAction)});
mountMaps();
