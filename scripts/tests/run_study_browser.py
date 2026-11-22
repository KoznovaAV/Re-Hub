"""Observed automated run of /study. This does not recruit or simulate human participants.

Uses a real Chromium page and LibreOffice Calc for the baseline. Timings come from
page performance.now(), not constants. Run only against synthetic study data.
"""
import argparse,csv,json,os,socket,subprocess,tempfile,time
from pathlib import Path
from urllib.request import urlopen
from openpyxl import Workbook
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--chromium',required=True);p.add_argument('--soffice',default='soffice');p.add_argument('--out',type=Path,default=ROOT/'reports/h00');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    log=tempfile.TemporaryFile();server=subprocess.Popen(['node','frontend/src/server.mjs'],cwd=ROOT,env={**os.environ,'PORT':str(port),'WEB_HOST':'127.0.0.1','REHUB_MODE':'demo'},stdout=log,stderr=log)
    try:
        for _ in range(100):
            try:
                with urlopen(f'http://127.0.0.1:{port}/health',timeout=.3):break
            except OSError:time.sleep(.1)
        with tempfile.TemporaryDirectory(prefix='h00-browser-workflow-') as temp, sync_playwright() as pw:
            folder=Path(temp);browser=pw.chromium.launch(executable_path=a.chromium,args=['--no-sandbox','--single-process','--no-zygote','--disable-gpu']);page=browser.new_page(viewport={'width':1240,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{port}/study');page.locator('#person1').fill('AUTO-ORDER-1');page.locator('#person2').fill('AUTO-ORDER-2');page.locator('#executor').select_option('automation');page.locator('#create').click()
            for index,tool in enumerate(['excel','rehub','rehub','excel']):
                assert not page.locator('#gold').is_visible()
                page.locator('#start').click()
                if tool=='excel':
                    work=folder/str(index);work.mkdir()
                    with page.expect_download() as event:page.locator('#source').click()
                    source=work/'source.csv';event.value.save_as(source)
                    rows=list(csv.reader(source.open()));book=Workbook();sheet=book.active;sheet.title='Selection'
                    for row in rows:
                        sheet.append([int(v) if v.isdigit() else v for v in row])
                    sheet.cell(1,8,'selected_id')
                    for k in range(2,len(rows)+1):sheet.cell(k,8,f'=IF(AND(B{k}="2026Q3",G{k}=1,F{k}=0,C{k}>=8,D{k}=0),A{k},"")')
                    workbook=work/'selection.xlsx';book.save(workbook);book.close()
                    result=subprocess.run([a.soffice,f'-env:UserInstallation={(work/"profile").as_uri()}','--headless','--convert-to','csv','--outdir',str(work),str(workbook)],capture_output=True,text=True,timeout=90)
                    if result.returncode:raise RuntimeError(result.stderr)
                    selected=[r[7] for r in list(csv.reader((work/'selection.csv').open()))[1:] if len(r)>7 and r[7]]
                    page.locator('#answer').fill('\n'.join(selected))
                else:
                    page.locator('#period').select_option('2026Q3');page.locator('#minimum').fill('8')
                with page.expect_download() as event:page.locator('#finish').click()
                event.value.save_as(folder/f'answer-{index}.csv')
                if page.locator('#error').inner_text():raise AssertionError(page.locator('#error').inner_text())
            with page.expect_download() as event:page.locator('#journal').click()
            event.value.save_as(a.out/'browser-workflow-journal.json')
            with page.expect_download() as event:page.locator('#protocol').click()
            event.value.save_as(a.out/'browser-workflow-protocol.csv')
            page.screenshot(path=str(a.out/'browser-workflow-screen.png'),full_page=True)
            assert not errors,errors
            browser.close()
        evaluation=subprocess.run(['python3','scripts/evaluate-h00.py',str(a.out/'browser-workflow-journal.json')],cwd=ROOT,capture_output=True,text=True,check=True)
        result=json.loads(evaluation.stdout);assert result['human_participants']==0 and result['confirmed'] is False and result['quality_passed']
        (a.out/'browser-workflow-evaluation.json').write_text(evaluation.stdout)
        print(json.dumps({k:result[k] for k in ['data_kind','human_participants','median_seconds','speedup','quality_passed','confirmed']},ensure_ascii=False,indent=2))
    finally:server.terminate();server.wait(timeout=10);log.close()
if __name__=='__main__':main()
