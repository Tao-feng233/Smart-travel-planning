/* Shared selection map, provisional timeline and actionable guidance. */
let mapFocusId='',miniWorkspace='',miniSignature='',miniCollapsed=false,timelinePinned=false,timelineHideTimer=null,mealAdvanceTimer=null;
const mealNames={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'};
function timelineEntries(){return workspace?.timeline?.entries||[]}
function activeMealKey(){return (mealDate||workspace?.requirements.start_date||'')+'|'+mealPeriod}
function mealSlots(){return workspace?.timeline?.meal_slots||[]}
function nextMealSlot(after=''){const slots=mealSlots(),choices=workspace.meal_choices||{};const start=after?slots.findIndex(x=>x.key===after)+1:0;return slots.slice(Math.max(0,start)).find(x=>!choices[x.key]&&!x.included_in_room)||(!after?slots.find(x=>!choices[x.key]&&!x.included_in_room):null)}
function travelTimeText(entry){
 if(['route','unknown_route'].includes(entry.kind)&&entry.route_minutes==null)return '出发、抵达时间待路线查询';
 if(entry.kind==='transfer_plan')return (entry.time||'待定')+'–'+(entry.end||'待定')+' · 建议准备区间';
 return (entry.time?entry.time+' 出发':'出发时间待查询')+(entry.end?' · '+entry.end+' 预计抵达'+(entry.buffer_minutes?'（含缓冲）':''):'');
}
function selectTimelineSlot(entry){
 if(busy)return;
 if(['route','unknown_route','transfer_plan'].includes(entry.kind)){const label=entry.kind==='transfer_plan'?'接驳或候车准备':timelineMode(entry);$('#info-title').textContent=entry.name;$('#info-content').innerHTML=`<p>${esc(entry.date)} · ${esc(travelTimeText(entry))}</p><p>${esc(label)}${entry.route_minutes!=null?'，道路预计 '+esc(entry.route_minutes)+' 分钟':''}${entry.buffer_minutes!=null?'，另留 '+esc(entry.buffer_minutes)+' 分钟缓冲':''}</p><p>${esc(entry.reason||'具体路线与等候条件需核实。')}</p>${entry.source?.queried_at?`<small>路线查询时间：${esc(entry.source.queried_at)}</small>`:''}`;$('#info-dialog').showModal();return}
 if(entry.kind==='meal'){
  mealDate=entry.date;mealPeriod=entry.period;foodAnchor='';switchTab('food');
  if(entry.candidate_id)focusCandidate(entry.candidate_id,true);
  action('search_foods',{meal_date:entry.date,meal_period:entry.period});return;
 }
 if(entry.kind==='transport'){transportDirection=entry.direction||'return';switchTab('transport');if(entry.candidate_id)focusCandidate(entry.candidate_id,true);return}
 if(entry.candidate_id)focusCandidate(entry.candidate_id,true);
}
function focusCandidate(id,show=true){const p=workspace.catalog[id]||(workspace.hotel?.id===id?workspace.hotel:null);if(!p)return;mapFocusId=id;referenceFocus=id;const view=({spot:'spot',hotel:'hotel',food:'food',train:'transport',flight:'transport'})[p.kind];if(view)switchTab(view,id);if(show)openCandidate(id);else syncMiniMap();}
function conflictHTML(c){return `<div class="inline-conflict ${c.level==='advisory'?'advisory':''}" role="alert"><strong>${esc(c.date||'安排提醒')} · ${c.level==='advisory'?'建议调整':'时间冲突'}</strong><p>${esc(c.message||'请核对当前安排。')}</p><div><button class="text-button" data-conflict-jump="${c.view==='food'?'food':'spots'}" data-conflict-period="${esc(c.meal_period||'')}" data-conflict-date="${esc(c.date)}" data-conflict-ids="${esc(JSON.stringify(c.candidate_ids||[]))}">${c.view==='food'?'查看相关餐厅 / 调整餐次':'查看相关景点 / 调整游玩日期'}</button><button class="text-button" data-conflict-jump="transport" data-conflict-direction="${esc(c.direction||'return')}" data-conflict-date="${esc(c.date)}">查看${c.direction==='outbound'?'去程':'返程'}班次</button><button class="text-button" data-reorder>按位置优化并重排</button></div></div>`}
function candidateConflicts(id){const cs=[...(workspace.timeline?.conflicts||[])];if(workspace.ui?.conflict)cs.push({...workspace.ui.conflict,message:workspace.ui.message||workspace.ui.error||'当前安排未通过时间校验，请调整后重排。'});return cs.filter(c=>(c.candidate_ids||[]).includes(id)||['selected_transport','selected_return'].some(k=>workspace[k]?.id===id&&c.direction===(k==='selected_return'?'return':'outbound')))}
const experienceCard=card;card=function(p){const html=experienceCard(p),cs=candidateConflicts(p.id);return cs.length?html.replace('</article>',cs.map(conflictHTML).join('')+'</article>'):html};
const experienceSpotCard=spotCard;spotCard=function(p){const html=experienceSpotCard(p);return html.replace('</article>',candidateConflicts(p.id).map(conflictHTML).join('')+'</article>')};
const experienceCandidateBody=candidateBody;candidateBody=function(p){return candidateConflicts(p.id).map(conflictHTML).join('')+experienceCandidateBody(p)};
const experienceOpenCandidate=openCandidate;openCandidate=function(id,...args){mapFocusId=id;experienceOpenCandidate(id,...args);const mini=$('#selection-minimap');if(mini)$('#candidate-dialog').append(mini);syncMiniMap()};

function ensureExperienceUI(){
 if($('#selection-minimap'))return;
 const mini=document.createElement('section');mini.id='selection-minimap';mini.className='selection-minimap';mini.setAttribute('aria-label','可拖动的选择地图');mini.innerHTML='<div class="mini-handle" tabindex="0" aria-label="拖动小地图，方向键可移动"><strong>位置预览</strong><button class="ghost" id="mini-collapse" aria-label="收起小地图" aria-expanded="true">−</button></div><button id="mini-expand" class="ghost" aria-label="展开选择地图" aria-expanded="false" title="拖动移动，点击展开地图" hidden><svg viewBox="0 0 28 28" aria-hidden="true"><path d="M3 7.5 10 5l8 3 7-2.5v16L18 24l-8-3-7 2.5Z"/><path d="M10 5v16m8-3v6"/><path class="mini-pin" d="M22 10c0 3-4 7-4 7s-4-4-4-7a4 4 0 1 1 8 0Z"/><circle cx="18" cy="10" r="1.3"/></svg><span>地图</span></button><div class="mini-body"></div>';$('#application').append(mini);
 const rail=document.createElement('aside');rail.id='selection-timeline';rail.className='selection-timeline';rail.setAttribute('aria-label','旅行时间轴');rail.innerHTML='<div class="timeline-title"><strong>旅行时间轴</strong><button id="timeline-pin" class="text-button" aria-label="固定时间轴面板位置" aria-pressed="false">固定面板</button></div><button class="text-button" id="timeline-optimize">智能调整时间轴</button><button class="text-button" data-action="refresh_routes">核对交通时间</button><button class="text-button" data-action="review_timeline">检查安排合理性</button><button class="text-button" data-preview-route-issues hidden>查看通行提醒</button><p class="timeline-note"></p><div class="timeline-entries"></div>';$('#application').append(rail);
 const photo=document.createElement('dialog');photo.id='photo-dialog';photo.innerHTML='<div class="dialog-head"><h2>来源参考图片</h2><button data-close="photo-dialog" class="ghost">关闭</button></div><img alt="来源参考图片"><p>来源原图按窗口比例展示，拍摄日期与现场情况请以实际为准。</p>';document.body.append(photo);
 $('#candidate-dialog').addEventListener('close',()=>{const mini=$('#selection-minimap');if(mini)$('#application').append(mini)});
 const panel=$('.workspace');panel.addEventListener('pointerenter',()=>showTimeline());panel.addEventListener('pointerleave',hideTimeline);rail.addEventListener('pointerenter',()=>showTimeline());rail.addEventListener('pointerleave',hideTimeline);rail.addEventListener('focusin',()=>showTimeline());rail.addEventListener('focusout',hideTimeline);
 $('#timeline-optimize').onclick=()=>{if(!busy)action('adjust_timeline')};
  $('#timeline-pin').onclick=()=>{timelinePinned=!timelinePinned;$('#timeline-pin').setAttribute('aria-pressed',String(timelinePinned));$('#timeline-pin').textContent=timelinePinned?'取消固定面板':'固定面板';if(!timelinePinned)hideTimeline()};
 let drag=null,suppressExpand=false;
 $('#mini-collapse').onclick=()=>setMiniCollapsed(true);
 $('#mini-expand').onclick=e=>{if(suppressExpand&&e.detail){e.preventDefault();e.stopPropagation();return}setMiniCollapsed(false)};
 const installDrag=source=>{
  source.addEventListener('pointerdown',e=>{
   if(e.button!==0||source.id!=='mini-expand'&&e.target.closest('button'))return;
   if(source.id!=='mini-expand')e.preventDefault();
   const r=mini.getBoundingClientRect();drag={id:e.pointerId,source,x:e.clientX,y:e.clientY,dx:e.clientX-r.left,dy:e.clientY-r.top,moved:false};source.setPointerCapture(e.pointerId);
  });
  source.addEventListener('pointermove',e=>{
   if(drag?.id!==e.pointerId||drag.source!==source)return;
   if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)>5)drag.moved=true;
   if(!drag.moved)return;e.preventDefault();mini.classList.add('mini-dragging');moveMini(e.clientX-drag.dx,e.clientY-drag.dy);
  });
  const end=e=>{
   if(drag?.id!==e.pointerId||drag.source!==source)return;
   if(drag.moved&&source.id==='mini-expand'){suppressExpand=true;setTimeout(()=>{suppressExpand=false},0)}
   drag=null;mini.classList.remove('mini-dragging');if(source.hasPointerCapture(e.pointerId))source.releasePointerCapture(e.pointerId);
  };
  source.addEventListener('pointerup',end);source.addEventListener('pointercancel',end);source.addEventListener('lostpointercapture',end);
  source.addEventListener('keydown',e=>{const step={ArrowLeft:[-20,0],ArrowRight:[20,0],ArrowUp:[0,-20],ArrowDown:[0,20]}[e.key];if(!step)return;e.preventDefault();const r=mini.getBoundingClientRect();moveMini(r.left+step[0],r.top+step[1])});
 };
 installDrag(mini.querySelector('.mini-handle'));installDrag($('#mini-expand'));

}
function moveMini(x,y){const el=$('#selection-minimap'),r=el.getBoundingClientRect();el.style.left=Math.max(0,Math.min(Math.max(0,innerWidth-r.width),x))+'px';el.style.top=Math.max(0,Math.min(Math.max(0,innerHeight-r.height),y))+'px';el.style.bottom='auto';el.style.right='auto'}
function setMiniCollapsed(value){miniCollapsed=value;const el=$('#selection-minimap'),position=el.classList.contains('collapsed')!==value?el.getBoundingClientRect():null;el.classList.toggle('collapsed',value);el.querySelector('.mini-body').hidden=value;el.querySelector('.mini-handle').hidden=value;$('#mini-expand').hidden=!value;$('#mini-expand').setAttribute('aria-expanded',String(!value));$('#mini-collapse').setAttribute('aria-expanded',String(!value));if(position)moveMini(position.left,position.top);if(!value)syncMiniMap()}
function miniPoints(){const cat=workspace.catalog,ps=(workspace.spot_coverage?.active_ids||workspace.selected_spots).map(id=>cat[id]).filter(p=>p?.location);ps.push(...[...new Set(Object.values(workspace.stay_plan?.assignments||{}).map(x=>x.hotel_id).filter(Boolean))].map(id=>cat[id]).filter(p=>p?.location));if(!workspace.stay_hotels&&workspace.hotel?.location)ps.push(workspace.hotel);ps.push(...Object.values(workspace.meal_choices||{}).filter(c=>c.mode!=='self'&&workspace.meal_mode!=='self').map(c=>cat[c.food_id]).filter(p=>p?.location));if(cat[mapFocusId]?.location)ps.push(cat[mapFocusId]);return [...new Map(ps.map(p=>[p.id,p])).values()].filter(validMapPoint)}
function syncMiniMap(){
 if(!workspace||$('#application').hidden)return;ensureExperienceUI();const el=$('#selection-minimap');
 if(workspace.id!==miniWorkspace){miniWorkspace=workspace.id;miniSignature='';mapFocusId='';el.querySelector('.mini-body').innerHTML='';miniCollapsed=innerWidth<850;setMiniCollapsed(miniCollapsed)}
 const points=miniPoints();el.hidden=!points.length;
 if(!points.length)return;
 const roads=!workspace.plan?.stale?(workspace.plan?.days||[]).flatMap(d=>(d.events||[]).flatMap(e=>e.route?.polylines||[])):[];
 const signature=JSON.stringify([points.map(p=>[p.id,p.location]),mapFocusId,roads]);el.querySelector('.mini-handle strong').textContent=workspace.catalog[mapFocusId]?.name||'已选地点与路线';if(signature===miniSignature)return;miniSignature=signature;
 let root=el.querySelector('.location-map');
 if(!root){el.querySelector('.mini-body').innerHTML=interactiveMapHTML(points,'',mapFocusId)+'<div class="mini-color-key"><span class="spot">景点</span><span class="hotel">住宿</span><span class="food">餐饮</span><span class="focus">当前地点</span></div>';root=el.querySelector('.location-map');root.querySelectorAll('.map-legend,.map-caption,.map-gesture-hint').forEach(e=>e.remove());root.dataset.mapKey=workspace.id+':mini';mountMaps()}
 else {root.dataset.mapFocus=mapFocusId;root.dataset.mapPoints=JSON.stringify(points);root.dataset.mapRoads=JSON.stringify(roads);const map=mapControllers.get(root);if(map){map.points=points;map.roads=roads.map(line=>String(line).split(';').map(x=>x.split(',').map(Number)).filter(x=>x.length===2&&x.every(Number.isFinite)).map(x=>mapWorld(...x)));map.original=mapFitCenter(points);map.fit=fitMapZoom(points);map.sync();const focused=points.find(p=>p.id===mapFocusId);if(focused){const camera=mapWorld(...map.center),target=mapWorld(...focused.location.split(',').map(Number)),size=MAP_WORLD_PIXELS*Math.pow(2,map.zoom);if(Math.abs(worldDelta(target[0]-camera[0])*size)>330||Math.abs((target[1]-camera[1])*size)>175){map.center=focused.location.split(',').map(Number);map.invalidate();map.schedule(200)}}map.drawSoon()}}
}
function positionTimeline(){const el=$('#selection-timeline');if(!el)return;const r=$('.workspace').getBoundingClientRect();el.style.left=Math.max(8,r.left-176)+'px';el.style.top=Math.max(75,r.top+90)+'px';el.style.maxHeight=Math.max(160,Math.min(innerHeight-100,r.height-115))+'px'}
function showTimeline(){clearTimeout(timelineHideTimer);if(!timelineEntries().length||innerWidth<950)return;$('#selection-timeline')?.classList.add('visible');positionTimeline()}
function hideTimeline(){clearTimeout(timelineHideTimer);timelineHideTimer=setTimeout(()=>{const el=$('#selection-timeline');if(!timelinePinned&&!el?.matches(':hover')&&!$('.workspace').matches(':hover')&&!el?.contains(document.activeElement))el?.classList.remove('visible')},180)}
function timelineMode(e){
 if(e.transport_kind==='flight')return '飞机';
 if(e.transport_kind==='train')return /[GDC]\d/.test(e.name||'')?'高铁／动车':'火车';
 return ({walking:'步行',transit:'公交／地铁',driving:'驾车／打车参考'})[e.mode]||'交通方式待查询';
}
// 选择阶段（还没生成计划书）只显示"上午/下午/晚上 + 顺序"，不显示具体时刻：
// 此时排期尚未统一规划，给出 10:00、13:15 这类时刻会误导。
function timelinePhaseMode(){return !workspace?.plan}
function phaseOf(e){
 const m=String(e.time||'').match(/^(\d{1,2}):/);
 if(!m)return '待定';
 const hour=Number(m[1]);
 if(hour<11)return '上午';
 if(hour<17)return '下午';
 return '晚上';
}
function phaseRank(p){return {'上午':0,'下午':1,'晚上':2,'待定':3}[p]??3}
function groupedTimelineHTML(entries){
 const byDate=new Map();
 entries.forEach(e=>{
  if(!byDate.has(e.date))byDate.set(e.date,[]);
  byDate.get(e.date).push(e);
 });
 let out='';
 for(const [date,rows] of byDate){
  rows.sort((a,b)=>phaseRank(phaseOf(a))-phaseRank(phaseOf(b)));
  const byPhase=new Map();
  rows.forEach(e=>{
   const p=phaseOf(e);
   if(!byPhase.has(p))byPhase.set(p,[]);
   byPhase.get(p).push(e);
  });
  out+=`<div class="timeline-day"><small class="timeline-day-label">${esc(date.slice(5))}</small>`;
  for(const [phase,group] of byPhase){
   // 交通段在选择阶段不显示分钟数，只提示"需车程 · 待核对"。
   const names=group.map(e=>{
    const leg=['route','unknown_route','transport','transfer_plan'].includes(e.kind);
    return esc(leg?e.name+'（需车程 · 待核对）':e.name);
   }).join(' · ');
   out+=`<button class="timeline-phase" data-timeline-key="${esc(group[0].key)}" title="${esc(group.map(e=>e.reason||e.name).join(' / '))}"><small class="timeline-phase-label">${esc(phase)}</small><span>${names}</span></button>`;
  }
  out+='</div>';
 }
 return out;
}
function phaseTightNotice(){
 const issues=(workspace?.timeline_review?.issues||[]).filter(i=>!i.optimize||i.code==='timeline_load');
 if(!issues.length)return '';
 const days=[...new Set(issues.map(i=>i.date).filter(Boolean))];
 const label=days.length?days.map(d=>d.slice(5)).join('、'):'部分日子';
 return `<p class="timeline-phase-notice">${esc(label)} 安排可能偏紧，生成计划书时会统一调整。</p>`;
}
function timelineEntryHTML(e){
 const road=['route','unknown_route'].includes(e.kind),waiting=e.kind==='transfer_plan',train=e.kind==='transport';
 const status=road?(e.route_minutes!=null?'交通预计':'交通待核对'):waiting?'准备预留':e.confirmed?'已确认':'建议';
 const knownRoad=road&&e.route_minutes!=null;const timing=road||train?`<time>${(knownRoad||train)&&e.time?esc(e.time)+' 出发':'出发时间待查询'}</time>${(knownRoad||train)&&e.end?`<small class="timeline-arrival">${e.end_date&&e.end_date!==e.date?esc(e.end_date.slice(5))+' ':''}${esc(e.end)} ${train?'班次抵达':'预计抵达'}${!train&&e.buffer_minutes?'（含缓冲）':''}</small>`:''}`:`<time>${esc(e.time)}</time>`;
 const travel=road||train?`<small class="timeline-transport-mode">${esc(timelineMode(e))}</small>${e.route_minutes!=null?`<small>路程预计 ${esc(e.route_minutes)} 分钟${e.buffer_minutes!=null?' · 另留 '+esc(e.buffer_minutes)+' 分钟缓冲':''}</small>`:road?'<small>交通耗时待查询</small>':''}`:'';
 const visit=['spot','spot_continue'].includes(e.kind)&&e.duration?`<small>建议游玩 ${esc(e.duration)} 分钟${e.includes_meal_break?' · 含用餐休息':''}${e.over_capacity?' · 待优化':''}</small>`:'';
 return `<button class="timeline-entry ${e.rest_type==='midday'?'midday-rest':''} ${road||waiting||train?'travel-leg':''} ${e.key===activeMealKey()&&tab==='food'?'active':''} ${e.confirmed?'confirmed':''}" title="${esc(e.reason||e.name)}" data-timeline-key="${esc(e.key)}"><small>${esc(e.date.slice(5))} · ${status}</small>${timing}<span>${esc(e.name)}</span>${travel}${waiting?'<small>候车／安检或接驳准备 · 建议预留</small>':''}${e.rest_type==='midday'?`<small>休息至 ${esc(e.end||'')} · 建议安排</small>`:''}${visit}</button>`;
}
function syncTimeline(){
 ensureExperienceUI();const entries=timelineEntries(),root=$('#selection-timeline');
 root.querySelector('.timeline-note').textContent=timelinePhaseMode()?'选择阶段 · 只显示时段与顺序；生成计划书后给出具体时刻':(workspace.timeline?.provisional?(workspace.timeline?.route_status==='checked'?'动态建议 · 已核对道路':workspace.timeline?.route_status==='partial'?'动态建议 · 部分交通待核对':'初步建议 · 交通待查询，核对后自动更新时间'):'计划安排 · 游玩与交通分开展示');
 root.querySelector('.timeline-note').title=workspace.timeline?.route_message||'';root.querySelector('[data-preview-route-issues]').hidden=!workspace.timeline?.route_message;
 // 选择阶段只给"日期 + 上午/下午/晚上 + 顺序"，具体时刻留到生成计划书后。
 const phaseMode=timelinePhaseMode();
 root.querySelector('.timeline-entries').innerHTML=phaseMode?groupedTimelineHTML(entries)+phaseTightNotice():entries.map(timelineEntryHTML).join('');
 positionTimeline();if(!entries.length)root.classList.remove('visible');else if($('.workspace').matches(':hover'))showTimeline();
}
const experienceRender=render;render=function(){experienceRender();if(workspace){syncTimeline();syncMiniMap()}};
const experienceFoodHTML=foodHTML;foodHTML=function(){const html=experienceFoodHTML(),slots=mealSlots(),index=slots.findIndex(x=>x.key===activeMealKey());const done=slots.filter(x=>workspace.meal_choices?.[x.key]||x.included_in_room).length;return `<div class="meal-sequence"><strong>${mealDate||workspace.requirements.start_date||'日期待定'} · ${mealNames[mealPeriod]}</strong><span>${index>=0?'第 '+(index+1)+' / '+slots.length+' 个可安排餐次 · ':''}已安排 ${done} 餐</span><small>按饭点选择周边餐厅，选定或自行安排后自动进入下一餐。可点时间轴返回修改，也可完成餐饮并保留其余餐次自行安排。</small></div>`+html};
const experienceFinishJob=finishJob;finishJob=function(j,name,args={}){
 const previousSlot=activeMealKey(),previousMeals=JSON.stringify(workspace?.meal_choices||{}),wid=workspace?.id,epoch=tripEpoch;
 experienceFinishJob(j,name,args);
 if(j.error&&j.ui?.conflict){$('#error').innerHTML=conflictHTML({...j.ui.conflict,message:j.error})}
 const performed=(name||j.action)==='chat'?workspace?.last_action:(name||j.action);
 if(j.status!=='completed')return;
 if(performed==='meal_choice'&&args.mode!=='remove'&&(args.meal_mode!=='self'||args.meal_date)){
  const before=JSON.parse(previousMeals),changed=Object.keys(workspace.meal_choices||{}).find(key=>JSON.stringify(before[key])!==JSON.stringify(workspace.meal_choices[key]));const chosenKey=args.meal_date&&args.meal_period?args.meal_date+'|'+args.meal_period:changed||previousSlot;
  const next=nextMealSlot(chosenKey);clearTimeout(mealAdvanceTimer);clearTimeout(foodRefreshTimer);
  if(next){mealDate=next.date;mealPeriod=next.period;foodAnchor='';render();toast('已保存当前餐次，接下来选择 '+next.date+' '+mealNames[next.period]);mealAdvanceTimer=setTimeout(()=>{if(tripEpoch===epoch&&workspace.id===wid&&!busy)action('search_foods',{meal_date:next.date,meal_period:next.period})},220)}
  else toast('后续餐次已查看完，可完成餐饮并保留其余餐次自行安排；仍可返回补选或修改。');
 }
};
// Known action labels are converted only after escaping/model markdown rendering.
const experienceMessageHTML=messageHTML;messageHTML=function(text,context){let html=experienceMessageHTML(text,context);if(context?.role==='user')return html;const labels=[['生成旅行计划书','plan'],['生成旅游计划书','plan'],['生成计划书','plan'],['重新生成计划书','plan'],['完成景点选择','complete_spots'],['完成住宿选择','complete_hotel'],['完成餐饮选择','complete_food']];if(!/下一步|可以|请|重新生成/.test(text))return html;const pattern=new RegExp(labels.map(([label])=>label).sort((a,b)=>b.length-a.length).join('|'),'g');return html.split(/(<[^>]+>)/).map((part,i)=>i%2?part:part.replace(pattern,label=>`<button class="inline-execute" data-action="${labels.find(x=>x[0]===label)[1]}">${label}<span aria-hidden="true"> ↗</span></button>`)).join('')};

