import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from variant_external_curve import sell
class ExternalCurveTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p=json.loads(Path('reports/amm/variant-external-output.json').read_text());cls.s=cls.p['seed']['accounts'][cls.p['tx']['to']]['storage']
 def test_actual_code_outputs_and_writes(self):
  for c in json.loads(Path('reports/amm/variant-external-sizes.json').read_text())['cases']:
   r=c['result'];self.assertTrue(r['execution_success']);local=sell(self.s,c['amount']);self.assertEqual(local['output'],int(r['output'],16))
   actual={w['slot']:int(w['value'],16) for w in r['storage_writes']}
   self.assertEqual({k:int(v,16) for k,v in local['writes'].items()},actual)
 def test_original_size_fails_current_reserve(self):
  self.assertFalse(self.p['result']['execution_success'])
  a=int(self.p['tx']['data'][10:74],16)
  with self.assertRaisesRegex(ValueError,'underflow'):sell(self.s,a)
 def test_unknown_branch_and_missing_state_reject(self):
  s=dict(self.s);s.pop('0x6')
  with self.assertRaises(ValueError):sell(s,10**18)
  s=dict(self.s);s['0x1']=hex(int(s['0x1'],16)|(1<<160))
  with self.assertRaises(ValueError):sell(s,10**18)
