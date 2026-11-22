"""Automated Calc-vs-Go experiment. This measures software, not administrator task time."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import tempfile
import time
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[2]
DB=os.environ.get('H00_BENCH_DATABASE_URL','')


def check_book(path, data):
    book=load_workbook(path,data_only=False,read_only=True)
    rows=book.active.iter_rows(min_row=2,max_col=9,values_only=True)
    for actual, expected in zip(rows,data['rows'],strict=True):
        wanted=(expected['id'],expected['period'],expected['unsent'],expected['total'],int(expected['excluded']),int(expected['inactive']),int(expected['contacted']),int(expected['observed']),int(expected['closed']))
        if actual!=wanted: raise AssertionError(('workbook and API source differ',actual,wanted))
    book.close()


def save_ids(path, ids):
    with path.open('w',newline='',encoding='utf-8') as file:
        writer=csv.writer(file);writer.writerow(['external_id']);writer.writerows([value] for value in sorted(ids))


def get_ids(base, period='2026Q3'):
    ids=[];offset=0
    while True:
        query=urlencode({'period':period,'min_unsent':8,'min_share':30,'contacted':'no','limit':1000,'offset':offset})
        with urlopen(Request(base+'/api/v1/call-list?'+query,headers={'X-Role':'admin','X-User-Id':'00000000-0000-0000-0000-000000000001'}),timeout=20) as response: result=json.load(response)
        ids.extend(c['external_id'] for c in result['data'])
        total=result['meta']['total']
        if len(ids)>=total: break
        if not result['data']:raise AssertionError('empty intermediate page')
        offset+=len(result['data'])
    if len(ids)!=len(set(ids)):raise AssertionError('duplicate result IDs')
    return sorted(ids)


def start_api(binary):
    listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1];listener.close()
    process=subprocess.Popen([str(binary)],env={**os.environ,'DATABASE_URL':DB,'BACKEND_ADDR':f'127.0.0.1:{port}'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    deadline=time.monotonic()+15
    while True:
        if process.poll() is not None:raise RuntimeError('backend exited during startup')
        try:
            with urlopen(base+'/health',timeout=.5) as reply:
                assert json.load(reply)['db']=='ok'
            return process,base
        except OSError:
            if time.monotonic()>deadline: process.terminate();raise TimeoutError('backend startup')
            time.sleep(.005)


def stop(process):
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait()


def quality(ids, data, period):
    expected=set(data['expected'][period]);actual=set(ids)
    excluded={c['id'] for c in data['clients'] if c['excluded']}
    hits=len(expected&actual)
    return {'count':len(ids),'precision':hits/len(actual) if actual else 0,'recall':hits/len(expected),
            'excluded_errors':len(actual&excluded),'exact_match':actual==expected,
            'ids_sha256':hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds',type=int,default=5)
    parser.add_argument('--out',type=Path,default=ROOT/'reports/h00/automated.json')
    parser.add_argument('--soffice',default='soffice')
    args=parser.parse_args()
    if not DB or not args.rounds>0:parser.error('H00_BENCH_DATABASE_URL and positive rounds required')
    api=ROOT/'scripts/h00/rehub-api';fixture=ROOT/'scripts/h00/h00-fixture'
    result={'started_at':datetime.now(timezone.utc).isoformat(),'kind':'automated_software_experiment',
      'human_participants':0,'business_hypothesis_confirmed':False,
      'environment':{'platform':platform.platform(),'cpu_count':os.cpu_count(),'calc':subprocess.check_output([args.soffice,'--version'],text=True).strip()},
      'method':{'cold':'application start + list output + application shutdown; PostgreSQL already running',
       'warm':'running Go API + JSON read + CSV output','warmup_rounds':1,'rounds':args.rounds,
       'not_measured':['administrator actions','manual Excel work','frontend usability','user learning','Microsoft Excel engine']},'datasets':[]}
    with tempfile.TemporaryDirectory(prefix='rehub-h00-') as temp:
        work=Path(temp)
        for size in (30,4000):
            source=ROOT/f'contracts/testing/h00/data-{size}.json';data=json.loads(source.read_text())
            book=ROOT/f'contracts/testing/h00/selection-{size}.xlsx';check_book(book,data)
            subprocess.run([str(fixture),str(source)],check=True,env=os.environ,stdout=subprocess.DEVNULL)
            trials=[]
            for round_no in range(args.rounds+1):
                order=('calc','rehub') if round_no%2==0 else ('rehub','calc')
                for tool in order:
                    directory=work/f'{size}-{round_no}-{tool}';directory.mkdir()
                    process=None;started=time.perf_counter()
                    try:
                        if tool=='calc':
                            subprocess.run([args.soffice,f'-env:UserInstallation={(directory/"profile").as_uri()}','--headless','--convert-to','csv','--outdir',str(directory),str(book)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
                            with (directory/f'selection-{size}.csv').open(encoding='utf-8',newline='') as file:
                                rows=list(csv.reader(file));ids=sorted(r[9] for r in rows[1:] if len(r)>9 and r[9])
                        else:
                            process,base=start_api(api);ids=get_ids(base)
                        save_ids(directory/'result-ids.csv',ids)
                    finally:
                        if process is not None:stop(process)
                    seconds=time.perf_counter()-started
                    score=quality(ids,data,'2026Q3')
                    if not score['exact_match']:raise AssertionError((size,tool,score,ids,data['expected']['2026Q3']))
                    trials.append({'round':round_no,'warmup':round_no==0,'tool':tool,'seconds':seconds,**score})
            process,base=start_api(api)
            try:
                q2=get_ids(base,'2026Q2');assert quality(q2,data,'2026Q2')['exact_match']
                warm=[]
                for n in range(args.rounds):
                    started=time.perf_counter();ids=get_ids(base);save_ids(work/f'warm-{size}-{n}.csv',ids)
                    warm.append(time.perf_counter()-started)
            finally:stop(process)
            medians={tool:statistics.median(t['seconds'] for t in trials if t['tool']==tool and not t['warmup']) for tool in ('calc','rehub')}
            result['datasets'].append({'clients':size,'period_rows':len(data['rows']),
              'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'workbook_sha256':hashlib.sha256(book.read_bytes()).hexdigest(),
              'trials':trials,'cold_median_seconds':medians,'cold_ratio_calc_to_rehub':medians['calc']/medians['rehub'],
              'warm_api_seconds':warm,'warm_api_median_seconds':statistics.median(warm),'q2_exact_match':True})
            print(json.dumps({k:v for k,v in result['datasets'][-1].items() if k not in ('trials','warm_api_seconds')},ensure_ascii=False),flush=True)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
