import json,unittest
from pathlib import Path
class WrapperHookTest(unittest.TestCase):
 def test_fixed_anchor_before_swap_result(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-hook-initialized-probe.json').read_text())
  self.assertTrue(e['anchor_verified']);self.assertIsNone(e['error']);self.assertEqual(len(e['reads']),6)
  for read in e['reads']:self.assertEqual(e['seed']['accounts'][read['address']]['storage'][read['slot']],read['value'])
  r=e['stages'][-1];self.assertIsNone(r['error']);self.assertTrue(r['execution_success'])
  self.assertEqual(r['calls'],[]);self.assertEqual(r['storage_writes'],[])
  raw=bytes.fromhex(r['output'][2:]);self.assertEqual(len(raw),96)
  self.assertEqual(raw[:32],bytes.fromhex('575e24b4')+bytes(28))
  self.assertEqual(int.from_bytes(raw[32:64],'big'),0)
  self.assertEqual(int.from_bytes(raw[64:],'big'),0x400000)
 def test_same_sender_six_direction_size_cases(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-hook-variants.json').read_text())
  self.assertEqual(len(e['cases']),6)
  for case in e['cases']:
   r=case['result'];self.assertIsNone(r['error']);self.assertTrue(r['execution_success'])
   self.assertEqual(int(r['output'][-64:],16),0x400000);self.assertEqual(r['storage_writes'],[])
 def test_sender_profile_change_requires_more_pool_state(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-hook-sender-disabled.json').read_text())
  self.assertEqual(e['synthetic_value'],0)
  self.assertIn('unknown slot',e['result']['error'])
  self.assertIn('2819640e4320c0bbbd13d85ac4defd79491d4586544071e535f0c4108ad186de',e['result']['error'])
 def test_non_exempt_branch_replays_locally(self):
  import sys
  sys.path.insert(0,str(Path('scripts').resolve()))
  from probe_delegated_kind8 import run
  e=json.loads(Path('reports/amm/delegated-wrapper-hook-sender-disabled-initialized.json').read_text())
  self.assertTrue(e['anchor_verified']);self.assertIsNone(e['error'])
  self.assertTrue(e['synthetic_sender_disabled'])
  self.assertEqual(len(e['reads']),6)
  for read in e['reads']:
   self.assertEqual(e['seed']['accounts'][read['address']]['storage'][read['slot']],read['value'])
  r=run(e['seed'],e['tx'])
  self.assertIsNone(r['error']);self.assertTrue(r['execution_success'])
  self.assertEqual(r['output'],e['stages'][-1]['output'])
  self.assertEqual(int(r['output'][-64:],16),0x400000|450)
  self.assertEqual(r['calls'],[]);self.assertEqual(r['storage_writes'],[])
 def test_non_exempt_direction_and_amount_cases(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-hook-sender-disabled-variants.json').read_text())
  self.assertTrue(e['synthetic_sender_disabled']);self.assertEqual(len(e['cases']),6)
  for case in e['cases']:
   r=case['result'];self.assertIsNone(r['error']);self.assertTrue(r['execution_success'])
   self.assertEqual(int(r['output'][-64:],16),0x400000|450)
   self.assertEqual(r['calls'],[]);self.assertEqual(r['storage_writes'],[])
