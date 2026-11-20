import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from discover_feed_actors import discover
class FeedActors(unittest.TestCase):
 def test_native_deposit_accounts_are_initialization_dependencies(self):
  a='0x'+'12'*20;b='0x'+'34'*20
  row=dict(kind='feed_system_tx',system_kind='eth_deposit',sequence=9,**{'from':a,'to':b})
  self.assertEqual({x['from_address'] for x in discover([json.dumps(row)],10)},{a,b})
 def test_strict_causal_cutoff_and_dedup(self):
  a='0x'+'ab'*20;b='0x'+'cd'*20;c='0x'+'ef'*20
  rows=[dict(kind='feed_tx',sequence=8,**{'from':a.upper().replace('0X','0x'),'to':b}),dict(kind='feed_tx',sequence=9,**{'from':a,'to':None}),dict(kind='feed_tx',sequence=10,**{'from':c,'to':a})]
  out=discover(map(json.dumps,rows),10)
  self.assertEqual(out,[dict(from_address=a,sequence=9),dict(from_address=b,sequence=8)])
 def test_invalid_address_rejected(self):
  with self.assertRaises(ValueError):discover([json.dumps(dict(kind='feed_tx',sequence=1,**{'from':'bad'}))],2)
