import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_conditions import evaluate,score
class ConditionTest(unittest.TestCase):
 def verify(self,name):
  report=json.loads(Path('reports/amm/delegated-condition-'+name+'-probe.json').read_text());plan=report['plan']
  for case in report['cases']:
   groups=copy.deepcopy(plan['condition_groups']);threshold=case.get('threshold_override')
   if threshold is not None:groups[0]['prefix']=threshold.to_bytes(8,'big').hex()
   prices=iter(case['prices']);returns={(r['target'],r['calldata']):next(prices).to_bytes(32,'big') for g in groups for r in g['records']}
   result=case['result'];self.assertIsNone(result['error'])
   expected=[s['input_amount'] for s,g in zip(plan['strategies'],groups) if evaluate(g,returns)['passes']]
   self.assertTrue(all(c['data'].startswith('0x0b0d9c09') for c in result['calls']))
   self.assertEqual(expected,[int(c['data'][-64:],16) for c in result['calls']])
   # Compare each weighted score with the original EVM MUL operands and SAR32.
   traces=[m for m in result['math_ops'] if m['pc']==0x1d58]
   records=[r for g in groups for r in g['records']];self.assertEqual(len(traces),len(records))
   for r,m in zip(records,traces):
    product=int(m['a'])*int(m['b'])% (1<<256)
    if product>>255:product-=1<<256
    self.assertEqual(score(r,returns[(r['target'],r['calldata'])]),product>>32)
 def test_price_interventions(self):self.verify('score')
 def test_threshold_equality(self):self.verify('boundary')
