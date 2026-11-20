import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_settler_v3 import intent
class SettlerV3Test(unittest.TestCase):
 def test_intent_matches_actual_swap_fields(self):
  plans=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions']
  pools=json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']
  e=json.loads(Path('reports/amm/delegated-settler-wrapped-1000000000000000.json').read_text())['cases']
  for plan,case in zip(plans,e):
   p=intent(plan['plan']['actions'][2]['data'],case['synthetic_output'],pools)
   call=case['result']['calls'][0];d=bytes.fromhex(call['data'][10:])
   self.assertEqual(p['pool'],call['to']);self.assertEqual(int(p['recipient'],16),int.from_bytes(d[:32],'big'))
   self.assertEqual(p['zero'],bool(int.from_bytes(d[32:64],'big')))
   self.assertEqual(p['amount'],int.from_bytes(d[64:96],'big',signed=True))
   self.assertEqual(p['limit'],int.from_bytes(d[96:128],'big'))
 def test_unknown_profile_and_ambiguous_pool_rejected(self):
  action=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions'][0]['plan']['actions'][2]['data']
  pools=json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']
  for balance,ps in [(1,pools),(100,[]),(100,pools+pools)]:
   with self.assertRaises(ValueError):intent(action,balance,ps)
 def test_curve_derived_output_matches_second_trace(self):
  c=json.loads(Path('reports/amm/delegated-settler-chain-preview.json').read_text())
  e=json.loads(Path('reports/amm/delegated-settler-wrapped-'+str(c['v4_net'])+'.json').read_text())['cases']
  actual=next(x for x in e if x['tx']['tx']==c['tx'])['result']['calls'][0]
  self.assertEqual(actual['to'],c['v3_intent']['pool'])
  d=bytes.fromhex(actual['data'][10:])
  self.assertEqual(int.from_bytes(d[64:96],'big',signed=True),c['v3_intent']['amount'])
  self.assertEqual(c['v3_intent']['amount'],c['v4_net']-1)
  self.assertEqual(c['v3_fill']['amount0'],c['v3_intent']['amount'])
  self.assertEqual(c['v3_fill']['unfilled'],0)
