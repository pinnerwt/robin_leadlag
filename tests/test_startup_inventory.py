import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_startup_inventory import prepare
class StartupInventory(unittest.TestCase):
 def test_recent_callers_expand_domain_without_future_leak(self):
  router='0x'+'11'*20;a='0x'+'22'*20;b='0x'+'33'*20
  training={'complete':True,'training_tip':{'number':'0x8'},'accounts':{}}
  base=[dict(router=router,mapping_slot=4,key_addresses=[],implementation_code_hash='old')]
  rows=[dict(kind='feed_tx',sequence=s,**{'from':who,'to':router}) for s,who in [(9,a),(10,b)]]
  actors,profiles=prepare({'number':'0xa'},training,base,[],map(json.dumps,rows))
  self.assertEqual(profiles[0]['key_addresses'],[a]);self.assertNotIn(b,{r['from'] for r in actors})
 def test_nested_horizon_rebased_and_proxy_pin_preserved(self):
  router='0x'+'11'*20;t={'complete':True,'training_tip':{'number':'0x8'},'accounts':{}}
  base=[dict(router=router,mapping_slot=4,implementation_slot='0x1',implementation_code_hash='impl',nested_indices=[1],key_addresses=[router])]
  _,p=prepare({'number':'0xa'},t,base,[dict(router=router,mapping_slot=4,implementation_code_hash='proxy')],[],2)
  self.assertEqual(p[0]['nested_indices'],[11,12]);self.assertEqual(p[0]['implementation_code_hash'],'impl');self.assertEqual(base[0]['nested_indices'],[1])
 def test_future_training_rejected(self):
  with self.assertRaises(ValueError):prepare({'number':'0xa'},{'complete':True,'training_tip':{'number':'0xa'}},[],[],[])
