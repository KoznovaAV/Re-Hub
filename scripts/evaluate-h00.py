"""Расчёт H-00 по журналу двух администраторов. Не создаёт пользовательские замеры."""
import argparse
import json
import math
from statistics import median


def evaluate(payload):
    kind = payload.get('data_kind', 'measured')
    if kind not in ('measured', 'simulated', 'agent_observed'):
        raise ValueError('data_kind: measured, simulated или agent_observed')
    gold, runs = payload['gold'], payload['runs']
    if len(gold) != 2 or len(runs) != 4:
        raise ValueError('Нужны два набора и четыре прохода')
    all_ids = set()
    for item in gold.values():
        ids, expected, excluded = set(item['all_ids']), set(item['expected']), set(item['excluded'])
        if len(item['all_ids']) != 15 or len(ids) != 15 or ids & all_ids:
            raise ValueError('Нужны непересекающиеся наборы по 15 клиентов')
        if not expected or expected & excluded or not (expected | excluded) <= ids or (kind == 'measured' and not item.get('approved_by')):
            raise ValueError('Нужен согласованный эталон без противоречий')
        all_ids |= ids
    participants = {r['participant'] for r in runs}
    if len(participants) != 2:
        raise ValueError('Нужны два администратора')
    for person in participants:
        own = [r for r in runs if r['participant'] == person]
        if len(own) != 2 or {r['tool'] for r in own} != {'excel','rehub'} or {r['group'] for r in own} != set(gold):
            raise ValueError('Каждый участник проходит оба инструмента на разных наборах')
    if len({(r['tool'],r['group']) for r in runs}) != 4:
        raise ValueError('Нужно чередовать наборы и инструменты')
    scores = []
    for run in runs:
        seconds = run['seconds']
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Недопустимое время')
        item = gold[run['group']]
        ids, expected = set(run['ids']), set(item['expected'])
        if len(ids) != len(run['ids']) or not ids <= set(item['all_ids']):
            raise ValueError('Повторные или неизвестные ID')
        hits = len(ids & expected)
        scores.append({**run,'precision':hits/len(ids) if ids else 0,'recall':hits/len(expected),
                       'excluded_errors':len(ids & set(item['excluded'])),
                       'false_positive_ids':sorted(ids-expected), 'missed_ids':sorted(expected-ids),
                       'false_exclusions':len(expected-ids)})
    times = {tool:median(s['seconds'] for s in scores if s['tool']==tool) for tool in ('excel','rehub')}
    quality = all(s['precision'] >= .8 and s['recall'] >= .9 and not s['excluded_errors'] for s in scores if s['tool']=='rehub')
    speedup = times['excel']/times['rehub']
    criteria_met = quality and speedup >= 2
    return {'hypothesis':'H-00','data_kind':kind,
            'human_participants':len(participants) if kind == 'measured' else 0,
            'speedup':speedup,'median_seconds':times,'quality_passed':quality,
            'criteria_met':criteria_met,
            'confirmed':criteria_met and kind == 'measured',
            'conclusion':('Учебные смоделированные данные: не подтверждают работу реальных пользователей.'
                          if kind == 'simulated' else 'Фактический прогон агента: не подтверждает скорость работы людей.' if kind == 'agent_observed' else 'Критерии пилота выполнены.' if criteria_met else 'Критерии пилота не выполнены.'),
            'runs':scores}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('measurements')
    args = parser.parse_args()
    try:
        with open(args.measurements,encoding='utf-8') as source:
            print(json.dumps(evaluate(json.load(source)),ensure_ascii=False,indent=2))
    except (ValueError,KeyError,TypeError) as exc:
        parser.exit(2,f'Нельзя оценить пилот: {exc}\n')
