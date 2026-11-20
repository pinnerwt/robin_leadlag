import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bootstrap_accounts import read_accounts

class AccountBootstrap(unittest.TestCase):
 def test_tracer_omission_requires_explicit_same_block_metadata(self):
  address='0x'+'0'*39+'8';calls=[]
  class Source:
   def trace(self,request,block):
    self.block=block
    return {}
   def rpc(self,method,params):
    calls.append((method,params))
    return {'eth_getCode':'0x','eth_getBalance':'0x123','eth_getTransactionCount':'0x2'}[method]
  with patch('bootstrap_accounts.selector',return_value='0x4d2301cc'):
   result=read_accounts(Source(),'0x1234',[address])
  self.assertEqual(result[address],{'code':'0x','balance':'0x123','nonce':2})
  self.assertEqual(len(calls),3)
  self.assertTrue(all(params==[address,'0x1234'] for _,params in calls))

if __name__=='__main__':unittest.main()
