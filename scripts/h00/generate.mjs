import fs from 'node:fs/promises';
import {resolve} from 'node:path';
// Контрольные случаи заданы отдельно от реализации отбора.
const cases=[
 {name:'eligible',unsent:40,expected:true},
 {name:'zero',unsent:0},
 {name:'excluded',unsent:40,excluded:true},
 {name:'inactive',unsent:40,inactive:true},
 {name:'missing',unsent:40,observed:false},
 {name:'called',unsent:40,contacted:true},
 {name:'below_threshold',unsent:5},
 {name:'closed',unsent:40,closed:true},
 {name:'unknown_total',unsent:40,total:0},
 {name:'boundary',unsent:30,expected:true},
 {name:'q2_only',unsent:40,expected:true,only:'2026Q2'},
 {name:'q3_only',unsent:40,expected:true,only:'2026Q3'},
];
const out=resolve(process.argv[2]??'contracts/testing/h00');await fs.mkdir(out,{recursive:true});
for(const size of [30,4000]){
 const clients=[];const rows=[];const expected={'2026Q2':[],'2026Q3':[]};
 for(let n=0;n<size;n++){
  const scenario=cases[n%cases.length];const id='BCH'+String(n+1).padStart(5,'0');
  clients.push({id,name:'Тест '+(n+1),excluded:!!scenario.excluded,inactive:!!scenario.inactive,closed:!!scenario.closed,scenario:scenario.name});
  for(const period of ['2026Q2','2026Q3']){
   const observed=scenario.observed!==false&&(!scenario.only||scenario.only===period);
   rows.push({id,period,unsent:scenario.unsent,total:scenario.total??100,excluded:!!scenario.excluded,inactive:!!scenario.inactive,contacted:!!scenario.contacted,observed,closed:!!scenario.closed});
   if(scenario.expected&&observed)expected[period].push(id);
  }
 }
 await fs.writeFile(resolve(out,`data-${size}.json`),JSON.stringify({size,synthetic:true,expert_approved:false,criteria:{min_unsent:8,min_share:30,contacted:'no'},clients,rows,expected},null,2)+'\n');
}
