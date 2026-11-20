import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_two_pool_route import inspect
from router0480_0d import intent
from bootstrap_state import hashhex,word
class TwoPoolTest(unittest.TestCase):
 def cases(self):return json.loads(Path('reports/amm/router0480-other-swaps.json').read_text())['cases']
 def test_two_original_routes(self):
  for r in self.cases():
   if r['opcode']!=10:continue
   p=inspect(r['original_tx']['data']);self.assertEqual(p['block_guard']['block_number'],r['original_tx']['sequence']);self.assertIn('0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca',p['pools']);self.assertFalse(p['execution_complete'])
 def test_payment_corruption(self):
  r=self.cases()[0];raw=bytearray.fromhex(r['original_tx']['data'][2:]);o=int.from_bytes(raw[12:14],'big');raw[o+5:o+7]=bytes(2)
  with self.assertRaises(ValueError):inspect('0x'+raw.hex())
 def test_real_manager_callback_swap(self):
  r=next(r for r in self.cases() if r['opcode']==13);p=intent(r['original_tx']['data'],r['offset'],r['stop']);trace=json.loads(Path('reports/amm/router0480-0d-manager.json').read_text());self.assertIsNone(trace['result']['error']);c=trace['result']['calls'][0];self.assertEqual(p['data'],c['data']);self.assertEqual(p['manager'],c['to']);self.assertEqual(p['pool_id'],hashhex(b''.join(word(v) for v in (int(p['currency0'],16),int(p['currency1'],16),p['config']))))
 def test_unverified0d_direction_rejected(self):
  r=next(r for r in self.cases() if r['opcode']==13);raw=bytearray.fromhex(r['original_tx']['data'][2:]);raw[r['offset']+1]=1
  with self.assertRaises(ValueError):intent('0x'+raw.hex(),r['offset'],r['stop'])
