(()=>{'use strict';
const STYLE=`
.mid{grid-template-rows:auto auto auto auto minmax(0,1fr)!important}
.model-activity{border-bottom:1px solid var(--line);background:var(--panel-2);display:grid;grid-template-rows:auto minmax(0,1fr);min-height:104px;max-height:220px}
.model-activity[hidden]{display:none}
.model-activity-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 10px;border-bottom:1px solid var(--line)}
.model-activity-title{font:700 10px/1.2 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.model-activity-meta{font:10px/1.25 var(--mono);color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1}
.model-activity-tabs{display:flex;gap:3px;flex:0 0 auto}
.model-activity-tabs button{height:25px;min-height:25px;padding:0 .5rem;font-size:9.5px;line-height:23px;border-radius:6px}
.model-activity-tabs button.active{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
.model-activity-body{margin:0;padding:8px 10px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:10.5px/1.45 var(--mono);color:var(--text);background:transparent}
`;
const style=document.createElement('style');style.id='nel-model-activity-style';style.textContent=STYLE;document.head.appendChild(style);
const TOKEN=new URLSearchParams(location.search).get('t')||'';
async function request(path){const res=await fetch(path,{headers:{'X-NEL-Token':TOKEN}});if(!res.ok)throw new Error(`${res.status} ${res.statusText}`);return res.json()}
function selectedRun(){const row=document.querySelector('.run-row.selected');if(!row)return'';const own=String(row.getAttribute('title')||'').trim();const caseSelect=document.getElementById('casePaneSelect');if(caseSelect&&!caseSelect.hidden&&caseSelect.value)return String(caseSelect.value).trim();return own}
const mid=document.querySelector('.column.mid'),midBody=mid?.querySelector('.mid-body');
if(!mid||!midBody)return;
const panel=document.createElement('div');panel.className='model-activity';panel.id='modelActivity';panel.hidden=true;panel.innerHTML=`<div class="model-activity-head"><span class="model-activity-title">Model activity</span><span class="model-activity-meta" id="modelActivityMeta"></span><span class="model-activity-tabs"><button type="button" id="modelThinkingTab" class="active">Thinking</button><button type="button" id="modelOutputTab">Output</button></span></div><pre class="model-activity-body" id="modelActivityBody"></pre>`;mid.insertBefore(panel,midBody);
const meta=document.getElementById('modelActivityMeta'),body=document.getElementById('modelActivityBody'),thinking=document.getElementById('modelThinkingTab'),output=document.getElementById('modelOutputTab');
let mode='thinking',run='',offset=0,pending='',snapshot=null,busy=false;
function inferOperation(){const text=document.getElementById('consoleView')?.textContent||'';const lines=text.split(/\r?\n/);for(let i=lines.length-1;i>=0;i--){const m=lines[i].match(/\]\s*-\s+\s*([^:]+):\s+(?:answering|retry|syntax-only repair)/i);if(m)return m[1].trim()}return''}
function resetCall(start){snapshot={start,reasoning:'',answer:'',finished:false,reasoningExposed:false,fallback:'',error:''}}
function consume(row){if(!row||typeof row!=='object')return;if(row.event==='start')resetCall(row);else if(!snapshot)return;else if(row.event==='reasoning'){snapshot.reasoning+=String(row.text||'');snapshot.reasoningExposed=true}else if(row.event==='output')snapshot.answer+=String(row.text||'');else if(row.event==='fallback')snapshot.fallback=String(row.message||'');else if(row.event==='error')snapshot.error=String(row.message||'');else if(row.event==='finish'){snapshot.finished=true;snapshot.reasoningExposed=!!row.reasoning_exposed||snapshot.reasoningExposed}}
function consumeText(text){pending+=String(text||'');const lines=pending.split(/\r?\n/);pending=lines.pop()||'';for(const line of lines){if(!line.trim())continue;try{consume(JSON.parse(line))}catch(_){}}}
function render(){if(!snapshot){panel.hidden=true;return}panel.hidden=false;const s=snapshot.start||{},op=inferOperation(),parts=[];if(op)parts.push(op);if(s.role)parts.push(s.role);if(s.model)parts.push(s.model);if(s.provider)parts.push(s.provider);if(s.reasoning&&s.reasoning!=='default')parts.push(`reasoning ${s.reasoning}`);meta.textContent=parts.join(' · ');thinking.classList.toggle('active',mode==='thinking');output.classList.toggle('active',mode==='output');if(mode==='output'){body.textContent=snapshot.answer||snapshot.error||'Waiting for model output…'}else if(snapshot.reasoning){body.textContent=snapshot.reasoning}else if(snapshot.finished&&!snapshot.reasoningExposed){body.textContent='Reasoning not exposed by this model/provider.'}else if(snapshot.fallback){body.textContent=snapshot.fallback}else{body.textContent='Waiting for provider-supplied reasoning…'}}
thinking.addEventListener('click',()=>{mode='thinking';render()});output.addEventListener('click',()=>{mode='output';render()});
async function poll(){if(busy)return;const selected=selectedRun();if(!selected){run='';offset=0;pending='';snapshot=null;render();return}if(selected!==run){run=selected;offset=0;pending='';snapshot=null;render()}busy=true;const previousOffset=offset;try{const d=await request(`/api/model-activity?run=${encodeURIComponent(run)}&offset=${offset}`);const next=Number(d.offset||0);if(next<previousOffset){offset=0;pending='';snapshot=null}consumeText(d.text||'');offset=next;render()}catch(_){if(!snapshot)panel.hidden=true}finally{busy=false}}
setInterval(poll,350);poll();
})();
