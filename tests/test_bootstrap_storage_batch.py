import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bootstrap_storage import read_slots,MULTICALL
class StorageBatch(unittest.TestCase):
 def test_out_of_gas_splits_same_anchor_without_dropping_accounts(self):
  addresses=['0x'+i.to_bytes(20,'big').hex() for i in (1000,1001)];sizes=[]
  def rpc(method,params):
   calls,block,_=params;self.assertEqual(block,'0x99');sizes.append(len(calls))
   if len(calls)>1:raise RuntimeError('out of gas')
   return [(True,'0x'+(7).to_bytes(32,'big').hex())]
  with patch('bootstrap_storage.aggregate',side_effect=lambda calls:calls),patch('bootstrap_storage.split',side_effect=lambda result:result):out=read_slots(rpc,'0x99',{a:[0] for a in addresses})
  self.assertEqual(sizes,[2,1,1]);self.assertEqual(out,{a:{'0x0':'0x7'} for a in addresses})
 def test_multicall_storage_does_not_replace_aggregate_entrypoint(self):
  def rpc(method,params):
   call,block,overrides=params
   self.assertEqual(call['to'],MULTICALL);self.assertEqual(block,'0x99')
   self.assertEqual(call['data'],'0x'+(1).to_bytes(32,'big').hex())
   self.assertIn(MULTICALL,overrides)
   return '0x'+(123).to_bytes(32,'big').hex()
  self.assertEqual(read_slots(rpc,'0x99',{MULTICALL:[1]}),{MULTICALL:{'0x1':'0x7b'}})
 def test_many_short_accounts_preserve_every_result(self):
  requests={'0x'+i.to_bytes(20,'big').hex():list(range(32)) for i in range(1000,1130)};batches=[]
  def rpc(method,params):
   calls,block,overrides=params;self.assertEqual(block,'0x99');self.assertEqual(method,'eth_call');batches.append(calls)
   self.assertLessEqual(sum((len(c['data'])-2)//64 for c in calls),4096)
   return [(True,'0x'+''.join((int(c['to'],16)+int(c['data'][j:j+64],16)).to_bytes(32,'big').hex() for j in range(2,len(c['data']),64))) for c in calls]
  with patch('bootstrap_storage.aggregate',side_effect=lambda calls:calls),patch('bootstrap_storage.split',side_effect=lambda result:result):out=read_slots(rpc,'0x99',requests)
  self.assertEqual(sorted(len(b) for b in batches),[2,128])
  for address,keys in requests.items():self.assertEqual(out[address],{hex(k):hex(int(address,16)+k) for k in keys})
if __name__=='__main__':unittest.main()
