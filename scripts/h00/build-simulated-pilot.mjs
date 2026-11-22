// Educational simulation of measurements. No people were observed or contacted.
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {sample,callList} from '../../frontend/src/pilot-data.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url));
const gold={};
for(const group of ['A','B']){
 const rows=sample(group);
 gold[group]={all_ids:rows.map(r=>r.client),expected:callList(rows,'2026Q3',8).map(r=>r.client),excluded:rows.filter(r=>r.excluded).map(r=>r.client),approved_by:null,expert_approved:false};
}
const example={data_kind:'simulated',title:'СМОДЕЛИРОВАННЫЙ УЧЕБНЫЙ ПРИМЕР. НЕ ЗАМЕРЫ ПОЛЬЗОВАТЕЛЕЙ.',
 human_participants:0,source:'Assumed times and outputs for demonstrating the evaluation method',
 assumptions:['Два виртуальных участника, два набора по 15 синтетических клиентов',
 'Секунды и ошибки придуманы. Это не наблюдения и не прогноз скорости сотрудников',
 'Эталон получен из учебного набора /pilot; заказчик и эксперт его не утверждали',
 'Эта упрощённая проверка фильтров не заменяет основной сценарий на реальных данных'],
 gold,runs:[
 {participant:'SIM-01',tool:'excel',group:'A',seconds:110,ids:gold.A.expected.slice(0,-1)},
 {participant:'SIM-01',tool:'rehub',group:'B',seconds:42,ids:[...gold.B.expected]},
 {participant:'SIM-02',tool:'rehub',group:'A',seconds:35,ids:[...gold.A.expected]},
 {participant:'SIM-02',tool:'excel',group:'B',seconds:90,ids:[...gold.B.expected,gold.B.all_ids.find(id=>!gold.B.expected.includes(id)&&!gold.B.excluded.includes(id))]},
 ]};
await fs.mkdir(root+'contracts/testing/h00/simulated',{recursive:true});
await fs.writeFile(root+'contracts/testing/h00/simulated/pilot.json',JSON.stringify(example,null,2)+'\n');
const negative=structuredClone(example);
negative.title='СМОДЕЛИРОВАННЫЙ КОНТРПРИМЕР: быстрый, но ошибочный отбор';
negative.runs[1].ids.push(gold.B.excluded[0]);
await fs.writeFile(root+'contracts/testing/h00/simulated/pilot-failed-quality.json',JSON.stringify(negative,null,2)+'\n');
console.log(JSON.stringify({kind:'simulated',human_participants:0,expected:Object.fromEntries(Object.entries(gold).map(([g,v])=>[g,v.expected]))}));
