import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from settler_funding_action import inspect
class BatchVariantsTest(unittest.TestCase):
 def test_funding_action_matches_actual_holder_call(self):
  p=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions'][0]['plan']
  r=json.loads(Path('reports/amm/batch-variant-prefixes.json').read_text())['cases'][0]['result']
  a=inspect(p['actions'][0]['data'],'0x5399d94d2cab7c252a6034042e1917a0e5e17a18')
  self.assertEqual(a['holder_transfer'],r['calls'][0]['data']);self.assertEqual(a['amount'],p['amount'])
 def test_new_v3_pool_metadata_is_explicitly_synthetic(self):
  baseline=json.loads(Path('reports/amm/batch-variant-prefixes.json').read_text())['cases'][1]
  extended=json.loads(Path('reports/amm/batch-variant-continuation.json').read_text())['cases'][1]
  self.assertIn('unknown account',baseline['result']['error']);self.assertFalse(extended['entry_code_verified'])
  pool='0xf55045c021949b202a5d10451b2ffa01561c5f55'
  self.assertEqual(extended['synthetic_accounts'],[pool])
  call=extended['result']['calls'][0];self.assertEqual(call['to'],pool);self.assertEqual(call['data'][:10],'0x128acb08')
  p=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions'][1]['plan']
  d=bytes.fromhex(call['data'][10:]);self.assertEqual(int.from_bytes(d[64:96],'big',signed=True),p['amount'])
 def test_external_action_matches_executed_prefix(self):
  from settler_external_action import intent
  c=json.loads(Path('reports/amm/settler-variant-actions.json').read_text())['cases'][0]
  balance=next(m['value'] for m in c['synthetic_inputs'] if m['kind']=='getter' and m['call']['data'].startswith('0x70a08231'))
  decoded=intent(c['action']['data'],balance);call=c['result']['calls'][0]
  self.assertEqual(decoded['target'],call['to']);self.assertEqual(decoded['data'],call['data']);self.assertFalse(decoded['scope_verified'])
  with self.assertRaises(ValueError):intent(c['action']['data']+'00',balance)
 def test_both_downstream_profiles_match_actual_settler(self):
  from delegated_settler_v3 import intent
  pools=json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']
  rows=json.loads(Path('reports/amm/settler-variant-actions.json').read_text())['cases'][1:]
  for c in rows:
   decoded=intent(c['action']['data'],10**15,pools);call=c['result']['calls'][0];d=bytes.fromhex(call['data'][10:])
   self.assertEqual(decoded['pool'],call['to']);self.assertEqual(decoded['amount'],int.from_bytes(d[64:96],'big',signed=True));self.assertEqual(decoded['limit'],int.from_bytes(d[96:128],'big'))
   self.assertEqual(decoded['zero'],bool(int.from_bytes(d[32:64],'big')))
