let workspace=null,tab='spot',busy=false,renderedMessages='',detailOpenId=null,jobUI=null,destinationPage=1,transportMode='train',transportDirection='outbound',trainType='all',timeStart='',timeEnd='',replaceTarget=null,liveReply='',liveSteps=[],workbenchExpanded=false,transportDates={},mealDate='',mealPeriod='lunch',foodAnchor='',pickedHotelOpen=null,stayOpenDate='';
const actionViews={discover_destinations:'spot',choose_destination:'spot',spots_page:'spot',dismiss_spot:'spot',complete_spots:'hotel',complete_hotel:'transport',skip_hotel:'transport',plan:'plan',optimize_plan:'plan',complete_food:'plan',visit_schedule:'spot',search_foods:'food',meal_choice:'food',search_hotels:'hotel',hotel_detail:'hotel',select_room:'hotel',train:'transport',flight:'transport',search_spots:'spot',ticket:'spot',weather:'weather'};
const sceneNames={spot:'目的地与景点',hotel:'住宿选择',transport:'往返交通',weather:'天气',plan:'旅行计划书',knowledge:'资料与依据',food:'餐饮选择',map:'旅行地图'};
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const mode=m=>({walking:'步行',driving:'驾车 / 打车',transit:'公交 / 地铁'}[m]||m);
function link(url,label){try{const u=new URL(url);if(u.protocol!=='https:'&&u.protocol!=='http:')return esc(label);return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`}catch{return esc(label)}}
function src(s){return s?`<details class="source"><summary>${esc(s.name)} · 查询依据</summary>${link(s.url,'查看数据来源 ↗')}<br>查询时间：${esc(s.queried_at?.replace('T',' '))}<br>${esc(s.kind||'查询事实')}</details>`:''}
async function api(url,opts={}){const method=(opts.method||'GET').toUpperCase(),headers={...(opts.headers||{})};if(method!=='GET'){headers['Content-Type']='application/json';if(csrfToken)headers['X-CSRF-Token']=csrfToken}const r=await fetch(url,{...opts,headers,credentials:'same-origin'});if(!r.ok){let d;try{d=await r.json()}catch{}if(r.status===401&&currentUser)showGate('登录已过期，请重新登录后继续。');const e=new Error(d?.detail||`请求失败 ${r.status}`);e.code=r.status;throw e}return r.json()}
function error(msg){$('#error').hidden=!msg;$('#error').textContent=msg||''}
// Restore only a button's own eligibility; never capture temporary busy state as eligibility.
const disabledBeforeBusy=new WeakMap();
function setBusy(v){busy=v;$('#progress').hidden=!v;document.querySelectorAll('#application button:not([data-tab]):not(#history-toggle):not(#conversation-history):not(#cancel-task):not(#auto-selection-stop):not(#restore-trip):not([data-info]):not(#feedback-button):not(#selected-button):not(#expand-workbench):not(#sources-button):not(#map-button)').forEach(b=>{if(!disabledBeforeBusy.has(b))disabledBeforeBusy.set(b,b.disabled);b.disabled=v||!!workspace?.archived||disabledBeforeBusy.get(b)});$('#message').disabled=!!workspace?.archived;$('#cancel-task').disabled=!v;}
function switchTab(next,focusId=null){if(!sceneNames[next])return;tab=next;render();const card=focusId?[...document.querySelectorAll('[data-candidate]')].find(x=>x.dataset.candidate===focusId):null;$('#content').scrollTo({top:card?Math.max(0,card.offsetTop-$('#content').offsetTop):0,behavior:'smooth'});const active=$(`.tabs [data-tab="${next}"]`);active?.scrollIntoView({behavior:'smooth',block:'nearest',inline:'nearest'});if(innerWidth<=900)$('.workspace').scrollIntoView({behavior:'smooth',block:'start'});if(card){card.classList.add('just-updated');setTimeout(()=>card.classList.remove('just-updated'),2400)}}
function readable(text){return String(text??'').replaceAll('\\r\\n','\n').replaceAll('\\n','\n').replaceAll('\\t','    ')}
function messageHTML(text){const lines=readable(text).split('\n'),blocks=[];let list=[];const inline=s=>esc(s).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');const flush=()=>{if(list.length){blocks.push('<ul>'+list.map(s=>'<li>'+inline(s)+'</li>').join('')+'</ul>');list=[]}};for(const line of lines){if(/^[-*] /.test(line)){list.push(line.slice(2));continue}flush();if(/^#{1,3} /.test(line))blocks.push('<h3>'+inline(line.replace(/^#{1,3} /,''))+'</h3>');else if(line.trim())blocks.push('<p>'+inline(line)+'</p>')}flush();return blocks.join('');}
function processHTML(steps){return steps?.length?`<details class="process-details"><summary>处理过程 · ${steps.length}项</summary><ul>${steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></details>`:'';}
function renderLive(){if(!busy||!liveReply&&!liveSteps.length){$('#live-reply')?.remove();return}let el=$('#live-reply');if(!el){el=document.createElement('div');el.id='live-reply';el.className='message';$('#messages').append(el)}const nearBottom=$('#messages').scrollHeight-$('#messages').scrollTop-$('#messages').clientHeight<140;const open=el.querySelector('details')?.open;el.innerHTML=`<span class="speaker">识途</span>${processHTML(liveSteps)}<div class="bubble streaming">${messageHTML(liveReply,jobUI)}</div>`;if(open&&el.querySelector('details'))el.querySelector('details').open=true;if(nearBottom)$('#messages').scrollTop=$('#messages').scrollHeight;}
function setWorkbenchExpanded(value){workbenchExpanded=value;$('#application').classList.toggle('workbench-expanded',value);$('#workbench-shade').hidden=!value;$('#expand-workbench').setAttribute('aria-expanded',String(value));$('#expand-workbench').textContent=value?'›':'‹';}
function hintText(text){return String(text||'').replaceAll('{位置}',innerWidth<=700?'下方':'右侧')}
function guideButton(cta){if(!cta)return '';const attr=cta.view&&sceneNames[cta.view]?`data-tab="${cta.view}"`:cta.settings?'data-open-settings':Object.hasOwn(actionViews,cta.action)?`data-action="${cta.action}"`:'';return attr?`<button ${attr}>${esc(cta.label)} →</button>`:''}
function guidanceHTML(ui,reply=false){if(!ui)return '';if(reply)return '';return ui.status==='loading'?`<div class="scene-guide"><span>${esc(ui.title)}</span><span class="spinner" aria-hidden="true"></span></div>`:'';}
function initialView(w){const view=w.ui?.view;return sceneNames[view]?view:w.plan?'plan':w.hotel?'hotel':'spot'}
async function action(name,args={},text=''){
 if(busy||!workspace||workspace.archived)return;const wid=workspace.id,epoch=tripEpoch;liveReply='';liveSteps=[];
 const p=workspace.catalog?.[args.id],view=name==='complete_spots'&&Number(workspace.requirements.days)===1?'transport':(name==='place_detail'?args.view||tab:actionViews[name])||(name==='select'?({spot:'spot',hotel:'hotel',train:'transport',flight:'transport',food:'food'}[p?.kind]):null);
 jobUI={action:name,view,status:'loading',title:name==='chat'?'正在理解你的想法':name==='select'?'正在保存你的选择':`正在处理${sceneNames[view]||'旅行条件'}`,message:name==='chat'?'识别需求后，工作台会切换到对应内容。':'结果更新后，会告诉你下一步怎么做。'};
 if(name==='train'||name==='flight'){transportMode=name;transportDirection=args.direction||'outbound';args={...args,train_type:trainType,time_start:timeStart||undefined,time_end:timeEnd||undefined,departure_date:transportDates[transportDirection]||transportDate(transportDirection)}}
 if(view)tab=view;setBusy(true);render();error('');$('#reconnect-task').hidden=true;$('#progress-text').textContent=jobUI.title;
 try{
  const {job_id}=await api(`/api/workspaces/${wid}/actions`,{method:'POST',body:JSON.stringify({revision:workspace.revision,action:name,args,text,request_id:crypto.randomUUID()})});
  if(epoch!==tripEpoch)return;if(text){workspace.messages.push({role:'user',content:text});render();}
  await pollJob(wid,job_id,epoch,name,args);
 }catch(e){if(epoch===tripEpoch){error(e.message);$('#reconnect-task').hidden=false;if(text)$('#message').value=text}}finally{if(epoch===tripEpoch){jobUI=null;liveReply='';liveSteps=[];setBusy(false);render()}}
}
async function pollJob(wid,jid,epoch=tripEpoch,name='',args={}){
 runningJobId=jid;setBusy(true);let followedView=jobUI?.view||null;
 try{const streamed=await readEvents(jid,epoch);if(streamed){finishJob(streamed,name,args);return}for(let i=0;i<360;i++){
  await new Promise(r=>setTimeout(r,750));if(epoch!==tripEpoch||workspace?.id!==wid)return;const j=await api('/api/jobs/'+jid);if(epoch!==tripEpoch)return;$('#progress-text').textContent=j.progress;
  if(j.status==='running'&&j.ui?.status){applyWorkspacePreview(j.ui?.workspace_preview);jobUI={...j.ui,message:j.progress};if(sceneNames[j.ui.view]&&j.ui.view!==followedView){followedView=j.ui.view;switchTab(j.ui.view)}else render();}
  if(j.status!=='running'){finishJob(j,name,args);return;}
 }error('任务等待较长，请点击恢复任务进度查看最新状态。');$('#reconnect-task').hidden=false;
 }catch(e){if(epoch===tripEpoch){error(e.message);$('#reconnect-task').hidden=false}}finally{if(epoch===tripEpoch){jobUI=null;liveReply='';liveSteps=[];setBusy(false);render()}}
}
async function readEvents(jid,epoch){const controller=new AbortController();const r=await fetch('/api/jobs/'+jid+'/events',{credentials:'same-origin',signal:controller.signal});if(!r.ok||!r.headers.get('content-type')?.includes('text/event-stream')){controller.abort();return null}const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';try{while(true){if(epoch!==tripEpoch){controller.abort();return null}const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true}).replaceAll('\r\n','\n');let pos;while((pos=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,pos);buffer=buffer.slice(pos+2);const type=frame.split('\n').find(l=>l.startsWith('event:'))?.slice(6).trim();const raw=frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n');if(!raw)continue;const data=JSON.parse(raw);if(epoch!==tripEpoch)return null;if(type==='delta'){liveReply+=data.text;renderLive()}if(type==='replace'){liveReply=data.text;renderLive()}if(type==='progress'){applyWorkspacePreview(data.ui?.workspace_preview);await applyQueryControls(data.ui?.controls,true,epoch);liveSteps=data.ui?.process_steps||[];jobUI=data.ui;$('#progress-text').textContent='正在处理';if(sceneNames[data.ui?.view]&&tab!==data.ui.view){tab=data.ui.view;render()}renderLive()}if(type==='done')return data;}}return null}finally{reader.cancel().catch(()=>{});controller.abort();}}
function applyWorkspacePreview(preview){
 if(!preview||!busy||preview.id!==workspace?.id)return;
 workspace.catalog={...workspace.catalog,...(preview.catalog||{})};
 for(const key of ['spot_search','spot_page','hotel_query','food_query'])if(preview[key])workspace[key]=preview[key];
 if(typeof preview.discovery_mode==='boolean')workspace.discovery_mode=preview.discovery_mode;
 render();
}
function finishJob(j,name,args){applyQueryControls(j.ui?.controls,false);runningJobId=null;jobUI=null;liveReply='';liveSteps=[];setBusy(false);if(!j.workspace)return;workspace=j.workspace;const performed=(name||j.action)==='chat'?workspace.last_action:name||j.action;if(['train','flight'].includes(performed)&&workspace.transport){transportMode=performed;transportDirection=workspace.transport.direction||'outbound'}const pickedHotel=performed==='select'&&workspace.catalog[args.id]?.kind==='hotel'?args.id:null;
 if(performed==='hotel_detail'||pickedHotel)detailOpenId=pickedHotel||args.id||j.ui?.focus_id;
 // 选择住宿后直接打开该酒店的房型详情：房型已由后端在同一次操作里取回。
 if(pickedHotel&&workspace.catalog[pickedHotel]?.room_choices?.length)pickedHotelOpen=pickedHotel;
const view=j.ui?.view||actionViews[performed];if(sceneNames[view]&&tab!==view)switchTab(view);else render();if(j.status==='completed'&&workspace.feedback?.id===j.id)toast(workspace.feedback.text);else if(j.status==='completed'&&['search_spots','search_hotels','weather','train','flight'].includes(performed))toast('查询结果已更新，可在右侧查看');if(j.status==='completed'&&performed==='select'){const picked=workspace.catalog[args.id];if(picked&&['train','flight'].includes(picked.kind)&&picked.direction!=='return'&&(!workspace.selected_return||workspace.selected_return.selection_status==='recommended'))$('#return-dialog').showModal()}if(j.ui?.suggested_view&&j.status==='completed'){switchTab(j.ui.suggested_view);toast(workspace.next_step?.message||'往返班次已确认。');if(j.ui.suggested_view==='food'){const slot=nextMealSlot();if(slot){mealDate=slot.date;mealPeriod=slot.period;render();const epoch=tripEpoch,wid=workspace.id;setTimeout(()=>{if(epoch===tripEpoch&&workspace.id===wid&&!busy)action('search_foods',{meal_date:slot.date,meal_period:slot.period})},120)}}}else if(['train','flight'].includes(performed)&&j.status==='completed'){scrollToResults()}
 if(pickedHotelOpen&&pickedHotelOpen===pickedHotel)openRoomView(pickedHotel);pickedHotelOpen=null;
 // 选好某一晚的住宿后把那一晚折叠起来；查过某一晚则保持该晚展开。
 if(performed==='select'&&args.stay_date)stayOpenDate='';
 else if(performed==='search_hotels'&&args.stay_date)stayOpenDate=args.stay_date;
 if(j.error)error(j.error);}
// 打开某家酒店的房型详情：复用详情弹窗，与点“房型详情”看到的是同一个界面。
function openRoomView(id){
 if(!id)return;const p=workspace.catalog[id];if(!p||p.kind!=='hotel')return;
 if(typeof openCandidate==='function')openCandidate(id);
 else{const d=document.querySelector('#candidate-dialog');if(d&&!d.open)d.showModal()}
}

// 主住宿候选：以"全部已选景点的中心"为参照。适合一次定下全程，但要逐晚点选。
function centerStayHTML(){
 const w=workspace,hq=w.hotel_query||{};
 const ids=(hq.center_matches||[]).length?hq.center_matches:Object.keys(w.center_hotel_quotes||{});
 const found=ids.map(id=>w.catalog[id]).filter(p=>p&&!p.stale);
 const basis=hq.center_basis||'全部已选景点的中心';
 const head=`<div class="stay-head"><strong>住宿候选（以全部景点中心为参照）</strong><small>以${esc(basis)}为参照，位置对整天行程都方便。选哪一家就点它上面的“住这一晚”，逐晚指定，没选就是还没选。</small></div>`;
 if(!found.length)return `<div class="stay-plan center-stay">${head}<p class="panel-footnote">还没有以全部景点中心查过主住宿。点上面的“查询住宿”会同时给出这一组候选；也可以直接在住宿编排里逐晚挑。</p></div>`;
 return `<div class="stay-plan center-stay">${head}<div class="cards">${found.map(p=>card(p)).join('')}</div><p class="panel-footnote">想让某一晚单独换一家，在下面“住宿编排”里点那一晚的候选即可，不会影响其它夜晚。</p></div>`;
}
// 逐晚住宿编排：每晚一行。住宿只按晚指定，没选就显示"尚未选这一晚的住宿"，
// 不再有"主住宿覆盖其余夜晚"这种兜底。行内卡片点选只改这一晚。
function stayPlanHTML(){
 const w=workspace,stay=w.stay_plan;
 if(!stay||!(stay.rows||[]).length)return '';
 const assignedRows=(stay.assignments||{});
 const rows=(stay.rows||[]).map(row=>{
  const found=(row.candidate_ids||[]).map(id=>w.catalog[id]).filter(p=>p&&!p.stale);
  const assigned=assignedRows[row.date];
  const rowHotelId=assigned?assigned.hotel_id:(row.hotel_source==='explicit'?row.hotel_id:null);
  const picked=rowHotelId?w.catalog[rowHotelId]:null;
  const chosen=!!rowHotelId;
  const pickedName=(picked||{}).name||'已选住宿';
  const label=chosen?esc(pickedName)+'（这一晚已选）':esc(row.anchor_name||'待定')+' 周边';
  const sub=chosen?'这一晚单独指定'
   :'尚未选这一晚的住宿'+(row.anchor_is_station?'（次日赶车，建议靠近出发站）':'');
  const onway=(row.dinner_hint||[]).filter(x=>x.on_the_way).map(x=>x.name);
  // 已选好住宿的那一晚折叠候选，避免整页一直是长列表；要换再点开。
  const expanded=!chosen||stayOpenDate===row.date;
  const body=found.length?`<details class="stay-candidates"${expanded?' open':''}><summary>${chosen?'想换这一晚的住宿':'这一晚的候选'}（${found.length} 家）</summary><div class="cards stay-cards">${found.map(card).join('')}</div></details>`:'';
  return `<div class="stay-row${chosen?'':' needs-hotel'}" data-stay-date="${esc(row.date)}"><div class="stay-date"><strong>${esc(row.date)}</strong><small>住 1 晚</small></div><div class="stay-anchor"><span>${label}</span><small>${sub}</small>${onway.length?`<small>晚餐顺路：${esc(onway.join('、'))}</small>`:''}</div><div class="stay-actions">${found.length?`<small>${found.length} 家候选</small>`:`<button class="ghost" data-action="search_hotels" data-stay-date="${esc(row.date)}">查这晚</button>`}</div>${body}</div>`;
 }).join('');
 const pending=(stay.unassigned||[]).length;
 return `<div class="stay-plan"><div class="stay-head"><strong>住宿编排</strong><small>${esc(stay.note||'')}</small></div>${rows}${pending?`<p class="panel-footnote">还有 ${pending} 晚没有选住宿（${esc((stay.unassigned||[]).join('、'))}）：没选就是还没选，在对应夜晚点候选卡片即可。</p>`:`<p class="panel-footnote">${(stay.rows||[]).length} 晚都已选定。要换某一晚，点那一晚的候选卡片即可，不影响其它夜晚。</p>`}</div>`;
}
function empty(n,title,text,button='',actionName=''){return `<div class="empty"><span class="number">${n}</span><h3>${title}</h3><p>${text}</p>${button?`<button data-action="${actionName}">${button}</button>`:''}</div>`}
function workflowHTML(){return planningNavigation();}
function legacyWorkflowHTML(){
 const w=workspace,r=w.requirements,ready=r.city&&r.start_date&&r.days&&r.adults,spots=w.selected_spots.length,plan=w.plan&&!w.plan.stale,oneDay=Number(r.days)===1;
 const stayReady=oneDay||w.hotel&&!w.hotel.stale;
 const steps=[['目的地与景点',r.city||'目的地待定',!!w.spots_confirmed,'spot'],['住宿安排',oneDay?'一日游，可跳过':w.hotel?'住宿已选':'住宿待定',!!w.hotel||oneDay||w.stay_skipped,'hotel'],['往返交通',w.selected_transport&&w.selected_return?'往返已选':'班次待定',!!(w.selected_transport&&w.selected_return),'transport'],['旅行计划书',plan?'计划已生成':w.plan?'计划需更新':'等待生成',!!plan,'plan']];
 const current=({spot:0,hotel:1,transport:2,weather:2,plan:3}[tab]??0);
 return steps.map((s,i)=>`<button ${s[3]==='conditions'?'data-open-settings':`data-tab="${s[3]}"`} class="flow-step ${i===current?'current':''} ${s[2]?'done':''}"><span>${s[2]?'✓':String(i+1).padStart(2,'0')}</span><div><strong>${s[0]}</strong><small>${s[1]}</small></div></button>`).join('');
}
function selectionHTML(){const w=workspace;return `<div class="selected-section"><h3>景点 · ${w.selected_spots.length}个</h3><div class="selection-spots">${w.selected_spots.map(id=>`<button data-select="${esc(id)}">${esc(w.catalog[id]?.name||id)} ×</button>`).join('')||'<p>未选择景点</p>'}</div></div><div class="selected-section"><h3>住宿与房型</h3>${w.hotel?`<p>${esc(w.hotel.name)}${w.hotel.stale?' · 需重新查询':''}</p>${w.selected_room?`<p>${esc(w.selected_room.name)} · ${w.selected_room.quantity}间 · ¥${esc(w.selected_room.price??'待核实')}</p><p>${esc(w.selected_room.meal||'餐食待核实')} · ${esc(w.selected_room.cancel||'退改待核实')}</p>`:'<p>房型可选 · 尚未选择</p>'}`:'<p>未选择住宿</p>'}</div><div class="selected-section"><h3>用餐选择（可选）</h3>${Object.entries(w.meal_choices||{}).map(([key,c])=>`<p>${esc(key.replace('|',' · ').replace('breakfast','早餐').replace('lunch','午餐').replace('dinner','晚餐'))}：${c.mode==='chosen'?esc(w.catalog[c.food_id]?.name):'自行安排'}</p>`).join('')||'<p>自行安排</p>'}</div><div class="selected-section"><h3>往返交通</h3>${['selected_transport','selected_return'].map((key,i)=>`<p>${i?'返程':'去程'}：${w[key]?`${esc(w[key].name)} · ${esc(w[key].departure)}<br>${w[key].selection_status==='recommended'?'推荐 · 待确认':'已选定'}，尚未购票`:'未选择'}</p>`).join('')}</div>`;}
function render(){
 const w=workspace,r=jobUI?.requirements||w.requirements;
 $('#conversation-title').textContent=w.title||'旅行规划';$('#conversation-title').title=w.title||'';
 $('#workspace-title').textContent=tab==='spot'&&(!r.city||w.discovery_mode)?'目的地推荐':r.city?`${r.city} · ${sceneNames[tab]}`:sceneNames[tab];
 const values=[['city','目的地',r.city],['origin','出发地',r.origin],['start_date','出游日期',r.start_date],['days','天数',r.days?`${r.days} 天`:null],['adults','同行人数',r.adults?`${r.adults} 成人${r.children?` / ${r.children} 儿童`:''}`:null],['budget','总预算',r.budget?`¥${r.budget}`:null]];
 $('#requirements').innerHTML=values.map(([key,label,v])=>`<button class="info-field ${v?'':'unknown'}" data-edit-field="${key}"><small>${label}</small><strong>${esc(v||'未确定')}</strong></button>`).join('');
 $('#workflow').innerHTML=workflowHTML();$('#selected-content').innerHTML=selectionHTML();$('#selection').hidden=!w.archived;$('#selection').innerHTML=w.archived?'<div class="archive-notice">已归档，仅供查看。<button id="restore-trip" class="ghost">恢复规划</button></div>':'';
 const ui=jobUI||w.ui;
 $('#scene-feedback').hidden=ui?.status!=='loading'||!ui||!!w.archived||!!ui.view&&ui.view!==tab;$('#scene-feedback').innerHTML=guidanceHTML(ui);$('#scene-feedback').classList.toggle('loading',ui?.status==='loading');
 $('#mission').hidden=!w.archived&&(!!ui?.view&&ui.view===tab||tab==='plan'&&w.plan&&!w.plan.stale);
 $('#mission').classList.toggle('compact',!!w.plan&&!w.plan.stale&&!w.archived);
 $('#trip-state').textContent=w.plan?.stale?'计划待更新':w.plan?'计划已生成':w.title||'新旅行';
 const displayMessages=w.messages.filter(m=>!(m.role==='assistant'&&/^已(?:选择|取消选择)：.*当前已选\d+个景点/.test(readable(m.content))));const welcome={role:'assistant',type:'welcome',content:'欢迎使用识途。\n\n**您想去哪里？目的地是否已经确定？**\n也可以先告诉我大致预算、出游时间和旅行偏好，我会帮您比较目的地，再逐步安排景点、住宿、交通与餐饮。'};const messages=displayMessages.some(m=>m.type==='welcome'||m.role==='assistant'&&m.content.startsWith('欢迎使用识途。'))?displayMessages:[welcome,...displayMessages];
 const lastAssistant=messages.findLastIndex(m=>m.role==='assistant');
 const messageSignature=w.id+JSON.stringify(messages)+innerWidth;if(messageSignature!==renderedMessages){$('#messages').innerHTML=messages.map((m,i)=>`<div class="message ${m.role==='user'?'user':''}"><span class="speaker">${m.role==='user'?'用户':'识途'}</span><div class="bubble">${processHTML(m.process_steps)}${messageHTML(m.content,{...m.ui,role:m.role})}${!busy&&!w.archived&&i===lastAssistant?guidanceHTML(m.ui||w.ui,true):''}</div></div>`).join('');$('#messages').scrollTop=$('#messages').scrollHeight;renderedMessages=messageSignature;}
 document.querySelectorAll('.tabs [data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
 $('#content').innerHTML=prerequisitesHTML()+content();const count=w.selected_spots.length;$('#selection-indicator').hidden=!count;$('#selection-indicator').innerHTML=count?`<span>已选 <strong>${count}</strong> 个景点</span><button class="text-button" data-action="complete_spots">${w.spots_confirmed?'重新确认景点':'完成景点选择'}</button>`:'';setBusy(busy);renderLive();
}
function mapHTML(items){
 const ps=items.filter(x=>x.location).map(p=>({...p,xy:p.location.split(',').map(Number)}));if(ps.length<2)return '';
 const xs=ps.map(p=>p.xy[0]),ys=ps.map(p=>p.xy[1]);const xmin=Math.min(...xs),ymin=Math.min(...ys),dx=Math.max(...xs)-xmin||.01,dy=Math.max(...ys)-ymin||.01;
 return `<div class="map"><small>地点分布 · 真实坐标示意，连线不代表道路或导航路线</small><svg viewBox="0 0 650 220" role="img" aria-label="已选地点位置示意"><path d="M0 180 Q150 150 300 195 T650 170" fill="none" stroke="#d2dfd5" stroke-width="30"/>${ps.map((p,i)=>{const x=45+(p.xy[0]-xmin)/dx*520,y=180-(p.xy[1]-ymin)/dy*135;return `<circle cx="${x}" cy="${y}" r="6"/><text x="${Math.min(x+9,530)}" y="${y-9}">${esc(p.name.slice(0,15))}</text>`}).join('')}</svg></div>`;
}
function card(p){
 if(p.kind==='spot')return spotCard(p);
 if(p.kind==='food')return foodCard(p);
 const noTicket=['train','flight'].includes(p.kind)&&String(p.seats)==='0';
 const currentTransport=p.direction==='return'?workspace.selected_return:workspace.selected_transport;
 const sel=p.kind==='spot'?workspace.selected_spots.includes(p.id):p.kind==='hotel'?workspace.hotel?.id===p.id:(p.direction==='return'?workspace.selected_return:workspace.selected_transport)?.id===p.id;
 const h=p.kind==='hotel',t=p.kind==='train'||p.kind==='flight';
 return `<article class="card ${sel?'selected':''}" data-candidate="${esc(p.id)}"><div class="card-top"><div><span class="kind">${h?'住宿候选':t?'交通候选':'景点候选'}</span><h3>${esc(p.name)}</h3></div>${p.rating?`<span class="badge">${esc(p.rating)} 分</span>`:''}</div>
 ${p.price!=null?`<div class="price">¥${esc(p.price)} <small>${h?'起':'参考'}</small></div>`:''}
 ${t?`<p>${esc(p.departure)} → ${esc(p.arrival)}</p><p>${esc(p.departure_station||'')} → ${esc(p.arrival_station||'')}</p><p>${p.kind==='train'?esc(p.seat_type||'席别待核实')+' / ':''}当前可售状态：${esc(p.seat_label)}${p.tax!=null?' · 税费 '+esc(p.tax):''}</p>`:`<p>${esc(p.address||'地址未知')}</p>`}
 ${h?`<p>${esc(p.area||'')} · ${esc(p.room||'房型待核实')}</p><p>${esc(p.window||'')} · ${esc(p.meal||'')} · ${esc(p.refund||'')}</p><p>${esc(p.review_summary||'')}</p><p>${esc(p.match_status||'')}</p>${p.anchor_route?`<p>到${esc(p.anchor_name)}：${mode(p.anchor_route.mode)}约 ${p.anchor_route.minutes} 分钟</p>`:''}`:!t?`<p>地图营业资料：${esc(p.opening||'未提供')}</p><p>票价 / 预约：待核实，不能据此认定免费或无需预约</p>`:''}
 ${p.price_basis?`<p>${esc(p.price_basis)}</p>`:''}${p.recommendation?`<div class="reason">助手建议 · ${esc(p.recommendation)}</div>`:''}
 ${noTicket?'<div class="sold-out">无票 · 请选择其他班次</div>':''}<div class="card-actions"><button data-select="${esc(p.id)}" ${noTicket?'disabled aria-disabled="true"':''}>${noTicket?'无票':sel?(t&&currentTransport?.selection_status==='recommended'?'确认推荐':p.kind==='spot'?'已选择 · 移除':'已选定'):(h?'选择住宿':t?'选择班次':'想去这里')}</button>${h?`<button class="ghost" data-detail="${esc(p.id)}">房型详情</button>`:!t?`<button class="ghost" data-ticket="${esc(p.id)}">查门票</button>`:''}${p.location?link(`https://uri.amap.com/marker?position=${p.location}&name=${encodeURIComponent(p.name)}`,'地图查看 ↗'):''}</div>
 ${p.detail?roomHTML(p.detail,p.id):''}
 ${workspace.tickets[p.id]?ticketsHTML(workspace.tickets[p.id]):''}${src(p.source)}${p.detail_source?src(p.detail_source):''}${p.map_source?src(p.map_source):''}${p.evidence?.length?`<details><summary>推荐依据 · ${p.evidence.length} 条资料</summary>${p.evidence.map(g=>`<p>${esc(g.text)}</p>${link(g.url,g.title)}`).join('')}</details>`:''}</article>`;
}
function spotCard(p){
 const selected=workspace.selected_spots.includes(p.id);
 return `<article class="card spot-card ${selected?'selected':''}" data-candidate="${esc(p.id)}"><div class="card-top"><div><span class="candidate-label">${esc(p.discovery_label||'景点候选')}</span><h3>${esc(p.name)}</h3></div>${selected?'<span class="selected-mark">已选择</span>':''}</div><p class="candidate-location">${esc(p.district||'')} ${esc(p.address||'地址待核实')}</p>${p.recommendation?descriptionHTML(p):''}${p.rating?`<p>地图评分 ${esc(p.rating)} · 评分不代表实时客流</p>`:''}<div class="candidate-facts"><span>开放资料：${esc(p.opening||'待核实')}</span><span>门票与预约：待查询</span></div><div class="card-actions"><button data-select="${esc(p.id)}" class="${selected?'ghost':''}">${selected?'取消选择':'选择景点'}</button><button class="ghost" data-dismiss="${esc(p.id)}" ${selected?'disabled':''}>不感兴趣</button><button class="text-button" data-ticket="${esc(p.id)}">查询门票</button>${p.location?link(`https://uri.amap.com/marker?position=${p.location}&name=${encodeURIComponent(p.name)}`,'地图 ↗'):''}</div>${workspace.tickets[p.id]?ticketsHTML(workspace.tickets[p.id]):''}${src(p.source)}${p.evidence?.length?`<details><summary>推荐依据</summary>${p.evidence.map(g=>`<p>${esc(g.text)}</p>${link(g.url,g.title)}`).join('')}</details>`:''}</article>`;
}
function pager(page,pages,more=false,destination=false){
 const attr=destination?'data-destination-page':'data-spots-page',start=Math.max(1,Math.min(page-1,pages-3));
 return `<nav class="candidate-pager" aria-label="${destination?'目的地':'景点'}分页"><button class="ghost" ${attr}="${page-1}" ${page<=1?'disabled':''}>上一页</button>${Array.from({length:Math.min(4,pages)},(_,i)=>start+i).map(n=>`<button ${attr}="${n}" class="${page===n?'active':'ghost'}" aria-current="${page===n?'page':'false'}">${n}</button>`).join('')}<button class="ghost" ${attr}="${page+1}" ${page>=pages&&!more?'disabled':''}>下一页</button></nav>`;
}
function destinationHTML(){
 const items=workspace.destinations||[],pages=Math.max(1,Math.ceil(items.length/2));destinationPage=Math.min(destinationPage,pages);
 if(!items.length)return `<div class="panel-intro"><h3>确定旅行方向</h3><p>尚未确定目的地时，可先比较城市特色与代表景点。提供出发地或兴趣有助于筛选，也可以直接查看推荐。</p><button data-action="discover_destinations">推荐目的地</button></div><div class="starter-note"><strong>如何开始</strong><p>在对话中描述旅行偏好，例如海滨、人文或自然景观；选择城市后，再确认具体景点。右侧旅行信息可随时补充。</p></div>`;
 return `<div class="candidate-head"><div><h3>目的地推荐</h3><p>${items.length} 个城市 · 第 ${destinationPage} / ${pages} 页</p></div><button class="ghost" data-action="discover_destinations">更新推荐</button></div>${pager(destinationPage,pages,false,true)}<div class="destination-cards">${items.slice((destinationPage-1)*2,destinationPage*2).map(d=>`<article class="card destination-card"><div class="destination-heading"><span class="city-mark">${esc(d.name.slice(0,1))}</span><div><small>${esc(d.discovery_label||'目的地候选')}</small><h3>${esc(d.name)}</h3></div></div><div class="destination-tags">${d.tags.map(t=>`<span>${esc(t)}</span>`).join('')}</div><p>${esc(d.summary)}</p><div class="destination-highlights"><small>代表景点</small><p>${d.highlights.map(esc).join(' · ')}</p></div>${d.recommendation?`<p class="candidate-reason">${esc(readable(d.recommendation))}</p>`:''}<button data-destination="${esc(d.id)}">选择目的地：${esc(d.name)}</button>${src(d.source)}</article>`).join('')}</div><p class="panel-footnote">城市介绍来自背景资料；交通成本、天气、票价和客流需结合实际日期查询。</p>`;
}
function spotsHTML(){
 const w=workspace,all=Object.values(w.catalog||{}).filter(p=>p.kind==='spot'&&!w.rejected_spots?.includes(p.id));
 const info=w.spot_page||{page:1,pages:Math.max(1,Math.ceil(all.length/4)),ids:all.slice(0,4).map(p=>p.id),has_more:false};
 const items=info.ids.map(id=>w.catalog[id]).filter(Boolean);
 const top=`<div class="candidate-head"><div><h3>景点推荐</h3><p>按条件匹配与推荐顺序排列 · 已选 ${w.selected_spots.length} 个</p></div><button data-action="complete_spots" ${w.selected_spots.length?'':'disabled'}>完成景点选择</button></div>`;
 const nav=`<div class="browse-tools">${info.pages>1?pager(info.page,info.pages,false):'<span class="panel-footnote">本轮推荐</span>'}<button class="text-button" data-replace-spots>重新筛选推荐</button></div>`;
 if(!all.length)return top+`<div class="panel-intro"><h3>${esc(w.requirements.city)}景点选择</h3><p>根据旅行偏好查询景点，选择完成后再比较住宿。可以在对话中指定兴趣或景点名称。</p><button data-action="search_spots">查询景点推荐</button><button class="ghost" data-action="discover_destinations">比较其他目的地</button></div>`;
 return top+nav+`<div class="cards">${groupedSpotsHTML(items)}</div><div class="panel-footer-actions"><button class="ghost" data-action="discover_destinations">比较其他目的地</button><button class="ghost" data-action="search_spots">按当前偏好重新查询</button></div>`;
}
function roomHTML(d,id){
 const h=workspace.catalog[id],choices=h.room_choices||[],policy=d.policies||{};
 return `<details class="room-details" ${detailOpenId===id||workspace.hotel?.id===id?'open':''}><summary>房型与报价（可选） · ${(d.roomTypes||[]).length}种</summary><p>入住 ${esc(policy.checkInTime||d.checkInTime||'待核实')} / 退房 ${esc(policy.checkOutTime||d.checkOutTime||'待核实')}</p>${policy.cancelPolicy?`<p>酒店退改概览：${esc(policy.cancelPolicy)}</p>`:''}${(d.roomTypes||[]).map((r,i)=>`<div class="room" data-room-group="${esc(id)}:${i}"><strong>${esc(r.roomTypeName)}</strong><p>${[r.bedType,r.maxOccupancy?`最多${r.maxOccupancy}人`:'人数待核实',r.roomSize?String(r.roomSize)+(String(r.roomSize).match(/^\d+(\.\d+)?$/)?'㎡':''):'',r.floor?'楼层 '+r.floor:''].filter(Boolean).map(esc).join(' · ')}</p>${r.images?.length?photoHTML({name:r.roomTypeName,photos:r.images,source:h.detail_source}):''}${(r.ratePlans||[]).map((v,j)=>{const c=choices.find(c=>c.room_index===i&&c.rate_index===j),soldOut=String(v.count)==='0';return `<div class="rate"><strong>¥${esc(v.rmbPrices??'待核实')}</strong><small>参考报价</small>${v.ratePlanName?`<p>${esc(v.ratePlanName)}</p>`:''}<p>${esc(v.mealText||'餐食待核实')} · ${esc(v.cancelText||v.cancelDesc||'退改待核实')}</p>${soldOut?'<p class="sold-out">无房 · 请更换报价或更新详情</p>':v.count!=null?`<small>可售数量 ${esc(v.count)}（查询时）</small>`:'<small>可售状态待确认</small>'}${c?`<button data-room="${esc(c.id)}" ${soldOut?'disabled':''} class="${workspace.selected_room?.id===c.id?'ghost':''}">${soldOut?'无房':workspace.selected_room?.id===c.id?'已选此房型':'选择此房型'}</button>`:'<p>请更新房型详情后选择</p>'}</div>`}).join('')}</div>`).join('')}<p class="panel-footnote">报价、入住资格及整段住宿总价需预订前确认。</p></details>`;
}
function transportDate(direction){const r=jobUI?.requirements||workspace.requirements;return direction==='outbound'?(r.outbound_date||r.start_date):(r.return_date||(r.start_date?addDate(r.start_date,Number(r.days||2)):null))}
function prerequisitesHTML(){const w=workspace,r=w.requirements;let need=[];if(tab==='hotel')need=[['start_date','出游日期'],['days','游玩天数'],['adults','成人数']];if(tab==='transport')need=[['origin','出发城市'],['city','目的地'],['start_date','出游日期'],['days','游玩天数']];if(tab==='food')need=[['start_date','出游日期'],['days','游玩天数']];const missing=need.filter(([k])=>!r[k]).map(([,n])=>n);if(missing.length)return `<div class="missing-banner" role="status"><div><strong>请补充：${missing.map(esc).join('、')}</strong><p>可在对话中发送，系统自动填写；也可手动编辑旅行信息。</p></div><button class="ghost" data-open-settings>填写信息</button></div>`;const next=w.next_step;if(next?.action&&['transport','hotel','food','plan'].includes(tab))return `<div class="next-banner"><strong>下一步：${esc(next.message)}</strong><button data-action="${esc(next.action)}">${esc(next.label)}</button></div>`;return ''}
function foodCard(p){const key=(mealDate||workspace.requirements.start_date)+'|'+mealPeriod,selected=workspace.meal_choices?.[key]?.food_id===p.id&&workspace.meal_choices[key].mode==='chosen';return `<article class="card ${selected?'selected':''}" data-candidate="${esc(p.id)}"><span class="candidate-label">餐饮候选</span><h3>${esc(p.name)}</h3><p>${esc(p.address||'地址待核实')}</p>${p.search_anchor?`<p>查询参照：${esc(p.search_anchor)}</p>`:''}${p.recommendation?`<p>${esc(p.recommendation)}</p>`:''}<p>人均：${p.cost?esc(p.cost)+'元（地图参考）':'未提供'} · 营业资料：${esc(p.opening||'待核实')}</p><div class="card-actions"><button data-food="${esc(p.id)}" ${!workspace.requirements.start_date?'disabled':''}>${selected?'本餐已选':'选为本餐地点'}</button>${p.location?link(`https://uri.amap.com/marker?position=${p.location}&name=${encodeURIComponent(p.name)}`,'地图 ↗'):''}</div>${src(p.source)}</article>`}
function foodHTML(){const w=workspace,r=w.requirements,dates=r.start_date?Array.from({length:Number(r.days||2)},(_,i)=>addDate(r.start_date,i)):[];if(!dates.includes(mealDate))mealDate=dates[0]||'';const q=w.food_query?.meal_date&&(w.food_query.meal_date!==mealDate||w.food_query.meal_period!==mealPeriod)?null:w.food_query,items=(q?.ids||[]).map(i=>w.catalog[i]).filter(Boolean),key=mealDate+'|'+mealPeriod,ch=w.meal_choices?.[key];return `<div class="candidate-head"><div><h3>餐饮安排（可选）</h3><p>按日期和餐次选择，也可以出行时自行决定。</p></div><button class="ghost" data-search-foods>查询餐厅</button></div><div class="meal-picker"><label>日期<select id="meal-date">${dates.map(d=>`<option ${mealDate===d?'selected':''}>${esc(d)}</option>`).join('')}</select></label><label>参照地点<select id="food-anchor"><option value="">按当日行程自动选择</option>${[...w.selected_spots.map(id=>w.catalog[id]),w.hotel].filter(p=>p?.location).map(p=>`<option value="${esc(p.id)}" ${foodAnchor===p.id?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label><label>餐次<select id="meal-period">${[['breakfast','早餐'],['lunch','午餐'],['dinner','晚餐']].map(([v,n])=>`<option value="${v}" ${mealPeriod===v?'selected':''}>${n}</option>`).join('')}</select></label><button class="ghost" data-self-meal ${!dates.length?'disabled':''}>本餐自行安排</button></div><p class="meal-status">${ch?.mode==='chosen'?'本餐已选：'+esc(w.catalog[ch.food_id]?.name)+' <button class="text-button" data-meal-remove>取消这一餐</button>':'本餐尚未选定，可选下方餐厅或自行安排。'}</p>${q?`<p>${esc(q.meal_date||'未指定餐日')} ${esc(({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[q.meal_period]||'')} · ${esc(q.anchor)} · ${esc(q.scope||'城市范围')} · ${items.length}家候选</p>`:''}<div class="cards">${items.map(foodCard).join('')}</div>${q?.markets?.length?'<h3>海鲜采购场所（非用餐预订）</h3>'+q.markets.map(id=>{const p=w.catalog[id];return p?`<article class="card"><h3>${esc(p.name)}</h3><p>${esc(p.address)}</p>${src(p.source)}</article>`:''}).join(''):''}${!items.length?'<p>尚无餐厅候选：系统已先按当日景点周边、再按城市范围查询过。可以换一个日期或餐次、在参照地点里指定别的景点、或直接告诉我具体菜系（例如“水席”“面食”）或店名，我再查一次；也可以点“本餐自行安排”。</p>':''}<div class="panel-footer-actions"><button class="ghost" data-self-all-meals>全部用餐自行安排</button><button data-action="complete_food">完成餐饮安排，继续</button></div>`}
function transportHTML(){const w=workspace;if(w.local_trip)return '<div class="panel-intro"><h3>本地出游</h3><p>出发地与游玩地在同一区域，无需选择外地往返班次。市内步行、公交或打车方案会在计划书中比较。</p><button data-tab="food">下一步：餐饮安排</button></div>';const key=transportMode+':'+transportDirection,q=w.transport_queries?.[key]||(w.transport?.kind===transportMode&&w.transport?.direction===transportDirection?w.transport:null),items=q?.items||[];return `<div class="transport-picker"><div class="segmented"><button data-transport-mode="train" class="${transportMode==='train'?'active':'ghost'}">火车／高铁</button><button data-transport-mode="flight" class="${transportMode==='flight'?'active':'ghost'}">飞机</button></div><div class="segmented"><button data-transport-direction="outbound" class="${transportDirection==='outbound'?'active':'ghost'}">去程</button><button data-transport-direction="return" class="${transportDirection==='return'?'active':'ghost'}">返程</button></div><div class="transport-filter-row"><div class="transport-date"><label>${transportDirection==='return'?'返程':'去程'}日期<input id="transport-date" type="date" value="${esc(transportDates[transportDirection]||transportDate(transportDirection)||'')}"></label></div><div class="transport-time"><label>出发时段<input id="time-start" type="time" value="${esc(timeStart)}"></label><span>至</span><input id="time-end" type="time" value="${esc(timeEnd)}" aria-label="出发时段结束"></div></div>${transportMode==='train'?`<label class="train-type-label">车型选择<select id="train-type" aria-label="车次类型"><option value="all" ${trainType==='all'?'selected':''}>全部列车</option><option value="highspeed" ${trainType==='highspeed'?'selected':''}>高铁</option><option value="regular" ${trainType==='regular'?'selected':''}>动车／火车</option></select></label>`:''}<div class="toolbar"><p>${transportDirection==='return'?'返程':'去程'} · ${esc(transportDirection==='return'?w.requirements.city:w.requirements.origin||'出发地待定')} → ${esc(transportDirection==='return'?w.requirements.origin||'出发地待定':w.requirements.city||'目的地待定')}</p><button data-query-transport>查询班次</button></div></div><div class="transport-summary">${['selected_transport','selected_return'].map((k,i)=>`<div><small>${i?'返程':'去程'}</small>${w[k]?`<strong>${esc(w[k].name)}</strong><span>${esc(w[k].departure)} · ${w[k].selection_status==='recommended'?'推荐待确认':'已选定'}</span>${candidateConflicts(w[k].id).map(conflictHTML).join('')}${w[k].selection_status==='recommended'?`<button data-select="${esc(w[k].id)}">确认推荐</button>`:''}`:'<span>待选择</span>'}</div>`).join('')}</div>${q?`<div class="cards transport-results">${items.map(card).join('')}</div>${!items.length?'<p>本次查询没有符合条件的结果，可调整时段或交通类型。</p>':''}<p class="panel-footnote">当前展示接口返回的一批结果。车次类型按返回车次筛选；余票为查询时快照。</p>`:'<p>选择类型与方向后查询班次，已选另一方向会保留。</p>'}${w.selected_transport&&w.selected_return?`<div class="panel-footer-actions"><button data-tab="food">下一步：餐饮安排</button>${w.dining_reviewed||w.meal_mode==='self'?'<button class="ghost" data-action="plan">生成旅行计划书</button>':''}</div>`:''}`;}
function ticketsHTML(t){
 const rows=t.items||[],groups=[['admission','含门票产品'],['other','其他产品 · 入园范围需核对'],['addon','附加体验、餐食与商品']];
 function row(x){
  const hasDays=x.advanceBookDay!=null&&x.advanceBookDay!=='',hasHours=x.advanceBookHour!=null&&x.advanceBookHour!=='';
  const advance=[hasDays?esc(x.advanceBookDay)+'天':'',hasHours?esc(x.advanceBookHour)+'小时':''].filter(Boolean).join(' / ');
  const zeroAdvance=advance&&(Number(x.advanceBookDay||0)===0&&Number(x.advanceBookHour||0)===0);
  return `<article class="ticket-product"><small class="ticket-origin">${esc(t.source?.name||'来源未记录')}返回的产品资料</small><strong>${esc(x.resName||'未命名产品')}</strong>${x.scenicName?`<p>产品所属景区：${esc(x.scenicName)}${t.candidate_name&&t.candidate_name!==x.scenicName?'；请核对是否覆盖所选景点“'+esc(t.candidate_name)+'”':''}</p>`:''}<p><b>${x.startPrice!=null?'¥'+esc(x.startPrice)+' 起':'价格未提供'}</b><span class="ticket-price-scope">供应商区间起价</span> · ${esc(x.personTypeName||'适用人群待核实')} · ${esc(x.ticketTypeName||'')}</p><p>最低价日期：${esc(x.departsDate||'未提供')}；${t.requested_date===String(x.departsDate||'').slice(0,10)?'仍需确认当天报价':'不作为所选游玩日期的报价'}</p><p>销售区间：${esc(x.startDate||'未提供')}—${esc(x.endDate||'未提供')}${x.date_status==='outside_sales_window'?'<strong class="sold-out"> · 所选日期不在销售区间内</strong>':''}</p>${x.lossName?`<p>退改：${esc(x.lossName)}（具体规则待确认）</p>`:''}${x.admissionVoucherDesc?`<p>来源提供的入园凭证：${esc(x.admissionVoucherDesc)}</p>`:''}${x.enterTypeName?`<p>来源提供的入园方式：${esc(x.enterTypeName)}</p>`:''}${advance?`<p>供应商提前量字段：${advance}；${zeroAdvance?'是否支持当天预订及截止时间仍需确认':'具体截止时间需核对'}</p>`:''}${x.commonAgeLimit?`<p>年龄资料：${esc(x.commonAgeLimit.minAge??'未提供')}—${esc(x.commonAgeLimit.maxAge??'未提供')}岁，边界与证件要求需确认</p>`:''}<small>预约名额：未提供${x.productId?' · 产品 '+esc(x.productId):''}${x.resId?' / 资源 '+esc(x.resId):''}</small></article>`;
 }
 return `<details open class="ticket-results"><summary>门票产品 · 游玩日期 ${esc(t.requested_date||'未确定')}</summary>${t.status==='query_failed'?`<p class="sold-out">${esc(t.attempted_date||'本次日期')}查询失败，下列内容为之前的查询快照。</p>`:''}${rows.length?`<p class="ticket-price-status"><strong>${esc(t.requested_date||'当前')}所选日期报价尚未确认</strong> · 预约库存未提供。以下为${esc(t.source?.name||'查询来源')}返回的产品与区间起价，销售区间不代表当天可预订。</p>`:''}${t.query_name&&t.query_name!==t.candidate_name?`<p>使用名称“${esc(t.query_name)}”查询；请核对产品是否覆盖所选景点。</p>`:''}<p class="data-scope">${esc(t.note||'供应商返回区间起价，具体日期报价与预约名额待确认。')}</p>${rows.length?groups.map(([key,title])=>{const items=rows.filter(x=>(x.product_group||'other')===key);return items.length?key==='addon'?`<details><summary>${title} · ${items.length}项</summary>${items.map(row).join('')}</details>`:`<h4>${title} · ${items.length}项</h4>${items.map(row).join('')}`:''}).join(''):'未查到产品，不能据此断定免费、无票或关闭。'}${src(t.source)}</details>`;
}
function content(){
 const w=workspace;
 if(tab==='food')return foodHTML();
 if(tab==='spot'){
  return !w.requirements.city||w.discovery_mode?destinationHTML():spotsHTML();
 }
 if(tab==='hotel'){
  const chosen=w.hotel?`<div class="current-stay"><small>已选住宿</small><strong>${esc(w.hotel.name)}</strong><span>${w.selected_room?esc(w.selected_room.name)+' · '+w.selected_room.quantity+'间':'房型可选 · 未选择'}</span></div>`:'';
  const items=w.hotel_query?w.hotel_query.ids.map(id=>w.catalog[id]).filter(p=>p&&!p.stale):Object.values(w.catalog||{}).filter(p=>p.kind==='hotel'&&!p.stale);
  const missing=[['start_date','出游日期'],['days','旅行天数'],['adults','成人数']].filter(([k])=>!w.requirements[k]);
  return chosen+`<div class="candidate-head"><div><h3>住宿推荐</h3><p>选定酒店即可继续 · 具体房型可选</p></div><button data-action="complete_hotel" ${w.hotel&&!w.hotel.stale?'':'disabled'}>完成住宿选择</button></div>`+(missing.length?`<div class="inline-requirements"><strong>查询住宿需要补充信息</strong><p>${missing.map(x=>x[1]).join('、')}尚未确定。可以直接在对话中提供，或编辑右侧旅行信息。</p><button data-open-settings>补充旅行信息</button></div>`:'')+stayPlanHTML()+centerStayHTML()+`<div class="toolbar"><p>${items.length} 家候选${w.hotel_query?.keyword?' · '+esc(w.hotel_query.keyword):''} · 结合游览区域比较</p><button class="ghost" data-action="search_hotels">查询住宿</button></div>`+((items.length||(w.hotel_query?.center_matches||[]).length)&&!w.stay_plan?`<div class="cards">${(w.hotel_query?.center_matches||[]).map(id=>w.catalog[id]).filter(p=>p&&!p.stale).map(card).join('')+items.sort((a,b)=>(a.recommendation_rank??99)-(b.recommendation_rank??99)).map(card).join('')}</div>`:items.length?'':empty('02','住宿安排',Number(w.requirements.days)===1?'本次为一日游，可以跳过住宿。':'确认景点与日期后查询住宿。已有住宿或暂未决定时，可以先继续规划。'))+`<div class="panel-footer-actions"><button class="ghost" data-action="skip_hotel">暂不安排住宿，继续</button></div>`;
 }
 if(tab==='weather')return weatherHTML();
 if(tab==='transport')return transportHTML();
 if(tab==='plan')return bookHTML();
 const guides=w.rag_results||w.plan?.guides||[];
 return `<div class="toolbar"><p>官方页面片段，按城市检索并保留采集时间。检索命中不代表规则适用于未来出游日。</p></div>`+(guides.length?guides.map(g=>`<article class="knowledge"><h4>${esc(g.title)}</h4><p>${esc(g.text)}</p>${link(g.url,'查看原文 ↗')}<div class="source">采集 ${esc(g.fetched_at)} · ${esc(g.retrieval||'官方页面快照')} · ${g.score??''}</div></article>`).join(''):empty('RAG','介绍也需要有依据','查询景点时，助手会检索相关官方资料。没有匹配片段时明确保留未知。'))+`<details><summary>最近的执行记录</summary>${w.trace.map(x=>`<p>${esc(x.time)} · ${esc(x.text)}</p>`).join('')}</details>`;
}
function weatherHTML(){
 const w=workspace.weather,r=workspace.requirements;
 let top='<div class="toolbar"><p>和风真实预报，仅覆盖返回的日期。</p><button data-action="weather">更新天气</button></div>';
 if(!w)return top+empty('☀','天气信息','选一个景点后，用它的坐标查询天气。超出预报窗口的日期不提供伪造预报。');
 const relevant=w.days.filter(d=>!r.start_date||d.date>=r.start_date&&d.date<addDate(r.start_date,Number(r.days||2)));
 return top+(!relevant.length?'<div class="notice">旅行日期超出当前预报范围，天气待确认。下面展示当前可查询窗口。</div>':'')+`<div class="weather-days">${(relevant.length?relevant:w.days).map(d=>`<div class="weather-day"><small>${esc(d.date)}</small><h4>${esc(d.text)}</h4><div class="temp">${Math.round(d.low)}° — ${Math.round(d.high)}°</div><p>降水概率 ${d.rain!=null?Math.round(d.rain*100)+'%':'未知'}</p><p>风力 ${esc(d.wind??'未知')} 级</p></div>`).join('')}</div><p>${esc(w.alert_status)} · 当前预警，不等于出游日预警</p>${w.alerts.length?`<pre>${esc(JSON.stringify(w.alerts,null,2))}</pre>`:''}${src(w.source)}${w.attributions.map(u=>link(u,'天气数据署名')).join(' · ')}`;
}
function addDate(s,n){let d=new Date(s+'T12:00:00');d.setDate(d.getDate()+n);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function bookHTML(){
 const w=workspace,p=w.plan;
 const toolbar=`<div class="toolbar"><p>一份可以继续完善、打印和带走的旅行计划。</p><div><button data-action="plan">${p?'重新生成':'生成计划书'}</button>${p||w.last_plan_conflict?'<button class="ghost" data-action="optimize_plan">智能修订</button>':''}<button class="ghost" data-action="undo">撤销上一步</button>${p&&!p.stale?`<button class="ghost" id="print">打印 / PDF</button><a href="/api/workspaces/${w.id}/export">导出 Markdown ↗</a>`:''}</div></div>`;
 if(!p)return toolbar+empty('04','生成旅行计划书','包含每日安排、交通方式、住宿、预算、天气、准备事项、来源与审核意见。先选景点；住宿未定也可生成带未知项的草稿。');
 if(p.stale)return toolbar+`<div class="empty"><span class="number">↻</span><h3>选择已更新，计划需要重排</h3><p>上一版「${esc(p.title)}」已保留。当前景点、住宿或条件与上一版不同，请重新生成后查看和导出完整计划。</p><button data-action="plan">按当前选择重新整理 →</button></div>`;
 return toolbar+`<article class="book">${p.stale?'<div class="notice">选择或条件已经变化。这是上一版计划，请重新生成后再使用或导出。</div>':''}<div class="book-cover"><span class="eyebrow">YOUR TRAVEL BOOK / 旅行计划书</span><h2>${esc(w.requirements.city)}旅行计划书</h2><span class="badge">待完善草稿 · ${esc(p.created.replace('T',' '))}</span></div>
 <div class="book-stats"><div><strong>${p.days.length}</strong><span>天的旅行</span></div><div><strong>${w.selected_spots.length}</strong><span>个已选景点</span></div><div><strong>${p.days.reduce((n,d)=>n+d.events.filter(e=>e.route).length,0)}</strong><span>段已有路线数据</span></div><div><strong>待确认</strong><span>门票、接驳与完整预算</span></div></div>
 <nav class="book-nav" aria-label="计划书目录"><a href="#book-overview">旅行概览</a>${p.days.map((d,i)=>`<a href="#day-${i}">第${i+1}天</a>`).join('')}<a href="#book-budget">费用</a><a href="#book-todos">出发待办</a><a href="#book-review">审核意见</a></nav>
 <details class="book-overview"><summary>住宿与往返交通</summary><h3 id="book-overview">旅行信息</h3><p>${esc(w.requirements.city)} · ${esc(w.requirements.start_date)}起 · ${w.requirements.days||2}天 · ${w.requirements.adults||'未明确'}位成人</p><p>${w.hotel?`住宿：${esc(w.hotel.name)}（仅选定，尚未预订）<br>地址：${esc(w.hotel.address)}${w.selected_room?`<br>房型：${esc(w.selected_room.name)} · ${w.selected_room.quantity}间 · 报价¥${esc(w.selected_room.price??'待核实')}<br>${esc(w.selected_room.meal||'餐食待核实')} · ${esc(w.selected_room.cancel||'退改待核实')}`:''}${src(w.hotel.source)}`:'住宿未定，当前日程不含住宿往返。'}</p>${mapHTML(w.selected_spots.map(i=>w.catalog[i]))}
 <h3>往返交通</h3>${["selected_transport","selected_return"].map((key,i)=>workspace[key]?`<p>${i?"返程":"去程"}：${esc(workspace[key].name)} · ${esc(workspace[key].departure)} → ${esc(workspace[key].arrival)}（${workspace[key].selection_status==='recommended'?'推荐待确认':'选定'}，未预订）</p>`:`<p>${i?"返程":"去程"}尚未选定，接驳和可用时间待核实。</p>`).join("")}</details><h3>每日安排</h3><p>以下时间为建议日程。班次、预约等固定条件未确认前，起止时间保留调整空间。</p>${p.days.map((d,i)=>`<section class="day" id="day-${i}"><h4>${esc(d.date)} · ${esc(d.theme)}</h4>${d.note?`<p>${esc(d.note)}</p>`:''}${d.events.map(e=>`<div class="event ${e.kind==='route'?'route':''}"><div class="time">${esc(e.start)}<br>— ${esc(e.end)}</div><div class="event-body"><strong>${esc(e.name)}</strong><p>${esc(e.note)}</p>${e.route?`<p>${mode(e.route.mode)} · 高德预计 ${e.route.minutes} 分钟 / ${(e.route.distance/1000).toFixed(1)}公里 · 另留${e.buffer}分钟缓冲</p>${src(e.route.source)}${routeStepsHTML(e.route)}<details><summary>比较其他方式</summary>${e.options.map(o=>`<p>${mode(o.mode)}：${o.available?o.minutes+' 分钟，'+(o.distance/1000).toFixed(1)+'公里':esc(o.reason||'无数据')}</p>`).join('')}</details>`:''}${e.source?src(e.source):''}${e.poi?`<p>游玩 ${e.duration} 分钟是建议值；门票、预约及当天开放待核实。</p>${src(e.poi.source)}`:''}</div></div>`).join('')||'<p>弹性休息与待补充安排。</p>'}</section>`).join('')}
 <h3 id="book-budget">03 · 预算与费用口径</h3><table><tr><th>费用项</th><th>当前可确认程度</th></tr><tr><td>住宿起价参考</td><td>${p.budget.hotel_reference!=null?'¥'+p.budget.hotel_reference.toFixed(0):'未确定'}</td></tr>${p.budget.unknown.map(x=>`<tr><td>${esc(x)}</td><td>待核实，尚未计入完整预算</td></tr>`).join('')}</table><p>${esc(p.budget.basis||'总费用尚无法准确计算。')}</p>
 <h3>04 · 天气与应对</h3>${w.weather?weatherHTML().replace(/<div class="toolbar">[\s\S]*?<\/div>/,''):'<p>天气尚未查询。超出预报范围的日期需要临近出发时再确认。</p>'}
 <h3 id="book-todos">05 · 出发前要处理的事</h3><ul>${p.todos.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><h3>06 · 携带与节奏建议</h3><ul>${p.packing.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>
 <h3>07 · 风险与待确认条件</h3><ul>${p.warnings.map(x=>`<li>${esc(readable(x).replace(/breakfast/g,'早餐').replace(/lunch/g,'午餐').replace(/dinner/g,'晚餐'))}</li>`).join('')}</ul>
 <h3 id="book-review">08 · 独立审核意见</h3><p>${esc(p.review?.summary||'尚未完成')}</p><ul>${(p.review?.issues||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>审核意见为模型辅助检查，不能替代真实数据和程序检查。</p>
 <h3>09 · 资料来源</h3>${p.guides.map(g=>`<p>${link(g.url,g.title)} · 采集 ${esc(g.fetched_at)}；适用日期需核实</p>`).join('')||'<p>本次未检索到相关官方片段。</p>'}</article>`;
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.transportMode){transportMode=b.dataset.transportMode;render();return}
 if(b.dataset.transportDirection){transportDirection=b.dataset.transportDirection;render();return}
 if(b.dataset.returnMode){$('#return-dialog').close();transportMode=b.dataset.returnMode;transportDirection='return';switchTab('transport');if(!workspace.transport_queries?.[transportMode+':return'])await action(transportMode,{direction:'return'});return}
 if(b.hasAttribute('data-query-transport')){await action(transportMode,{direction:transportDirection});return}
 if(b.dataset.room){await action('select_room',{id:b.dataset.room});return}
 if(b.dataset.editField){$('#conditions').click();$('#settings-form').elements[b.dataset.editField]?.focus();return}
 if(b.dataset.destination){await action('choose_destination',{id:b.dataset.destination});return}
 if(b.dataset.destinationPage){destinationPage=Number(b.dataset.destinationPage);render();$('#content').scrollTo({top:0,behavior:'smooth'});return}
 if(b.dataset.spotsPage){await action('spots_page',{page:Number(b.dataset.spotsPage)});return}
 if(b.hasAttribute('data-replace-spots')){await action('search_spots',{reject_current:true});return}
 if(b.dataset.dismiss){await action('dismiss_spot',{id:b.dataset.dismiss});return}
 if(b.hasAttribute('data-open-settings')){$('#conditions').click();return}
 if(b.dataset.tab){switchTab(b.dataset.tab);return}
 if(b.dataset.action){const row=b.closest('.stay-row');const stayArgs=row?.dataset.stayDate?{stay_date:row.dataset.stayDate}:{};if(stayArgs.stay_date&&b.dataset.action==='search_hotels')stayOpenDate=stayArgs.stay_date;await action(b.dataset.action,b.dataset.direction?{direction:b.dataset.direction}:stayArgs);return}
 if(b.hasAttribute('data-search-foods')){await action('search_foods',{meal_date:mealDate||workspace.requirements.start_date,meal_period:mealPeriod,anchor_id:document.querySelector('#food-anchor')?.value||undefined});return}
 if(b.dataset.food){await action('meal_choice',{food_id:b.dataset.food,meal_date:mealDate||workspace.requirements.start_date,meal_period:mealPeriod,meal_mode:'chosen'});return}
 if(b.hasAttribute('data-meal-remove')){await action('meal_choice',{meal_date:mealDate||workspace.requirements.start_date,meal_period:mealPeriod,mode:'remove'});return}
 if(b.hasAttribute('data-self-meal')){await action('meal_choice',{meal_date:mealDate||workspace.requirements.start_date,meal_period:mealPeriod,meal_mode:'self'});return}
 if(b.hasAttribute('data-self-all-meals')){await action('meal_choice',{meal_mode:'self'});return}
 if(b.dataset.select){const picked=workspace.catalog[b.dataset.select],old=picked&&['train','flight'].includes(picked.kind)?workspace[picked.direction==='return'?'selected_return':'selected_transport']:null;if(old&&old.id!==picked.id){replaceTarget=picked.id;$('#replace-text').textContent=`该方向已选 ${old.name}，是否替换为 ${picked.name}？将只保留一个班次。`;$('#replace-dialog').showModal();return}
  // 住宿候选若位于某个"住宿晚"行内，点选只改那一晚；否则作为主住宿覆盖未指定的夜晚。
  const stayRow=b.closest&&b.closest('.stay-row');
  const stayArg=(picked&&picked.kind==='hotel'&&stayRow&&stayRow.dataset.stayDate)?{stay_date:stayRow.dataset.stayDate}:{};
  await action('select',{id:b.dataset.select,...stayArg});return}
 if(b.dataset.detail){await action('hotel_detail',{id:b.dataset.detail});return}
 if(b.dataset.ticket){const input=$('#candidate-dialog [data-ticket-date]');await action('ticket',{id:b.dataset.ticket,visit_date:input?.value||undefined});return}
 if(b.dataset.placeDetail){await action('place_detail',{id:b.dataset.placeDetail,view:tab});return}
 if(b.id==='print'){tab='plan';render();window.print()}
});
$('#chat-form').addEventListener('submit',async e=>{e.preventDefault();const t=$('#message').value.trim();if(!t||busy)return;$('#message').value='';sessionStorage.removeItem(draftKey(workspace.id));await action('chat',{},t)});
$('#message').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#chat-form').requestSubmit()}});
$('#conditions').onclick=()=>{
 $('#settings-form').reset();
 for(const [k,v]of Object.entries(workspace.requirements)){const el=$('#settings-form').elements[k];if(el)el.value=Array.isArray(v)?v.join(','):v??''}
 $('#settings').showModal();
};$('#close-settings').onclick=()=>$('#settings').close();
$('#settings-form').onsubmit=async e=>{e.preventDefault();const patch={};for(const [k,v]of new FormData(e.target))if(v.trim()){patch[k]=['days','adults','children','rooms','budget'].includes(k)?Number(v):k==='child_ages'?v.split(/[,，]/).map(x=>Number(x.trim())):v}$('#settings').close();await action('requirements',{patch})};
$('#new').onclick=newTrip;
$('#expand-workbench').onclick=()=>setWorkbenchExpanded(!workbenchExpanded);$('#workbench-shade').onclick=()=>setWorkbenchExpanded(false);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&workbenchExpanded)setWorkbenchExpanded(false)});
$('#selected-button').onclick=()=>{$('#selected-content').innerHTML=selectionHTML();$('#selected-dialog').showModal()};
$('#confirm-replace').onclick=async()=>{const id=replaceTarget;replaceTarget=null;$('#replace-dialog').close();await action('select',{id,replace:true})};
document.addEventListener('change',e=>{if(e.target.id==='transport-date')transportDates[transportDirection]=e.target.value;if(e.target.id==='food-anchor')foodAnchor=e.target.value;if(e.target.id==='meal-date'){mealDate=e.target.value;render()}if(e.target.id==='meal-period'){mealPeriod=e.target.value;render()}if(e.target.id==='time-start')timeStart=e.target.value;if(e.target.id==='time-end')timeEnd=e.target.value;if(e.target.id==='train-type'){trainType=e.target.value;if(!busy)action(transportMode,{direction:transportDirection})}});
for(const id of ['selected-dialog','replace-dialog','return-dialog','settings'])$('#'+id).addEventListener('click',e=>{const d=e.currentTarget,r=d.getBoundingClientRect();if(e.target===d&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))d.close()});
bootAccount();


let printSources=[];
window.addEventListener('beforeprint',()=>{printSources=[...document.querySelectorAll('.book details.source')].filter(d=>!d.open);printSources.forEach(d=>d.open=true)});
window.addEventListener('afterprint',()=>{printSources.forEach(d=>d.open=false);printSources=[]});

function routeStepsHTML(r){return r.steps?.length?`<details><summary>查看通行步骤${r.fare!=null?' · 公交参考¥'+esc(r.fare):''}</summary>${r.steps.map(s=>`<p>${esc(s.instruction||s.road_name||'通行路段')}${s.from?' · '+esc(s.from)+' → '+esc(s.to||''):''}</p>`).join('')}<small>查询时的路线建议，出行时请使用实时导航。</small></details>`:''}
