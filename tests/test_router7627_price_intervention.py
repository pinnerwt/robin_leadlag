import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_price_intervention import shift_no_crossing
from v3_state import State,sqrt_tick
class PriceInterventionTest(unittest.TestCase):
 def test_no_crossing_and_rejections(self):
  s=State(sqrt_tick(10),10,1000,40,1,{0:0},{})
  packed=(123<<184)|(10<<160)|s.sqrt
  value=shift_no_crossing(s,sqrt_tick(12),packed)
  self.assertEqual(value>>184,123);self.assertEqual((value>>160)&((1<<24)-1),12)
  s.bitmap[0]=1<<11
  with self.assertRaisesRegex(ValueError,'initialized tick'):shift_no_crossing(s,sqrt_tick(12),packed)
  s.bitmap={}
  with self.assertRaisesRegex(ValueError,'missing bitmap'):shift_no_crossing(s,sqrt_tick(12),packed)
 def test_shift_reaches_v3_payment(self):
  p=Path('reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4-transient-actual-take-deposit-seed-inventory-sync-usdg-balance-usdg-pay-usd-4548949483-settled-actual-inv-state-shift.json')
  for row in json.loads(p.read_text())['cases']:
   r=row['result'];self.assertIsNone(r['error']);self.assertTrue(row['synthetic_v4_state_shift'])
   v4=next(c for c in r['execution_returns'] if c['selector']=='0xf3cd914c' and c['result']=='Return');credit=int.from_bytes(bytes.fromhex(v4['output'][2:])[:16],'big',signed=True)
   callback=next(c for c in r['execution_calls'] if c['data'].startswith('0xfa461e33'));owed=int(callback['data'][10:74],16)
   self.assertGreaterEqual(credit-owed,7500000000000)
   c=r['calls'][0];self.assertEqual(c['to'],'0x0bd7d308f8e1639fab988df18a8011f41eacad73');self.assertEqual(c['data'],'0xa9059cbb'+int('52e65b17fb6e5ba00ed806f37afcd2daa50271ca',16).to_bytes(32,'big').hex()+owed.to_bytes(32,'big').hex());self.assertFalse(r['execution_success'])
