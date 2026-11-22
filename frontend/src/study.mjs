import {csvCell} from './composables/call-list.mjs';
import {sample,callList} from './pilot-data.mjs';
import {createStudy,finishRun,plan,journal,parseIDs,sourceCSV} from './study-session.mjs';
const $=id=>document.getElementById(id),key='rehub-h00-study-v1';
let study=null,running=null,interval=null,visible=0;
function save(){localStorage.setItem(key,JSON.stringify({study,unfinished:running?{...running,mono:undefined}:null}));}
function fail(error){$('error').textContent=error.message;}
function download(name,text,type='text/plain'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function task(){return plan[study.runs.length];}
function selected(){return callList(sample(task().group),$('period').value,Number($('minimum').value)).map(x=>x.client);}
function filter(){if(running&&task().tool==='rehub')$('matches').textContent=selected().join(', ')||'Список пуст';}
function render(){
 $('setup').hidden=Boolean(study);$('session').hidden=!study||study.runs.length===4;$('results').hidden=!study;
 if(!study)return;
 const t=task();if(t){$('task-heading').textContent=`Проход ${study.runs.length+1} из 4`;$('assignment').textContent=`Участник ${study.participants[t.person]} · ${t.tool==='excel'?'Excel / Calc':'Re:Hub'} · набор ${t.group}`;}
 $('start').disabled=Boolean(running);$('work').hidden=!running;
 $('excel').hidden=!running||t?.tool!=='excel';$('rehub').hidden=!running||t?.tool!=='rehub';
 $('kind').textContent=study.executor==='agent'?'Фактический прогон агента. Участников-людей: 0.':'Сессия для двух людей. Коды и подлинность участия проверяет организатор.';
 $('runs').replaceChildren(...study.runs.map(r=>{const tr=document.createElement('tr');for(const v of [r.participant,r.tool,r.group,r.seconds.toFixed(3),`${(r.precision*100).toFixed(1)}%`,`${(r.recall*100).toFixed(1)}%`])tr.insertCell().textContent=v;return tr;}));
 const median=xs=>{const a=xs.sort((a,b)=>a-b);return a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2;};
 $('summary').textContent=study.runs.length===4?`Сессия завершена. Медиана Excel: ${median(study.runs.filter(r=>r.tool==='excel').map(r=>r.seconds)).toFixed(3)} с; Re:Hub: ${median(study.runs.filter(r=>r.tool==='rehub').map(r=>r.seconds)).toFixed(3)} с. Это результат этой сессии; вывод проверяется оценщиком.`:`Завершено ${study.runs.length}/4; прервано: ${study.aborted.length}.`;
 $('gold').closest('details').hidden=study.runs.length!==4;
 $('gold').textContent=study.runs.length!==4?'':['A','B'].map(g=>`${g}: ${callList(sample(g),'2026Q3',8).map(x=>x.client).join(', ')}`).join('; ');
}
try{const stored=JSON.parse(localStorage.getItem(key)||'null');if(stored?.study){study=stored.study;if(stored.unfinished){study.aborted.push({...stored.unfinished,reason:'page_reloaded'});save();}}}catch{localStorage.removeItem(key);}
$('create').onclick=()=>{try{study=createStudy([$('person1').value,$('person2').value],$('executor').value);save();render();}catch(e){fail(e);}};
$('start').onclick=()=>{running={started_at:new Date().toISOString(),mono:performance.now(),task:task()};visible=0;$('error').textContent='';$('period').value='2026Q2';$('minimum').value='0';$('answer').value='';$('answer-file').value='';save();render();filter();interval=setInterval(()=>{$('timer').textContent=((performance.now()-running.mono)/1000).toFixed(1)+' с';},100);};
$('source').onclick=()=>download(`pilot-${task().group}.csv`,sourceCSV(task().group),'text/csv;charset=utf-8');
$('answer-file').onchange=async e=>{try{$('answer').value=await e.target.files[0].text();}catch(err){fail(err);}};
$('finish').onclick=()=>{try{
 if(!running)throw Error('Сначала начните проход');
 const ids=task().tool==='excel'?parseIDs($('answer').value):selected();
 const run=finishRun(study,{ids,elapsed_ms:performance.now()-running.mono,started_at:running.started_at,ended_at:new Date().toISOString(),visibility_changes:visible});
 clearInterval(interval);running=null;save();download(`answer-${run.participant}-${run.tool}-${run.group}.csv`,['client',...ids].join('\r\n'),'text/csv');$('timer').textContent=run.seconds.toFixed(3)+' с';render();
 }catch(e){fail(e);}};
$('abort').onclick=()=>{if(!running)return;study.aborted.push({...running,mono:undefined,reason:'participant_aborted',elapsed_ms:performance.now()-running.mono});clearInterval(interval);running=null;save();render();};
for(const id of ['period','minimum'])$(id).oninput=filter;
document.addEventListener('visibilitychange',()=>{if(running)visible++;});
$('journal').onclick=()=>download('h00-journal.json',JSON.stringify(journal(study,$('approved').value),null,2),'application/json');
$('protocol').onclick=()=>{const rows=[['participant','tool','group','seconds','ids','precision','recall','excluded_errors','executor','started_at','ended_at'],...study.runs.map(r=>[r.participant,r.tool,r.group,r.seconds,r.ids.join(' '),r.precision,r.recall,r.excluded_errors,r.executor,r.started_at,r.ended_at])];download('h00-protocol.csv',rows.map(r=>r.map(csvCell).join(',')).join('\r\n'),'text/csv');};
$('reset').onclick=()=>{if(running){fail(Error('Сначала завершите или прервите проход'));return;}if(study.runs.length&&!confirm('Скачайте журнал перед удалением. Начать новую сессию?'))return;study=null;localStorage.removeItem(key);render();};
render();
