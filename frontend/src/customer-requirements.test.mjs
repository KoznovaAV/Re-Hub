import {test,beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {store,clientMetrics} from './mock/data.js';
import {eligibleForCall} from './composables/call-list.mjs';
import {confirmSlice,reassignClient,releaseClient,addEvent,addToPool,addClientAction} from './mock/api.js';
const observation=(unsent,date='2026-10-20',total=100,period='2026Q3')=>({period,date,total,unsent,observed:true});
const client=(history,extra={})=>({id:'s',externalId:'SCENARIO',name:'Контроль',stage:'Не в работе',active:true,tags:[],owner:null,pool:false,history,events:[],...extra});
beforeEach(()=>{store.live=false;store.actor='admin';store.reportPeriod='2026Q3';store.periodDates={};});
test('S1: partial decrease is computed within a quarter and owner is retained',()=>{
 const c=client([observation(40),observation(15,'2026-11-01')],{owner:'operator-a'});const m=clientMetrics(c);
 assert.equal(m.dynamics,'Уменьшается');assert.equal(m.delta,-25);assert.equal(c.owner,'operator-a');
});
test('S2/S4: unchanged and partial values do not erase contacts or change owner',async()=>{
 const c=client([observation(40)],{owner:'operator-a',promise:'2026-11-15',events:[{id:'old',type:'call',date:'2026-11-01'}]});store.clients=[c];
 for(const n of [40,25]){await confirmSlice({period:'2026Q3',sliceDate:n===40?'2026-11-02':'2026-11-03',rows:[{status:'update',externalId:c.externalId,total:100,unsent:n}],counters:{accepted:1,errors:0},fileName:'test.xlsx'});assert.equal(c.owner,'operator-a');assert.ok(c.events.some(e=>e.id==='old'));}
 assert.equal(c.history.length,3);assert.equal(clientMetrics(c).delta,-15);
 assert.equal(c.promise,'2026-11-15');
});
test('S3: a positive value after a closed cycle is repeated, not a cross-quarter delta',()=>{
 const c=client([observation(30,'2025-10-01',200,'2025Q3'),observation(0,'2025-11-01',200,'2025Q3'),observation(12,'2026-10-20',210)]);
 assert.equal(clientMetrics(c).dynamics,'Повторный');assert.equal(clientMetrics(c).delta,null);
});
test('S5: a client already owned is not duplicated in the pool',async()=>{
 const c=client([observation(45)],{owner:'operator-a'});store.clients=[c];
 assert.equal((await addToPool(['s'],'admin')).changed,0);assert.equal(c.owner,'operator-a');
});
test('S6: 4% is excluded for an ordinary client and allowed for a newcomer; 5% is inclusive',()=>{
 const c=client([observation(4)]);assert.equal(eligibleForCall(c,'2026Q3'),false);
 c.tags=['Новичок'];assert.equal(eligibleForCall(c,'2026Q3'),true);c.tags=['newcomer'];assert.equal(eligibleForCall(c,'2026Q3'),true);c.tags=[];c.history[0].unsent=5;assert.equal(eligibleForCall(c,'2026Q3'),true);
});
test('S7: missing observation is distinct from zero and is not a candidate',()=>{
 const c=client([observation(30)]);store.periodDates={'2026Q3':'2026-11-01'};
 assert.equal(clientMetrics(c).missing,true);assert.equal(clientMetrics(c).unsent,30);
 assert.equal(eligibleForCall(c,'2026Q3',store.periodDates['2026Q3']),false);
 c.history.push({...observation(0,'2026-11-01'),observed:false});assert.equal(clientMetrics(c).dynamics,'Нет наблюдения');
});
test('S8: a missing total inherits within the same quarter, never from another quarter',async()=>{
 const c=client([observation(40)]);store.clients=[c];
 await confirmSlice({period:'2026Q3',sliceDate:'2026-11-01',rows:[{status:'update',externalId:c.externalId,total:null,unsent:30}],counters:{accepted:1,errors:0},fileName:'test.xlsx'});
 assert.equal(c.history.length,2);assert.equal(c.history[0].unsent,40);assert.equal(clientMetrics(c).total,100);assert.equal(clientMetrics(c).delta,-10);
 const other=client([observation(40,'2026-07-20',100,'2026Q2'),observation(30,'2026-10-20',null)]);assert.equal(clientMetrics(other).total,null);
});
test('zero documents produces a separate fully transferred state',()=>assert.equal(clientMetrics(client([observation(40),observation(0,'2026-11-01')])).dynamics,'Все документы переданы'));
test('operator transfers and releases explicitly; the former owner cannot write',async()=>{
 const c=client([observation(40)],{owner:'operator-a',stage:'В работе'});store.clients=[c];
 assert.equal((await reassignClient('s','admin','operator-b')).ok,false);
 assert.equal((await reassignClient('s','operator-a','operator-b')).ok,true);
 assert.equal((await addEvent('s',{type:'comment',comment:'old owner'},'operator-a')).ok,false);
 assert.equal((await releaseClient('s','operator-b')).ok,true);assert.equal(c.owner,null);assert.equal(c.pool,true);
});
test('historical dates and official letter details are retained',async()=>{
 const c=client([observation(40)],{owner:'operator-a'});store.clients=[c];
 const r=await addEvent('s',{type:'comment',comment:'История',date:'2026-10-01'},'operator-a');assert.equal(r.event.date,'2026-10-01');
 assert.equal((await addClientAction('s',{kind:'claim',number:'42',date:'2026-11-01',status:'Направлена'},'admin')).ok,true);
 assert.equal(c.claims[0].number,'42');assert.equal(c.claims[0].date,'2026-11-01');
});
