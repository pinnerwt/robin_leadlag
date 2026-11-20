import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_first_swap import intent
class FirstSwapTest(unittest.TestCase):
 def test_actual_three_inventory_interventions(self):
  r=json.loads(Path('reports/amm/router0480-inventory.json').read_text());p=intent(r['tx']['data'])
  for row in r['cases']:
   c=row['result']['calls'][0];d=bytes.fromhex(c['data'][10:]);self.assertEqual(c['to'],p['pool']);self.assertEqual(p['recipient'],'0x'+d[12:32].hex());self.assertEqual(p['amount'],int.from_bytes(d[64:96],'big',signed=True));self.assertEqual(p['zero'],bool(int.from_bytes(d[32:64],'big')));self.assertEqual(p['limit'],int.from_bytes(d[96:128],'big'))
  self.assertTrue(p['callback_unresolved']);self.assertFalse(p['scope_verified'])
 def test_reject_unverified_mode(self):
  r=json.loads(Path('reports/amm/router0480-inventory.json').read_text());raw=bytearray.fromhex(r['tx']['data'][2:]);raw[286]=2
  with self.assertRaises(ValueError):intent('0x'+raw.hex())
 def test_actual_callback_second_swap_is_fixed_input(self):
  r=json.loads(Path('reports/amm/router0480-callback.json').read_text());p=intent(r['tx']['data'],command_index=4)
  for row in r['cases']:
   self.assertTrue(row['getter_replays'][0]['result']['execution_success'])
   c=row['result']['calls'][0];d=bytes.fromhex(c['data'][10:]);self.assertEqual(p['pool'],c['to']);self.assertEqual(p['recipient'],'0x'+d[12:32].hex());self.assertEqual(p['amount'],int.from_bytes(d[64:96],'big',signed=True));self.assertEqual(p['zero'],bool(int.from_bytes(d[32:64],'big')));self.assertEqual(p['limit'],int.from_bytes(d[96:128],'big'))
  self.assertEqual(p['amount'],23561586807130800128)
 def test_nested_third_swap_and_payment_order(self):
  from router0480_payments import intents
  r=json.loads(Path('reports/amm/router0480-nested-paid.json').read_text())
  self.assertEqual(len(r['synthetic_registrations']),2)
  for i,s in enumerate(r['swaps'],3):
   p=intent(r['tx']['data'],command_index=i);c=s['call'];d=bytes.fromhex(c['data'][10:]);self.assertEqual(p['pool'],c['to']);self.assertEqual(p['amount'],int.from_bytes(d[64:96],'big',signed=True));self.assertEqual(p['zero'],bool(int.from_bytes(d[32:64],'big')));self.assertEqual(p['limit'],int.from_bytes(d[96:128],'big'))
  transfers=intents(r['tx']['data']);self.assertEqual(len(transfers),3)
  for p,c in zip(transfers,r['synthetic_transfers']):self.assertEqual(p['token'],c['to']);self.assertEqual(p['data'],c['data'])
  baseline=json.loads(Path('reports/amm/router0480-nested.json').read_text());self.assertIn('unknown slot',baseline['result']['error']);self.assertEqual(baseline['synthetic_registrations'],[])
 def test_direction_and_callback_profile_prefixes(self):
  r=json.loads(Path('reports/amm/router0480-swap-profiles.json').read_text());self.assertEqual(len(r['cases']),8)
  for row in r['cases']:
   p=intent(row['tx']['data']);self.assertIsNone(row['result']['error']);self.assertEqual(len(row['result']['calls']),1);c=row['result']['calls'][0];d=bytes.fromhex(c['data'][10:])
   self.assertEqual(c['data'][:10],'0x128acb08');self.assertEqual(p['pool'],c['to']);self.assertEqual(p['amount'],int.from_bytes(d[64:96],'big',signed=True));self.assertEqual(p['zero'],bool(int.from_bytes(d[32:64],'big')));self.assertEqual(p['limit'],int.from_bytes(d[96:128],'big'));self.assertEqual(p['callback_profile'],row['profile'])
