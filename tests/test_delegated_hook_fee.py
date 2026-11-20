import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_hook_fee import native_output_fee
class HookFeeTest(unittest.TestCase):
 def test_independent_config_interventions_match_actual_hook(self):
  e=json.loads(Path('reports/amm/delegated-hook-fee-fields.json').read_text())
  for case in e['cases']:
   expected=native_output_fee(int(case['synthetic_value'],16),10**15)
   self.assertIsNone(case['result']['error'])
   self.assertEqual(expected['fee'],int(case['result']['calls'][0]['data'][-64:],16))
 def test_rounding_cases_match_actual_hook(self):
  e=json.loads(Path('reports/amm/delegated-hook-fee-fields.json').read_text())
  for c in e['rounding']:
   r=c['result'];self.assertIsNone(r['error']);expected=native_output_fee(int(e['original'],16),c['output'])
   observed=int(r['calls'][0]['data'][-64:],16) if r['calls'] else int(r['output'][-64:],16)
   self.assertEqual(expected['fee'],observed)
  self.assertEqual(native_output_fee(int(e['original'],16),36)['fee'],0)
  self.assertEqual(36*285//10000,1)
 def test_accounting_matches_actual_hook_writes(self):
  from delegated_hook_fee import accounting_update
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
  hook='0xe5e702641ea86f4ae6cc3cdaed2b886f976be044';storage={k:int(v,16) for k,v in seed['accounts'][hook]['storage'].items()}
  config=int(json.loads(Path('reports/amm/delegated-hook-fee-fields.json').read_text())['original'],16)
  slots=dict(slot12='0x7d9da416064311c52905749fc2e2253769a4ef0a700f9df5505314d47e438344',slot13='0xcbfc8ba749ea0d1f842b889602c17bbc9a25c2796be533bbd5ff944db981610d')
  for path,gross in [('delegated-settler-hook-take-success.json',10**15),('delegated-settler-curve.json',820349038648306)]:
   actual=json.loads(Path('reports/amm/'+path).read_text())['cases'][1]['result']['storage_writes']
   expected={w['slot']:int(w['value'],16) for w in actual if w['address']==hook}
   before=storage.copy();r=accounting_update(storage,config,gross,**slots)
   self.assertEqual(r['writes'],expected);self.assertEqual(storage,before)
 def test_accounting_missing_overflow_and_zero_fee(self):
  from delegated_hook_fee import accounting_update
  config=(185<<160)|(100<<208);slots=dict(slot12='a',slot13='b')
  for storage in ({'a':0},{'a':0,'b':(1<<256)-1}):
   before=storage.copy()
   with self.assertRaises(ValueError):accounting_update(storage,config,10**15,**slots)
   self.assertEqual(storage,before)
  self.assertEqual(accounting_update({},config,36,**slots)['writes'],{})
