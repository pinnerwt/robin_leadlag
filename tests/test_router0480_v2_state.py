import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_v2_state import transition
class V2StateTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=json.loads(Path('reports/amm/router0480-v2-curve.json').read_text());s=json.loads(Path('captures/startup-v9-dependencies.json').read_text());cls.s=s['accounts'][cls.r['tx']['to']]['storage']
 def test_actual_pair_writes(self):
  r=self.r;self.assertTrue(r['result']['execution_success']);p=r['plan'];out=[p['amount0_out'],p['amount1_out']];local=transition(self.s,out,r['balances'],r['tx']['timestamp']);actual={w['slot']:int(w['value'],16) for w in r['result']['storage_writes']}
  self.assertEqual({k:int(v,16) for k,v in local['writes'].items()},actual);self.assertEqual(local['inputs'],[p['input_amount'],0])
 def test_underpayment_rejects(self):
  r=self.r;p=r['plan'];bal=[r['reserves'][0],r['balances'][1]]
  with self.assertRaises(ValueError):transition(self.s,[p['amount0_out'],p['amount1_out']],bal,r['tx']['timestamp'])
 def test_actual_invariant_payment_boundary(self):
  b=json.loads(Path('reports/amm/router0480-v2-invariant-boundary.json').read_text());self.assertEqual([x['success'] for x in b['cases']],[False,True])
  for case in b['cases']:
   r=json.loads(Path(case['artifact']).read_text());p=r['plan'];outputs=[p['amount0_out'],p['amount1_out']]
   if case['success']:transition(self.s,outputs,r['balances'],r['tx']['timestamp'])
   else:
    with self.assertRaisesRegex(ValueError,'invariant'):transition(self.s,outputs,r['balances'],r['tx']['timestamp'])
