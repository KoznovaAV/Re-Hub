import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=fileURLToPath(new URL('../../',import.meta.url));
const outputDir=`${root}/contracts/testing/h00`;
await fs.mkdir(outputDir,{recursive:true});
for(const n of [30,4000]){
 const data=JSON.parse(await fs.readFile(`${root}/contracts/testing/h00/data-${n}.json`,'utf8'));
 const wb=Workbook.create();const sh=wb.worksheets.add('Selection');sh.showGridLines=false;
 sh.getRange('A1:J1').values=[['ID','Период','Не передано','Всего','Исключён','Неактивен','Звонили','Есть срез','Закрыт','ID для обзвона']];
 sh.getRange(`A2:I${data.rows.length+1}`).values=data.rows.map(r=>[r.id,r.period,r.unsent,r.total,+r.excluded,+r.inactive,+r.contacted,+r.observed,+r.closed]);
 sh.getRange('L1:M3').values=[['Период','2026Q3'],['Не передано от',8],['Доля от, %',30]];
 sh.getRange(`J2:J${data.rows.length+1}`).formulas=data.rows.map((r,i)=>{const k=i+2;return [`=IF(AND(B${k}=$M$1,H${k}=1,E${k}=0,F${k}=0,I${k}=0,C${k}>0,C${k}>=$M$2,IF(D${k}>0,C${k}/D${k}*100,0)>=$M$3,G${k}=0),A${k},"")`];});
 sh.getRange('A1:J1').format={fill:'#20364D',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'}};
 sh.getRange('A2:J20').format.font={name:'Arial',size:10};
 sh.getRange('A1:B20').format.columnWidth=15;sh.getRange('C1:J20').format.columnWidth=17;sh.getRange('L1:M3').format.columnWidth=22;
 sh.getRange('M1:M3').format.fill='#FFF2CC';sh.freezePanes.freezeRows(1);wb.recalculate();
 console.log(n,(await wb.inspect({kind:'region',sheetId:'Selection',range:'I1:M6',maxChars:1200,tableMaxRows:6,tableMaxCols:5})).ndjson);
 if(n===30){const p=await wb.render({sheetName:'Selection',range:'A1:M12',scale:1,format:'png'});await fs.writeFile(`${outputDir}/preview.png`,new Uint8Array(await p.arrayBuffer()));}
 await(await SpreadsheetFile.exportXlsx(wb)).save(`${outputDir}/selection-${n}.xlsx`);
}
