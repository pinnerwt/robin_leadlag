"""Saved actual-bytecode interventions, not historical execution parity."""
import json
from pathlib import Path
import unittest

class DelegatedFundingTest(unittest.TestCase):
 def load(self,name):
  return json.loads(Path('reports/amm/delegated-router-funded-'+name+'.json').read_text())
 def swap(self,r,pool):
  self.assertIsNone(r['result']['error']);self.assertEqual(len(r['result']['calls']),1)
  c=r['result']['calls'][0];self.assertEqual(c['to'],pool);self.assertEqual(c['data'][:10],'0x128acb08')
  d=bytes.fromhex(c['data'][10:]);self.assertEqual(int.from_bytes(d[32:64],'big'),1)
  self.assertEqual(int.from_bytes(d[96:128],'big'),4295128740)
  return int.from_bytes(d[64:96],'big',signed=True)
 def test_first_input_tracks_native_take_not_initial_spcx_balance(self):
  for n in (0,10**30):
   r=self.load('balance-'+str(n));take=bytes.fromhex(r['take']['data'][10:])
   self.assertEqual(int.from_bytes(take[:32],'big'),0)
   self.assertEqual(self.swap(r,'0xc3c9f0171490ef0f4536fe493f3b0ebb5ee0cb5e'),int.from_bytes(take[64:96],'big'))
 def test_second_input_tracks_spcx_balance_delta(self):
  for name,expected in [('output-1000000000000000000',10**18),('output-12345678901234567890',12345678901234567890),('delta-2000000000000000000',2*10**18)]:
   r=self.load(name)
   self.assertEqual(self.swap(r,'0xc61284332117c3fb23a2a56cceffd07f7af60029'),expected)
  # This intervention holds swap return output fixed but changes measured balance.
  self.assertEqual(r['synthetic_v3_output'],10**18)
  self.assertEqual(r['synthetic_balance_delta'],2*10**18)
