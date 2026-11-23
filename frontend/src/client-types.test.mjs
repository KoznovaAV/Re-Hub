import {test} from 'node:test';
import assert from 'node:assert/strict';
import {clientTypeOptions,clientTypeCodes,clientTypeText} from './composables/client-types.mjs';
import {callSummary} from './composables/call-list.mjs';
test('client type is separate from stage and document dynamics',()=>{
 const c={stage:'В работе',tags:['Повторный','Без наблюдения','Новый']};
 assert.deepEqual(clientTypeCodes(c),[]);assert.equal(clientTypeText(c),'Не указан');
 assert.ok(clientTypeOptions.some(o=>o.value==='vip'&&o.label==='ВИП'));
});
test('VIP and customer type labels are stable across source formats',()=>{
 assert.equal(clientTypeText({tags:['vip','VIP','Ключевой','tech_partner']}),'ВИП, Техпартнёр');
 assert.equal(clientTypeText({tags:['newcomer']}),'Новичок');
});
test('legacy contact result uses the customer wording without losing the call',()=>{
 const result=callSummary({events:[{type:'call',result:'Не тот контакт',date:'2026-11-01'}]});
 assert.equal(result.status,'Не тот администратор');assert.equal(result.count,1);
});
