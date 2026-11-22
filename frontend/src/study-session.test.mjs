import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createStudy,finishRun,journal,plan,parseIDs,sourceCSV} from './study-session.mjs';
import {sample,callList} from './pilot-data.mjs';
const stamp='2026-11-22T15:00:00.000Z';
test('counterbalanced task journal records observed durations and quality without inventing people',()=>{
 const s=createStudy(['AUTO-1','AUTO-2'],'automation');
 for(const task of plan)finishRun(s,{ids:callList(sample(task.group),'2026Q3',8).map(x=>x.client),elapsed_ms:1234,started_at:stamp,ended_at:'2026-11-22T15:00:01.234Z'});
 const j=journal(s);assert.equal(j.data_kind,'automated');assert.equal(j.complete,true);assert.equal(j.runs.length,4);assert.ok(j.runs.every(r=>r.seconds===1.234&&r.precision===1&&r.recall===1));assert.equal(j.gold.A.approved_by,null);
 assert.deepEqual(j.runs.map(r=>[r.participant,r.tool,r.group]),[['AUTO-1','excel','A'],['AUTO-1','rehub','B'],['AUTO-2','rehub','A'],['AUTO-2','excel','B']]);
});
test('human collection needs two distinct codes and an explicit reviewer',()=>{
 assert.throws(()=>createStudy(['one','one']));assert.throws(()=>createStudy(['','two']));
 const s=createStudy(['P-1','P-2']);assert.equal(journal(s).data_kind,'measured');assert.equal(journal(s).complete,false);assert.equal(journal(s,'EXPERT-1').gold.B.approved_by,'EXPERT-1');
});
test('a wrong answer is retained and scored instead of silently repaired',()=>{
 const s=createStudy(['P-1','P-2']);const r=finishRun(s,{ids:['PILOT-01'],elapsed_ms:2000,started_at:stamp,ended_at:stamp});assert.equal(r.recall,0);assert.equal(r.excluded_errors,1);assert.equal(r.ids[0],'PILOT-01');assert.equal(r.missed_ids.length,3);
 assert.throws(()=>finishRun(s,{ids:['PILOT-01'],elapsed_ms:2000,started_at:stamp,ended_at:stamp}));
});
test('CSV uses explicit observation markers, preserving missing versus zero',()=>{
 const csv=sourceCSV('A');assert.equal(csv.split('\r\n').length,31);assert.match(csv,/excluded,observed/);assert.deepEqual(parseIDs('client\nPILOT-04\nPILOT-05'),['PILOT-04','PILOT-05']);assert.throws(()=>parseIDs('PILOT-04 PILOT-04'));assert.deepEqual(parseIDs('"client"\n"PILOT-04"'),['PILOT-04']);
});
