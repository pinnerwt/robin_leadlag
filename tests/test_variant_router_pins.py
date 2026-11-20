import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from initialize_batch_bridge import validate_router_pins,ROUTER_PINS
class VariantRouterPinsTest(unittest.TestCase):
 def test_latest_code_matches_both_entry_chains(self):
  r=json.loads(Path('reports/amm/variant-router-pins-latest.json').read_text());self.assertTrue(r['anchor_verified'])
  for entry in r['checks']:
   self.assertIsNone(entry['error']);self.assertEqual(validate_router_pins(r['seed'],entry['target']),entry['target'])
 def test_new_code_anchor_is_distinct_from_curve_anchor(self):
  r=json.loads(Path('reports/amm/variant-router-pins-latest.json').read_text());old=json.loads(Path('reports/amm/variant-v3-settled.json').read_text());self.assertNotEqual(r['seed']['anchor']['hash'],old['seed']['anchor']['hash'])
 def test_each_nested_code_mutation_rejects(self):
  r=json.loads(Path('reports/amm/variant-router-pins-latest.json').read_text())
  for address in ROUTER_PINS:
   s=copy.deepcopy(r['seed']);s['accounts'][address]['code']='0x00'
   with self.assertRaises(ValueError):validate_router_pins(s,r['checks'][0]['target'])
