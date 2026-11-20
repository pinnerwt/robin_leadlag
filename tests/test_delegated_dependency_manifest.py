import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_dependency_manifest import inventory,FEE,HELPER
class DependencyManifestTest(unittest.TestCase):
 def test_saved_inventory_exposes_actual_missing_state(self):
  r=json.loads(Path('reports/amm/delegated-initialization-manifest.json').read_text())
  self.assertFalse(r['complete']);self.assertEqual(len(r['pools']),2)
  keys={(k['address'],k['slot']):k for k in r['keys']}
  self.assertEqual(len(keys),len(r['keys']))
  self.assertFalse(keys[('0x05afb8e895e77ce70f79056137ea606b05bf5abd','0x393')]['present'])
  self.assertEqual(sum(not k['present'] for k in r['keys']),r['missing'])
  caches=[k for k in r['keys'] if k['address']==FEE and 'fee cache at requested block' in k['reasons']]
  self.assertEqual(len(caches),2);self.assertTrue(all(not k['present'] for k in caches))
  profiles=[k for k in r['keys'] if k['address']==HELPER and 'caller/origin discount' in k['reasons']]
  self.assertEqual(len(profiles),1);self.assertFalse(profiles[0]['present'])
 def test_missing_core_does_not_invent_observation_keys(self):
  pool='0x'+'11'*20
  seed={'anchor':{'hash':'anchor'},'accounts':{pool:{'code':'0x363d3d373d3d3d363d731642634c8cb1c9f1b84c9a1a08534f8c3f4e89f85af43d82803e903d91602b57fd5bf3','storage':{}}}}
  r=inventory(seed,{'actions':[{'target':pool}]},caller=pool,origin=pool,block=1)
  self.assertFalse(any('observation ring' in k['reasons'] for k in r['keys']))
  self.assertTrue(r['unresolved']);self.assertFalse(r['complete'])
 def test_unknown_profile_includes_both_pool_discount_keys(self):
  from bootstrap_state import mapping
  r=json.loads(Path('reports/amm/delegated-initialization-manifest.json').read_text())
  actor='0x111bac94814e496abc36dc3594ef4f8c43bbc5b2'
  base=int(mapping(int(actor,16),2),16)
  expected={hex(int(mapping(int(pool,16),base+1),16)) for pool in r['pools']}
  actual={k['slot'] for k in r['keys'] if k['address']==HELPER and 'pool-specific caller/origin discount' in k['reasons']}
  self.assertEqual(actual,expected)
  self.assertFalse(any('discount keys' in x['reason'] for x in r['unresolved']))
