import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {JSDOM} from 'jsdom';
import {sample,callList} from './pilot-data.mjs';

test('pilot exports exactly the displayed IDs for both synthetic groups',async()=>{
 const html=await readFile(new URL('./pilot.html',import.meta.url),'utf8');
 const dom=new JSDOM(html,{url:'http://localhost/pilot',runScripts:'outside-only'});
 const w=dom.window;let blob;const downloads=[];
 w.sample=sample;w.callList=callList;w.Blob=Blob;
 w.URL.createObjectURL=value=>{blob=value;return 'blob:test';};w.URL.revokeObjectURL=()=>{};
 w.HTMLAnchorElement.prototype.click=function(){downloads.push(this.download);};
 const script=w.document.querySelector('script[type=module]').textContent.replace(/^\s*import .*?;\s*$/m,'');
 w.eval(script);
 for(const [group,wanted] of [['A',['PILOT-04','PILOT-05','PILOT-12']],['B',['PILOT-19','PILOT-20','PILOT-27']]]){
  w.document.getElementById('group').value=group;
  w.document.getElementById('group').dispatchEvent(new w.Event('change'));
  assert.equal(w.document.getElementById('clients').textContent,wanted.join(', '));
  w.document.getElementById('save-list').click();
  assert.equal(await blob.text(),['client',...wanted].join('\r\n'));
  assert.equal(downloads.at(-1),`call-list-${group}.csv`);
 }
 dom.window.close();
});
