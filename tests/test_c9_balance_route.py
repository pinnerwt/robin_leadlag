import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from c9_balance_route import plan,resolve_callback,preview

class C9BalanceRouteTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.fixture=json.loads(Path('tests/fixtures/c9_balance_route.json').read_text())
  cls.aqua=json.loads(Path('tests/fixtures/aqua_program.json').read_text())
 def test_four_bytecode_callbacks(self):
  for case in self.fixture['cases']:
   route=plan(case['calldata'])
   self.assertEqual(route,case['route'])
   self.assertEqual(resolve_callback(route,case['callback_balance'],self.fixture['pools']),case['expected'])
 def test_unknown_layout_and_modes_rejected(self):
  original=bytearray.fromhex(self.fixture['cases'][0]['calldata'][2:])
  for offset,value in [(4+4*32,0),(4+224,2),(4+1088+64+5*32,9999),(4+1088+64+6*32,100)]:
   raw=original.copy();raw[offset:offset+32]=value.to_bytes(32,'big')
   with self.assertRaises(ValueError):plan(raw)
  with self.assertRaises(ValueError):plan(original[:-1])
 def test_unrecorded_callback_and_invalid_balance(self):
  r=self.fixture['cases'][0]['route']
  self.assertEqual(resolve_callback(r,10**18,{}),[])
  for balance in [-1,1<<256]:
   with self.assertRaises(ValueError):resolve_callback(r,balance,self.fixture['pools'])
 def test_preview_preserves_inventory_and_uses_aqua_price(self):
  for case in self.fixture['cases']:
   r=case['route']
   a=next(a for a in self.aqua if a['amount']==r['amount'] and a['token_in']==r['token_in'])
   for inventory in [0,123456789]:
    p=preview(case['calldata'],a['balance_in'],a['balance_out'],inventory,self.fixture['pools'])
    self.assertEqual(p['quote'],a['expected'])
    self.assertEqual(p['operations'][0]['amount'],a['expected']['amount_out']+inventory)
    self.assertFalse(p['state_complete'])
if __name__=='__main__':unittest.main()
