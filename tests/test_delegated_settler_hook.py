import json,unittest
from pathlib import Path
class SettlerHookTest(unittest.TestCase):
 def test_first_pool_missing_state_stays_unknown(self):
  c=json.loads(Path('reports/amm/delegated-settler-hook.json').read_text())['cases'][0]
  self.assertIn('unknown slot',c['result']['error'])
  self.assertEqual(c['result']['calls'],[])
 def test_second_pool_take_and_after_swap_delta_match(self):
  before=json.loads(Path('reports/amm/delegated-settler-hook.json').read_text())['cases'][1]
  after=json.loads(Path('reports/amm/delegated-settler-hook-take-success.json').read_text())['cases'][1]
  call=before['result']['calls'][0];d=bytes.fromhex(call['data'][10:])
  self.assertEqual(call['data'][:10],'0x0b0d9c09')
  self.assertEqual(int.from_bytes(d[:32],'big'),0)
  fee=int.from_bytes(d[64:96],'big');self.assertEqual(fee,28500000000000)
  self.assertEqual(fee*10000,before['synthetic_output']*285)
  r=after['result'];self.assertIsNone(r['error']);self.assertTrue(r['execution_success'])
  self.assertEqual(r['output'],'0x'+('b47b2fb1'+'00'*28)+fee.to_bytes(32,'big').hex())
  self.assertEqual(r['calls'],[]);self.assertEqual(len(r['storage_writes']),2)
