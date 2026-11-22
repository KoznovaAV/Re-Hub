import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('evaluation',Path(__file__).parents[1]/'evaluate-h00.py')
evaluation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
class PilotTest(unittest.TestCase):
    def data(self):
        gold={g:{'all_ids':[f'{g}{i}' for i in range(15)],'expected':[f'{g}0'],'excluded':[f'{g}1'],'approved_by':'expert'} for g in ('A','B')}
        runs=[{'participant':p,'tool':t,'group':g,'seconds':sec,'ids':[f'{g}0']} for p,t,g,sec in [('one','excel','A',100),('one','rehub','B',40),('two','rehub','A',40),('two','excel','B',100)]]
        return {'gold':gold,'runs':runs}
    def test_speed_alone_does_not_confirm(self):
        d=self.data();d['runs'][1]['ids'].append('B1');r=evaluation.evaluate(d);self.assertGreater(r['speedup'],2);self.assertFalse(r['confirmed'])
    def test_quality_without_speed_does_not_confirm(self):
        d=self.data();d['runs'][1]['seconds']=100;self.assertFalse(evaluation.evaluate(d)['confirmed'])
    def test_complete_pilot(self): self.assertTrue(evaluation.evaluate(self.data())['confirmed'])
    def test_no_expert_no_conclusion(self):
        d=self.data();d['gold']['A']['approved_by']=''
        with self.assertRaises(ValueError):evaluation.evaluate(d)
    def test_single_person_is_not_pilot(self):
        d=self.data();d['runs']=d['runs'][:2]
        with self.assertRaises(ValueError):evaluation.evaluate(d)
    def test_simulation_cannot_confirm_a_user_pilot(self):
        d=self.data();d['data_kind']='simulated'
        for g in d['gold'].values():g['approved_by']=None
        result=evaluation.evaluate(d)
        self.assertTrue(result['criteria_met'])
        self.assertFalse(result['confirmed'])
        self.assertEqual(result['human_participants'],0)
    def test_unknown_data_kind_is_rejected(self):
        d=self.data();d['data_kind']='assumed_real'
        with self.assertRaises(ValueError):evaluation.evaluate(d)

    def test_missed_candidates_are_reported(self):
        d=self.data()
        run=next(r for r in d['runs'] if r['tool']=='rehub')
        missed=run['ids'].pop()
        result=evaluation.evaluate(d)
        score=next(r for r in result['runs'] if r['tool']=='rehub' and r['participant']==run['participant'])
        self.assertIn(missed,score['missed_ids'])
        self.assertEqual(score['false_exclusions'],1)

    def test_observed_agent_run_never_confirms_human_speed(self):
        d=self.data();d['data_kind']='agent_observed'
        result=evaluation.evaluate(d)
        self.assertEqual(result['human_participants'],0)
        self.assertFalse(result['confirmed'])
        self.assertTrue(result['criteria_met'])
