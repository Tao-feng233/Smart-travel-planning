/* Confirmed delegation and actionable planning diagnostics. */
let autoConsentKey='',autoContinueTimer=null,autoStopping=false,autoTripId='';
let planWarningKey='',planWarningTrip='';
function syncPlanWarning(){
 let dialog=$('#plan-warning-dialog');
 if(!dialog){
  dialog=document.createElement('dialog');dialog.id='plan-warning-dialog';
  dialog.innerHTML='<form><div class="dialog-head"><h2>安排有提醒，是否继续生成？</h2><button type="button" class="ghost" data-plan-warning-cancel>返回调整</button></div><p>以下为建议时长或每日负担的提醒，不要求填满每一天。继续后会保留警告；明确的日期、班次冲突仍需解决。</p><div class="plan-warning-issues"></div><div class="auto-selection-actions"><button type="button" class="ghost" data-plan-warning-cancel>先调整安排</button><button type="submit">继续生成带警告的草稿</button></div></form>';
  document.body.append(dialog);
  const cancel=()=>{if(busy)return;const id=workspace?.pending_plan_warning?.id;planWarningKey=workspace?.id+':'+id;dialog.close();action('cancel_plan_warning').then(()=>{if(workspace?.pending_plan_warning?.id===id){planWarningKey='';syncPlanWarning()}})};
  dialog.querySelectorAll('[data-plan-warning-cancel]').forEach(b=>b.onclick=cancel);
  dialog.addEventListener('cancel',e=>{e.preventDefault();cancel()});
  dialog.querySelector('form').onsubmit=e=>{e.preventDefault();if(busy)return;const id=workspace?.pending_plan_warning?.id;if(!id)return;planWarningKey=workspace.id+':'+id;dialog.close();action('approve_plan_warning',{approval_id:id,confirmed:true}).then(()=>{if(workspace?.pending_plan_warning?.id===id){planWarningKey='';syncPlanWarning()}})};
 }
 if(planWarningTrip!==workspace?.id){planWarningTrip=workspace?.id;planWarningKey=''}
 const pending=workspace?.pending_plan_warning;
 if(!pending||workspace?.archived||$('#application').hidden){if(dialog.open)dialog.close();return}
 if(busy||planWarningKey===workspace.id+':'+pending.id||$('#auto-selection-dialog')?.open)return;
 dialog.querySelector('.plan-warning-issues').innerHTML=pending.issues.map(i=>`<p>${esc(i.message)}</p>`).join('');
 if(!dialog.open)dialog.showModal();
}
function ensureAutoConsent(){
 if($('#auto-selection-dialog'))return;
 const dialog=document.createElement('dialog');dialog.id='auto-selection-dialog';dialog.innerHTML='<form><div class="dialog-head"><h2>允许助手自动配置吗？</h2><button type="button" class="ghost" data-auto-cancel>暂不代选</button></div><p class="auto-selection-scope"></p><p class="auto-selection-notice"></p><label class="auto-plan-option"><input type="checkbox" id="auto-generate-plan"><span>完成代选后生成计划书（往返交通需先由你确认）</span></label><div class="auto-selection-actions"><button type="button" class="ghost" data-auto-cancel>保留当前选择</button><button type="submit" id="auto-selection-confirm">确认并开始</button></div></form>';document.body.append(dialog);
 const stop=()=>{const id=workspace?.pending_auto_selection?.id;autoConsentKey=workspace?.id+':'+id;dialog.close();if(!busy)action('cancel_auto_selection')};
 dialog.querySelectorAll('[data-auto-cancel]').forEach(b=>b.onclick=stop);
 dialog.addEventListener('cancel',e=>{e.preventDefault();stop()});
 dialog.querySelector('form').onsubmit=e=>{
  e.preventDefault();if(busy)return;const id=workspace?.pending_auto_selection?.id;if(!id)return;
  autoConsentKey=workspace.id+':'+id;autoStopping=false;
  const generate=dialog.querySelector('#auto-generate-plan').checked;dialog.close();
  action('approve_auto_selection',{approval_id:id,confirmed:true,generate_plan:generate}).then(()=>{if(workspace?.pending_auto_selection?.id===id&&!busy){autoConsentKey='';syncAutoConsent()}});
 };
 const status=document.createElement('div');status.id='auto-selection-status';status.hidden=true;status.innerHTML='<span>正在按已确认的范围补齐安排，可随时停止。</span><button class="text-button" id="auto-selection-stop">停止自动配置</button>';$('#progress').after(status);
 $('#auto-selection-stop').onclick=async()=>{autoStopping=true;clearTimeout(autoContinueTimer);if(busy&&runningJobId){try{await api('/api/jobs/'+runningJobId+'/cancel',{method:'POST'})}catch(e){error(e.message)}}else if(!busy)action('cancel_auto_selection')};
}
function syncAutoConsent(){
 if(!workspace||$('#application').hidden)return;ensureAutoConsent();
 if(autoTripId!==workspace.id){autoTripId=workspace.id;autoConsentKey='';autoStopping=false;clearTimeout(autoContinueTimer)}
 const pending=workspace.pending_auto_selection,dialog=$('#auto-selection-dialog');$('#auto-selection-status').hidden=!workspace.auto_selection_run;
 if(!pending||workspace.archived){if(dialog.open)dialog.close();return}
 const key=workspace.id+':'+pending.id;if(busy||autoConsentKey===key)return;
 dialog.querySelector('.auto-selection-scope').textContent=pending.description;dialog.querySelector('.auto-selection-notice').textContent=pending.notice;
 if(!dialog.open){dialog.querySelector('#auto-generate-plan').checked=false;dialog.showModal()}
}
function diagnosticHTML(c){
 const issues=c?.issues;if(!issues?.length)return conflictHTML(c);
 return `<section class="planning-diagnostics" aria-label="安排检查结果">${issues.map(i=>`<div class="diagnostic-item"><p>${esc(i.message)}</p><div class="diagnostic-links">${(i.candidate_ids||[]).filter(id=>workspace.catalog[id]).map(id=>`<button class="text-button" data-diagnostic-candidate="${esc(id)}" data-diagnostic-date="${esc(i.date)}" data-diagnostic-period="${esc(i.meal_period||'')}">${esc(workspace.catalog[id].name)} · 查看安排 ↗</button>`).join('')}${i.direction?`<button class="text-button" data-conflict-jump="transport" data-conflict-direction="${esc(i.direction)}">查看${i.direction==='return'?'返程':'去程'}班次 ↗</button>`:''}${i.settings?'<button class="text-button" data-open-settings>调整旅行日期 ↗</button>':''}${i.optimize?'<button class="text-button" data-action="optimize_plan">自动修订计划书 ↗</button>':''}${i.retry?'<button class="text-button" data-action="plan">按当前选择重新生成 ↗</button>':''}${!(i.candidate_ids||[]).length&&!i.retry&&!i.settings&&!i.direction?`<button class="text-button" data-tab="${sceneNames[i.view]?esc(i.view):'spot'}">查看${esc(sceneNames[i.view]||'景点安排')} ↗</button>`:''}</div></div>`).join('')}</section>`;
}
const basicConflictHTML=conflictHTML;conflictHTML=function(c){return c?.issues?.length?diagnosticHTML(c):basicConflictHTML(c)};
const assistanceRender=render;render=function(){assistanceRender();syncAutoConsent();syncPlanWarning()};
const assistanceMessageHTML=messageHTML;messageHTML=function(text,context){const c=context?.conflict||context?.ui?.conflict;return assistanceMessageHTML(text,context)+(c?.issues?.length?diagnosticHTML(c):'')};
const assistanceFinishJob=finishJob;finishJob=function(j,name,args={}){
 assistanceFinishJob(j,name,args);
 if(j.error&&j.ui?.conflict?.issues?.length){$('#error').hidden=false;$('#error').innerHTML=`已定位 ${j.ui.conflict.issues.length} 项安排问题。<button class="text-button" data-show-diagnostics>查看具体问题与修改入口 ↗</button>`}
 clearTimeout(autoContinueTimer);
 if(j.status==='completed'&&workspace?.auto_selection_run){const wid=workspace.id,epoch=tripEpoch,id=workspace.auto_selection_run.id;autoContinueTimer=setTimeout(()=>{if(workspace?.id!==wid||tripEpoch!==epoch||busy)return;if(autoStopping){action('cancel_auto_selection');return}action('continue_auto_selection',{approval_id:id})},180)}
};
document.addEventListener('click',e=>{
 const jump=e.target.closest('[data-diagnostic-candidate]');if(jump&&!busy){const id=jump.dataset.diagnosticCandidate,p=workspace.catalog[id];if(!p)return;if(p.kind==='food'&&jump.dataset.diagnosticDate){mealDate=jump.dataset.diagnosticDate;mealPeriod=jump.dataset.diagnosticPeriod||mealPeriod}focusCandidate(id,true);return}
 if(e.target.closest('[data-show-diagnostics]')){const blocks=[...document.querySelectorAll('#messages .planning-diagnostics')];if(blocks.length)blocks.at(-1).scrollIntoView({behavior:'smooth',block:'center'});else if(workspace?.ui?.conflict)$('#error').innerHTML=diagnosticHTML(workspace.ui.conflict)}
});
