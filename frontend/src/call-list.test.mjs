import {test} from 'node:test';
import assert from 'node:assert/strict';
import {callSummary,eligibleForCall,visibleSelection,csvCell} from './composables/call-list.mjs';
const client=()=>({id:'a',active:true,stage:'В работе',history:[{period:'2026Q2',unsent:10}],events:[]});
test('call list excludes missing period, zero debt and excluded clients',()=>{
 const c=client();assert.equal(eligibleForCall(c,'2026Q3'),false);assert.equal(eligibleForCall(c,'2026Q2'),true);
 for(const patch of [{excluded:true},{active:false},{stage:'Закрыт'},{history:[{period:'2026Q2',unsent:0}]}])assert.equal(eligibleForCall({...c,...patch},'2026Q2'),false);
});
test('call counts and callback are separate from assignment and document promise',()=>{
 const c={...client(),promise:'2026-11-01',events:[{type:'system',date:'2026-11-20'},
 {type:'call',period:'2026Q2',result:'Недозвон',date:'2026-11-01'},
 {type:'call',period:'2026Q3',result:'Перенос',callbackOn:'2026-12-01',date:'2026-11-02'}]};
 assert.equal(callSummary(c,'2026Q2').missed,1);assert.equal(callSummary(c,'2026Q2').count,1);
 assert.equal(callSummary(c,'2026Q3').callbackOn,'2026-12-01');assert.equal(callSummary(c,'2025').status,'Не звонили');
});
test('hidden clients leave selection',()=>assert.deepEqual(visibleSelection(['a','b'],[{client:{id:'b'}}]),['b']));
test('export prevents formulas and quotes values',()=>{assert.equal(csvCell('=1+1'),'"\'=1+1"');assert.equal(csvCell('A"B'),'"A""B"');});
