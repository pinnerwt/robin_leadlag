import json,sys,unittest,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bootstrap_aqua import refresh_aqua
class BootstrapAquaTest(unittest.TestCase):
 def setUp(self):
  self.template=json.loads(Path('config/aqua-template.json').read_text());self.anchor=dict(number='0x123',hash='anchor');self.calls=[]
 def rpc(self,method,params):
  self.calls.append((method,params))
  if method=='eth_getBlockByNumber':return dict(hash='anchor')
  if method=='eth_getStorageAt':return '0x'+((2<<248)|12345).to_bytes(32,'big').hex()
  return '0x'+(999).to_bytes(32,'big').hex()
 def test_all_reads_pinned_and_complete(self):
  result=refresh_aqua(self.template,self.anchor,self.rpc)
  self.assertEqual(result['anchor_hash'],'anchor')
  self.assertEqual(len(result['strategies'][0]['balances']),2)
  self.assertTrue(all(int(v)==999 for v in result['router_inventory'].values()))
  for method,params in self.calls:
   self.assertEqual(params[0] if method=='eth_getBlockByNumber' else params[-1],'0x123')
 def test_reorg_and_missing_storage_fail(self):
  def bad(method,params):
   if method=='eth_getBlockByNumber':return dict(hash='changed')
   return self.rpc(method,params)
  with self.assertRaisesRegex(ValueError,'anchor changed'):refresh_aqua(self.template,self.anchor,bad)
  with self.assertRaisesRegex(ValueError,'uint256'):refresh_aqua(self.template,self.anchor,lambda *_:'0x')
 def test_cancellation(self):
  event=threading.Event();event.set()
  with self.assertRaisesRegex(RuntimeError,'cancelled'):refresh_aqua(self.template,self.anchor,self.rpc,event)
  self.assertFalse(self.calls)
if __name__=='__main__':unittest.main()
