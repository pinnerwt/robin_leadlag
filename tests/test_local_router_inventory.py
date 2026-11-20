import json,sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from read_local_router_inventory import inventory_at,ROUTERS,TOKENS
class InventoryTest(unittest.TestCase):
 def setUp(self):self.r=json.loads(Path('reports/amm/router-inventory-checkpoint.json').read_text())
 def test_verified_local_balances(self):
  self.assertEqual(inventory_at(self.r,ROUTERS[0],self.r['anchor_hash'],TOKENS),dict.fromkeys(TOKENS,0))
  self.assertEqual(inventory_at(self.r,ROUTERS[1],self.r['anchor_hash'],TOKENS)[TOKENS[1]],229937)
  for e in self.r['entries']:
   self.assertTrue(e['result']['execution_success']);self.assertFalse(e['result']['calls'])
   self.assertEqual(int(e['balance']),int(e['result']['output'],16))
 def test_mismatched_anchor_rejected(self):
  with self.assertRaises(ValueError):inventory_at(self.r,ROUTERS[0],'wrong',TOKENS)
 def test_missing_value_never_zero_filled(self):
  self.r['entries'][0].pop('balance')
  with self.assertRaises(ValueError):inventory_at(self.r,ROUTERS[0],self.r['anchor_hash'],TOKENS)
if __name__=='__main__':unittest.main()
