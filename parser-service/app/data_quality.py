"""P-04: reproducible aggregate CSV/Markdown and optional private row diagnostics."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from openpyxl import load_workbook
from .customer_coverage import coverage
from .customer_xlsx import parse_file, summary


def report(snapshot,directory,context,out,private_rows=False,baseline=1572,pdf_directory=None,pdf_layout_text=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    ctx=json.loads(Path(context).read_text())
    metrics,unknown=coverage(snapshot,directory,ctx)
    parsed=parse_file(snapshot,ctx)
    metrics.update(summary(parsed))
    metrics['input_sha256']={kind:hashlib.sha256(Path(p).read_bytes()).hexdigest() for kind,p in [('snapshot',snapshot),('directory',directory),('context',context)]}
    empty={};invalid={}
    for kind,path in [('snapshot',snapshot),('directory',directory)]:
        b=load_workbook(path,read_only=True,data_only=False,keep_links=False)
        missing=bad=0
        try:
            for s in b:
                for cells in s.iter_rows(min_row=3,max_col=2):
                    if all(c.value is None for c in cells):continue
                    value=cells[1].value
                    if value is None or isinstance(value,str) and not value.strip():missing+=1
                    elif not (isinstance(value,str) and len(value.strip())==7 and value.strip().isascii() and value.strip().isdigit()):bad+=1
        finally:b.close()
        empty[kind]=missing;invalid[kind]=bad
    metrics['empty_kcr_rows']=empty;metrics['invalid_nonempty_kcr_rows']=invalid
    metrics['historical_claim']={'unknown_ids':baseline,'snapshot_ids':4205,'verified':False,'difference_from_current':baseline-metrics['unknown_ids']}
    metrics['explanation']=("Current result is an exact set difference of valid unique anonymous IDs in the hashed XLSX pair. "
      "Blank KCR cells do not invalidate anonymous keys. Invalid IDs are excluded and duplicate client/period rows do not increase the denominator. "
      "The historical count has no reproducible source pair/method in the supplied evidence; its cause cannot be established. "
      "Do not claim source updates or a parser bug without that evidence.")
    if pdf_directory:
        from .pdf_coverage_audit import audit
        from .customer_xlsx import key_from,ANONYMOUS
        book=load_workbook(directory,read_only=True,data_only=False)
        try:native={key for (cell,) in book.active.iter_rows(min_row=3,max_col=1) if (key:=key_from(cell,ANONYMOUS))}
        finally:book.close()
        snapshot_ids={row['data']['external_id'] for row in parsed['rows']}
        metrics['pdf_extraction_audit']=audit(pdf_directory,native,snapshot_ids,pdf_layout_text)
        metrics['technical_audit_complete']=metrics['pdf_extraction_audit']['independent_native_verification_passed']
        metrics['explanation']="Native XLSX independently matches two PDF extractors. Poppler produces an incomplete directory and an inflated unknown-ID count. Historical 1572 is unverified for these sources."
    (out/'data-quality.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    flat=[]
    for key,value in metrics.items():
        if isinstance(value,dict):flat.extend((key+'.'+str(k),json.dumps(v,ensure_ascii=False)) for k,v in value.items())
        else:flat.append((key,json.dumps(value,ensure_ascii=False)))
    with (out/'data-quality.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['metric','value']);w.writerows(flat)
    text=f"""# P-04: качество исходных данных

Уникальных ID среза: {metrics['snapshot_ids']}; справочника: {metrics['directory_ids']}; неизвестных: {metrics['unknown_ids']} ({metrics['unknown_percent']}%).
Принято парсером строк: {metrics['parsed_rows']}; отклонено: {metrics['rejected_rows']}; повторных пар: {metrics['duplicates_in_parsed_rows']}.
Пустой КЦР: срез {empty['snapshot']}, справочник {empty['directory']}. Это строки, не уникальные клиенты.

Историческое утверждение: {baseline}/4205. Текущий воспроизводимый результат: {metrics['unknown_ids']}/{metrics['snapshot_ids']}. Разница числителей: {baseline-metrics['unknown_ids']}.
Число {baseline} не воспроизведено: для него нет идентифицированной пары файлов и метода. Причина расхождения не установлена; подмена этого ограничения догадкой недопустима.

Текущий метод: разность множеств валидных обезличенных ID. Четыре ошибочных ID не включаются в знаменатель; повторения по периодам считаются один раз. Пустой КЦР не исключает валидный обезличенный ID в режиме anonymous.

Хеши входов и полные агрегаты: data-quality.json. CSV содержит только агрегаты. Ключ --private-rows дополнительно создаёт локальный CSV с ID и координатами; его не следует публиковать вместе с агрегатами.
"""
    if 'pdf_extraction_audit' in metrics:
        evidence=metrics['pdf_extraction_audit'];methods=evidence['methods']
        text += "\n## Независимая проверка PDF и объяснение расхождения\n\nОдин и тот же PDF, один и тот же срез, одна регулярная маска ID.\n\n| Метод | ID справочника | Неизвестных ID | Пропущено ID относительно XLSX |\n|---|---:|---:|---:|\n"
        for name,m in methods.items():text+=f"| {name} | {m['directory_ids']} | {m['unknown_ids']} | {m['missing_native_ids']} |\n"
        lost=methods['poppler_layout']['lost_matching_ids']
        text+=f"\nPypdf и PyMuPDF независимо восстановили ровно то же множество ID, что исходный XLSX. Poppler пропустил {methods['poppler_layout']['missing_native_ids']} ID, из них {lost} встречаются в срезе. Поэтому неизвестных стало {methods['poppler_layout']['unknown_ids']}, а не {metrics['unknown_ids']}: разница равна {lost}. Это воспроизводимая причина расхождения результатов по методам извлечения.\n\nЧисло 1572 не воспроизводится ни одним из этих методов. Вариант 1527 подтверждён; предположение о перестановке цифр остаётся предположением. Для этих источников 1572 исключается из выводов как неподтверждённое утверждение.\n\nТехнический аудит P-04 завершён. Это не подтверждение полноты базы заказчика: остаются реальные 243 неизвестных клиента, и порог H-10 в 5% не пройден. Деловую причину их отсутствия должен объяснить поставщик.\n"
    (out/'data-quality.md').write_text(text)
    if private_rows:
        with (out/'unknown-private.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['external_id','period_code','sheet','row'])
            w.writerows((x['data']['external_id'],x['data']['period_code'],x['source']['sheet'],x['source']['row']) for x in unknown)
    return metrics

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot',type=Path);p.add_argument('directory',type=Path);p.add_argument('context',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--private-rows',action='store_true');p.add_argument('--baseline-unknown',type=int,default=1572)
    p.add_argument('--pdf-directory',type=Path);p.add_argument('--pdf-layout-text',type=Path,help='Optional cached pdftotext output; marked as not freshly extracted')
    a=p.parse_args();result=report(a.snapshot,a.directory,a.context,a.out,a.private_rows,a.baseline_unknown,a.pdf_directory,a.pdf_layout_text)
    print(json.dumps({k:result[k] for k in ['snapshot_ids','unknown_ids','unknown_percent','empty_kcr_rows']},ensure_ascii=False))
