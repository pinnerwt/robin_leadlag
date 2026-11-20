import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bootstrap_proxies import IMPLEMENTATION,hydrate_proxies,push_constants

class ProxyBootstrap(unittest.TestCase):
 def test_constant_inside_push_data_is_not_an_opcode(self):
  raw=b'\x7f'+b'\x7f'+IMPLEMENTATION.to_bytes(32,'big')[:31]
  self.assertNotIn(IMPLEMENTATION,push_constants('0x'+raw.hex()))
 def test_pointer_and_code_share_anchor_and_follow_references(self):
  proxy='0x'+'11'*20;impl='0x'+'22'*20
  accounts={proxy:{'code':'0x7f'+IMPLEMENTATION.to_bytes(32,'big').hex()+'5400'}}
  calls=[]
  class Source:
   def rpc(self,*args):raise AssertionError('unexpected RPC')
  def slots(rpc,block,requests):
   calls.append(block);self.assertEqual(requests,{proxy:[IMPLEMENTATION]})
   return {proxy:{hex(IMPLEMENTATION):impl}}
  def metadata(source,block,addresses):
   calls.append(block);self.assertEqual(addresses,{impl});return {impl:{'code':'0x00','nonce':1,'balance':'0x0'}}
  with patch('bootstrap_proxies.read_slots',side_effect=slots),patch('bootstrap_proxies.read_accounts',side_effect=metadata):
   refs=hydrate_proxies(Source(),'0x123',accounts)
  self.assertEqual(calls,['0x123','0x123']);self.assertEqual(refs[0]['target'],impl)
  self.assertEqual(accounts[proxy]['storage'][hex(IMPLEMENTATION)],impl)
  self.assertEqual(accounts[impl]['code'],'0x00')

if __name__=='__main__':unittest.main()
