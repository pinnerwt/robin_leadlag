import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from bootstrap_router7627_token import capture,TOKEN,IMPLEMENTATION

class TokenBootstrapTest(unittest.TestCase):
 def fake(self,changed=False,missing=False):
  calls=[];checks=0
  def rpc(method,args):
   nonlocal checks
   calls.append((method,args))
   self.assertEqual(args[0] if method=='eth_getBlockByNumber' else args[-1],'0x123')
   if method=='eth_getBlockByNumber':
    checks+=1
    return dict(hash='changed' if changed and checks==2 else 'anchor')
   if method=='eth_getStorageAt':return '0x1234' if args[1]==IMPLEMENTATION else '0x99'
   if method=='eth_getCode':return '0x' if missing else '0x6000'
   if method in ('eth_getBalance','eth_getTransactionCount'):return '0x1'
   raise AssertionError(method)
  return rpc,calls
 def test_all_reads_pinned_and_balance_kept(self):
  rpc,calls=self.fake();r=capture(rpc,dict(number='0x123',hash='anchor'))
  self.assertEqual(len(calls),12);self.assertEqual(len(r['accounts'][TOKEN]['storage']),4);self.assertFalse(r['complete']);self.assertEqual(r['implementation'],'0x'+'0'*36+'1234')
  self.assertEqual(set(r['accounts'][TOKEN]['storage'].values()),{'0x99','0x1234'})
 def test_reorg_rejected(self):
  rpc,_=self.fake(changed=True)
  with self.assertRaisesRegex(ValueError,'anchor mismatch'):capture(rpc,dict(number='0x123',hash='anchor'))
 def test_missing_code_rejected(self):
  rpc,_=self.fake(missing=True)
  with self.assertRaisesRegex(ValueError,'missing token'):capture(rpc,dict(number='0x123',hash='anchor'))
