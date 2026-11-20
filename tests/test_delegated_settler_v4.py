import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_settler_v4 import first_swap
class SettlerV4Test(unittest.TestCase):
 def test_prediction_matches_actual_callback(self):
  plans=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions']
  executions=json.loads(Path('reports/amm/delegated-settler-callback.json').read_text())['cases']
  for p,e in zip(plans,executions):
   self.assertEqual(p['tx'],e['tx']['tx'])
   r=first_swap(p['plan']['actions'][0]['data']);calls=e['result']['calls']
   self.assertEqual(len(calls),1);self.assertEqual(calls[0]['data'],r['swap_calldata'])
   self.assertEqual(r['amount'],p['plan']['amount'])
   self.assertEqual((r['currency0'],r['fee'],r['spacing'],r['zero']),('0x'+'00'*20,0,200,False))
 def test_unverified_path_flags_rejected(self):
  p=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions'][0]['plan']['actions'][0]['data']
  b=bytearray.fromhex(p[2:]);b[4+416+23]=2
  with self.assertRaises(ValueError):first_swap('0x'+b.hex())
 def test_upstream_output_reaches_recorded_v3_input(self):
  e=json.loads(Path('reports/amm/delegated-settler-wrapped-1000000000000000.json').read_text())
  self.assertEqual(len(e['cases']),2)
  for c in e['cases']:
   self.assertTrue(c['synthetic_native_funding']);r=c['result'];self.assertIsNone(r['error'])
   self.assertEqual(len(r['calls']),1);call=r['calls'][0]
   self.assertEqual(call['to'],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca')
   self.assertEqual(call['data'][:10],'0x128acb08');d=bytes.fromhex(call['data'][10:])
   self.assertEqual(int.from_bytes(d[32:64],'big'),1)
   self.assertEqual(int.from_bytes(d[64:96],'big',signed=True),c['synthetic_output']-1)
   selectors=[a['data'][:10] for stage in c['stages'] for a in stage['calls']]
   for selector in ('0xa5841194','0x15dacbea','0x23b872dd','0x11da60b4','0xd0e30db0','0x70a08231','0x128acb08'):
    self.assertIn(selector,selectors)
