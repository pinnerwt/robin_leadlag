import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from join_initialization import join
class JoinInitialization(unittest.TestCase):
 def test_same_anchor_numeric_formats_and_conflict_rejection(self):
  q=dict(quote_state_complete=True,anchor={'hash':'a','number':'0x1'},accounts={'0x11':{'nonce':1,'storage':{'0x0001':'0x0002'}}})
  d=dict(anchor=q['anchor'],accounts={'0x11':{'nonce':'0x1','storage':{'0x1':'0x2'}}},hydration={})
  result=join(q,d);self.assertEqual(result['accounts']['0x11']['storage'],{'0x1':'0x2'});self.assertFalse(result['execution_state_complete'])
  bad=copy.deepcopy(d);bad['anchor']['hash']='b'
  with self.assertRaises(ValueError):join(q,bad)
  bad=copy.deepcopy(d);bad['accounts']['0x11']['storage']['0x1']='0x3'
  with self.assertRaises(ValueError):join(q,bad)
