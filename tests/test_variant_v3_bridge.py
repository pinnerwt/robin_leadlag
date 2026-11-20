import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from preview_variant_v3_bridge import inputs
from variant_v3_bridge import preview
class BridgeTest(unittest.TestCase):
 def test_two_pool_state_commit_without_mutating_inputs(self):
  a,b,k,actual=inputs();before=copy.deepcopy(k);r=preview(a,b,**k)
  self.assertEqual(k,before);self.assertEqual(r['weth_balance'],1)
  for name,row in zip(('upstream','downstream'),actual):
   d=bytes.fromhex(row['result']['output'][2:]);fill=r[name+'_fill'];self.assertEqual([fill['amount0'],fill['amount1']],[int.from_bytes(d[i:i+32],'big',signed=True) for i in (0,32)])
   self.assertEqual(r[name].sqrt,fill['sqrt']);self.assertNotEqual(r[name].sqrt,k[name].sqrt)
 def test_anchor_mismatch_rejects(self):
  a,b,k,_=inputs();k['anchors']['inventory']='other'
  with self.assertRaisesRegex(ValueError,'anchor'):preview(a,b,**k)
 def test_missing_downstream_bitmap_is_atomic(self):
  a,b,k,_=inputs();k['downstream'].bitmap={};before=copy.deepcopy(k)
  with self.assertRaisesRegex(ValueError,'bitmap'):preview(a,b,**k)
  self.assertEqual(k,before)
 def test_inventory_changes_next_leg_size(self):
  a,b,k,_=inputs();zero=preview(a,b,**k);k['weth_balance']=1;one=preview(a,b,**k)
  self.assertEqual(one['next']['amount'],zero['next']['amount']+1)
