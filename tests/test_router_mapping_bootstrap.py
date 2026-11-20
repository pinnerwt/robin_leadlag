import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_router_mappings import add_mapping_keys
class RouterMappings(unittest.TestCase):
 def test_captured_nested_slot_matches_execution_preimage(self):
  request={'addresses':['0x7615926023bb149f36095645c2a81dc367d39750'],'slot':4,'nested_indices':[114612448]}
  out=subprocess.check_output([str(ROOT/'target/release/examples/address_mapping_keys')],input=json.dumps(request).encode())
  self.assertEqual(json.loads(out),['0x329fcbb6e7b501dbbd16744bdde6da151f85cca067e5f30e9f809115f23aa3e4'])
 def test_captured_caller_slot_matches_numeric_missing_key(self):
  out=subprocess.check_output([str(ROOT/'target/release/examples/address_mapping_keys')],input=json.dumps({'addresses':['0xfa491cff06b997baa538af350facf513db55b7e0'],'slot':0}).encode())
  self.assertEqual(int(json.loads(out)[0],16),int('de7599566d3352b9c0965d38d4fed85909cfe1f59b1020e8f90ae7a8e3b26d3',16))
 def test_changed_implementation_rejected_before_mapping_queries(self):
  router='0x'+'11'*20;impl='0x'+'22'*20;accounts={router:{'code':'0x00'},impl:{'code':'0x01'}};keys={}
  class Source:rpc=None
  profile=[dict(router=router,implementation_slot='0x1',implementation_code_hash='old',mapping_slot=0)]
  with tempfile.NamedTemporaryFile(mode='w') as f:
   json.dump(profile,f);f.flush()
   with patch('bootstrap_router_mappings.read_slots',return_value={router:{'0x1':impl}}),patch('bootstrap_router_mappings.hashhex',return_value='new'):
    with self.assertRaisesRegex(ValueError,'implementation changed'):add_mapping_keys(Source(),'0x1',accounts,keys,f.name)
  self.assertEqual(keys,{})
