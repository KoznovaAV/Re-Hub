import { store, periods, users } from '../mock/data.js';

export const actorIDs={admin:'00000000-0000-0000-0000-000000000001','operator-a':'00000000-0000-0000-0000-000000000002','operator-b':'00000000-0000-0000-0000-000000000003'};
const actorKey=id=>Object.keys(actorIDs).find(key=>actorIDs[key]===id)??null;
const day=value=>value?String(value).slice(0,10):null;
export async function request(path,{method='GET',body,actor=store.actor}={}){
 const headers={'X-Role':users[actor]?.role??'operator','X-User-Id':actorIDs[actor]};
 if(body&&!(body instanceof FormData)){headers['Content-Type']='application/json';body=JSON.stringify(body);}
 const response=await fetch('/api/v1'+path,{method,headers,body,signal:AbortSignal.timeout(60000)});
 const result=await response.json();if(!response.ok)throw new Error(result.message??result.error??'Запрос не выполнен');return result;
}
let generation=0;
export async function reloadWorkspace(){
 const token=++generation;store.loading=true;
 try{
  const [p,s]=await Promise.all([request('/periods'),request('/slices?limit=500')]);
  const items=[];
  for(let offset=0;;){
   const page=await request('/workspace?limit=1000&offset='+offset);
   for(const c of page.data??[]){
    const events=(page.events[c.id]??[]).map(e=>({id:e.id,type:e.event_type,date:day(e.event_date),createdAt:e.created_at,result:e.result,text:e.comment??'',title:e.event_type==='call'?'Звонок':e.event_type==='system'?'Изменение ответственного':e.event_type==='claim'?'Претензия / санкция':'Комментарий',author:e.author_name??'Система',promise:day(e.promised_at),promiseLabel:e.promise_label,callbackOn:day(e.callback_on),period:e.period_code}));
    const actions=(page.actions[c.id]??[]).map(a=>({...a,date:day(a.date),reason:a.comment}));
    items.push({id:c.id,externalId:c.external_id,name:c.name,inn:c.inn,kpp:c.kpp,stage:c.stage,owner:actorKey(c.assigned_to),pool:c.in_pool,active:!c.inactive,inactive:c.inactive,excluded:c.excluded,joinedOn:day(c.joined_on),tags:c.tags??[],promise:day(c.promised_at),contact:{name:c.contact_name||'Не указан',phone:c.contact_phone||'—',email:c.contact_email||'—',details:c.contact_details},history:(page.history[c.id]??[]).map(h=>({period:h.period_code,date:day(h.slice_date),total:h.total_docs,inherited:h.inherited,unsent:h.not_sent_docs,observed:true})),events,claims:actions.filter(a=>a.kind==='claim'),sanctions:actions.filter(a=>a.kind==='sanction')});
   }
   offset+=(page.data??[]).length;if(offset>=page.meta.total)break;if(!page.data.length)throw new Error('Неполная страница клиентов');
  }
  if(token!==generation)return;
  periods.splice(0,periods.length,...(p.data??[]).map(v=>({code:v.code,label:v.code})));
  store.periodDates={};for(const slice of s.data??[]){const date=day(slice.slice_date);if(date>(store.periodDates[slice.period_code]??''))store.periodDates[slice.period_code]=date;}
  store.clients=items;
  store.importLog=(s.data??[]).map(v=>({id:v.id,date:day(v.slice_date),kind:'Срез',file:v.file_name,accepted:v.rows,errors:0}));
  if(!periods.some(v=>v.code===store.reportPeriod))store.reportPeriod=periods.at(-1)?.code??'';
 }finally{if(token===generation)store.loading=false;}
}
export async function mutateClient(clientId,path,body,actor){
 try{
  const c=store.clients.find(v=>v.id===clientId);if(!c)throw new Error('Клиент не найден');
  const result=await request('/clients/'+encodeURIComponent(c.externalId)+path,{method:'POST',body,actor});
  await reloadWorkspace();return {ok:true,...result,ownerName:store.clients.find(v=>v.id===clientId)?.owner?users[store.clients.find(v=>v.id===clientId).owner].name:'Свободен'};
 }catch(error){return {ok:false,message:error.message};}
}
export async function upload(file,kind,{preview=false,date,context,acceptPartial=false}={}){
 const form=new FormData();form.append('file',file);if(date)form.append('snapshot_date',date);
 if(context)form.append('context',context);form.append('accept_partial',String(acceptPartial));
 return request((kind==='clients'?'/clients/import':'/slices')+(preview?'?preview=true':''),{method:'POST',body:form});
}
