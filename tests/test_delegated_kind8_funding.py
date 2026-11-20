import json,unittest
from pathlib import Path
class KindEightFundingTest(unittest.TestCase):
 def test_input_tracks_prefunded_recipient_balance(self):
  target='0x5d2806b9af9e9f740b55eda02a8484af5805803a'
  for amount in (123456789,987654321):
   e=json.loads(Path('reports/amm/delegated-kind8-funded-'+str(amount)+'.json').read_text())
   first=e['stages'][0]['calls'][0];self.assertEqual(first['data'][:10],'0x128acb08')
   d=bytes.fromhex(first['data'][10:]);self.assertEqual(int.from_bytes(d[:32],'big'),int(target,16))
   call=e['result']['calls'][0];self.assertEqual(call['to'],target);self.assertEqual(call['data'][:10],'0x9908fc8b')
   d=bytes.fromhex(call['data'][10:]);w=lambda i:int.from_bytes(d[32*i:32*(i+1)],'big')
   self.assertEqual(len(d),192);self.assertEqual(w(2),amount);self.assertEqual(w(3),1)
   self.assertEqual(w(4),int(e['tx']['to'],16))
   self.assertEqual(w(0),int('5fc5360d0400a0fd4f2af552add042d716f1d168',16))
   self.assertEqual(w(1),int('0bd7d308f8e1639fab988df18a8011f41eacad73',16))
 def test_checkpoint_inactive_pair_reverts(self):
  e=json.loads(Path('reports/amm/delegated-kind8-funded-987654321.json').read_text())
  r=e['continuations'][-1]
  returns=r['execution_returns'];gate=next(x for x in returns if x['to']=='0x135a93116097ec2a3a0892686fbd3f1b37753d78' and x['selector']=='0x22f3e2d4')
  self.assertEqual(gate['result'],'Return');self.assertEqual(int(gate['output'],16),0)
  swap=next(x for x in returns if x['selector']=='0x9908fc8b')
  self.assertEqual(swap['result'],'Revert')
  d=bytes.fromhex(swap['output'][10:]);length=int.from_bytes(d[32:64],'big')
  self.assertEqual(d[64:64+length],b'inactive pair')
 def test_active_intervention_transfers_input_then_calls_resolved_pool(self):
  e=json.loads(Path('reports/amm/delegated-kind8-funded-987654321-active.json').read_text())
  self.assertTrue(e['synthetic_active']);pool='0x72e46c9edf828002fdbfdd0952419790576c0f18'
  transfer=e['active_probe']['calls'][0];self.assertEqual(transfer['data'][:10],'0xa9059cbb')
  d=bytes.fromhex(transfer['data'][10:]);self.assertEqual(int.from_bytes(d[:32],'big'),int(pool,16))
  self.assertEqual(int.from_bytes(d[32:],'big'),987654321)
  call=e['transfer_probe']['calls'][0];self.assertEqual(call['to'],pool);self.assertEqual(call['data'][:10],'0x7c6c84af')
  d=bytes.fromhex(call['data'][10:]);w=lambda i:int.from_bytes(d[i*32:(i+1)*32],'big')
  self.assertEqual(len(d),192);self.assertEqual(w(3),987654321);self.assertEqual(w(4),1)
  self.assertEqual(w(2),int(e['tx']['to'],16));self.assertEqual(w(5),int(e['tx']['to'],16))