document.addEventListener('click',e=>{
 if(e.target.closest('[data-preview-route-issues]')){const data=workspace.timeline?.route_issues;$('#info-title').textContent='通行与时间核对';$('#info-content').innerHTML=data&&typeof diagnosticHTML==='function'?diagnosticHTML(data):`<p>${esc(workspace.timeline?.route_message||'通行尚需核实。')}</p>`;$('#info-dialog').showModal();return}
 const slot=e.target.closest('[data-timeline-key]');if(slot){const entry=timelineEntries().find(x=>x.key===slot.dataset.timelineKey);if(entry)selectTimelineSlot(entry);return}
 const jump=e.target.closest('[data-conflict-jump]');if(jump){if(jump.dataset.conflictJump==='transport'){transportDirection=jump.dataset.conflictDirection||'return';switchTab('transport');document.querySelector('#transport-date')?.focus()}else{if(jump.dataset.conflictJump==='food'){mealDate=jump.dataset.conflictDate||mealDate;mealPeriod=jump.dataset.conflictPeriod||mealPeriod;switchTab('food')}let ids=[];try{ids=JSON.parse(jump.dataset.conflictIds)}catch{}if(ids[0])focusCandidate(ids[0],true);else if(jump.dataset.conflictJump!=='food')switchTab('spot')}return}
 if(e.target.closest('[data-reorder]')&&!busy){$('#candidate-dialog').close();action('chat',{},'请按位置优化当前景点顺序并重新生成计划书，保留已选班次、景点、餐厅和我明确指定的日期时段。若仍不可行，请说明具体日期和需要调整的地点。');return}
 const image=e.target.closest('.place-photos img');if(image){const dialog=$('#photo-dialog'),img=dialog.querySelector('img');img.src=image.currentSrc||image.src;img.alt=image.alt;if(!dialog.open)dialog.showModal();return}
});
document.addEventListener('load',e=>{const img=e.target;if(!img.matches?.('.place-photos img'))return;const figure=img.closest('figure');if(!figure)return;figure.style.width=Math.min(img.naturalWidth,figure.closest('.room')?240:560)+'px';const caption=figure.querySelector('figcaption');caption.hidden=img.naturalWidth>=600;if(!caption.hidden)caption.textContent='来源仅提供 '+img.naturalWidth+'×'+img.naturalHeight+' 图片，按原比例显示';},true);
let focusTimer=null;document.addEventListener('pointerover',e=>{const card=e.target.closest('[data-open-candidate]');if(!card||e.relatedTarget&&card.contains(e.relatedTarget))return;const id=card.dataset.openCandidate;if(id===mapFocusId)return;clearTimeout(focusTimer);focusTimer=setTimeout(()=>{if(workspace?.catalog[id]){mapFocusId=id;syncMiniMap()}},100)});
window.addEventListener('resize',()=>{positionTimeline();const mini=$('#selection-minimap');if(mini&&!mini.hidden){if(innerWidth<850&&!miniCollapsed)setMiniCollapsed(true);const r=mini.getBoundingClientRect();moveMini(r.left,r.top)}});
