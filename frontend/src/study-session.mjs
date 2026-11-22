import {sample,callList} from './pilot-data.mjs';
export const STUDY_VERSION='h00-browser-v1';
export const plan=[{person:0,tool:'excel',group:'A'},{person:0,tool:'rehub',group:'B'},{person:1,tool:'rehub',group:'A'},{person:1,tool:'excel',group:'B'}];
export function createStudy(participants,executor='human') {
 const names=participants.map(x=>x.trim());
 if(names.length!==2||names.some(x=>!x)||new Set(names).size!==2)throw Error('Укажите два разных кода участника');
 if(!['human','automation'].includes(executor))throw Error('Неизвестный исполнитель');
 return {version:STUDY_VERSION,executor,participants:names,created_at:new Date().toISOString(),runs:[],aborted:[]};
}
export function parseIDs(text) {
 const ids=text.trim().split(/[\s,;]+/).filter(Boolean).map(x=>x.replace(/^"|"$/g,'' )).filter(x=>!['client','external_id','id'].includes(x.toLowerCase()));
 if(new Set(ids).size!==ids.length)throw Error('В ответе повторяются ID');
 return ids;
}
export function finishRun(study,{ids,elapsed_ms,started_at,ended_at,visibility_changes=0}) {
 const task=plan[study.runs.length];if(!task)throw Error('Все проходы завершены');
 if(!Number.isFinite(elapsed_ms)||elapsed_ms<=0)throw Error('Некорректное время');
 if(!started_at||!ended_at||!Number.isFinite(Date.parse(started_at))||!Number.isFinite(Date.parse(ended_at))||Date.parse(ended_at)<Date.parse(started_at))throw Error('Некорректные даты');
 const allowed=new Set(sample(task.group).map(x=>x.client));
 if(new Set(ids).size!==ids.length||ids.some(x=>!allowed.has(x)))throw Error('В ответе есть повторные ID или ID другого набора');
 const expected=new Set(callList(sample(task.group),'2026Q3',8).map(x=>x.client));
 const selected=new Set(ids),hits=ids.filter(x=>expected.has(x)).length;
 const excluded=new Set(sample(task.group).filter(x=>x.excluded).map(x=>x.client));
 const run={participant:study.participants[task.person],tool:task.tool,group:task.group,seconds:elapsed_ms/1000,ids:[...ids],executor:study.executor,started_at,ended_at,elapsed_ms,visibility_changes,source:'browser_monotonic_timer',precision:ids.length?hits/ids.length:0,recall:hits/expected.size,excluded_errors:ids.filter(x=>excluded.has(x)).length,missed_ids:[...expected].filter(x=>!selected.has(x))};
 study.runs.push(run);return run;
}
export function journal(study,approvedBy=null) {
 const gold=Object.fromEntries(['A','B'].map(group=>[group,{all_ids:sample(group).map(x=>x.client),expected:callList(sample(group),'2026Q3',8).map(x=>x.client),excluded:sample(group).filter(x=>x.excluded).map(x=>x.client),approved_by:approvedBy?.trim()||null}]));
 return {study_version:study.version,data_kind:study.executor==='human'?'measured':'automated',dataset_kind:'synthetic',task:'2026Q3; unsent >= 8; observed; not excluded; not contacted',timing_scope:'from task presentation through result submission; source download and opening included for Excel',gold,runs:study.runs,aborted:study.aborted,complete:study.runs.length===4};
}
export function sourceCSV(group) {
 return ['client,period,unsent,contacted,promise,excluded,observed',...sample(group).flatMap(c=>c.periods.map(p=>[c.client,p.period,p.observed?p.unsent:'',Number(p.contacted),p.promise,Number(c.excluded),Number(p.observed)].join(',')))].join('\r\n');
}
