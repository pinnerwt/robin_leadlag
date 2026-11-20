"""Integration checks against built decode_feed. Build release examples first."""
import json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class NitroContinuity(unittest.TestCase):
 def test_real_eth_deposit_is_explicit_system_transaction(self):
  import base64
  row=json.loads((ROOT/'tests/fixtures/nitro_eth_deposit.json').read_text());p=self.run_decode(row)
  self.assertEqual(p.returncode,0,p.stderr);marker,tx=map(json.loads,p.stdout.splitlines())
  msg=row['payload']['messages'][0]['message']['message'];raw=base64.b64decode(msg['l2Msg'])
  self.assertEqual(marker['transaction_count'],1);self.assertEqual(tx['system_kind'],'eth_deposit')
  self.assertEqual(tx['to'],'0x65c340eb0688d8f8b64e9c6d580f312a97b615d8')
  self.assertEqual(int(tx['value'],16),int.from_bytes(raw[20:],'big'))
  self.assertEqual(tx['l1_request_id'],msg['header']['requestId'])
  self.assertEqual(tx['from'],msg['header']['sender'])
  chain=json.loads((ROOT/'captures/eth-deposit-chain-transaction.json').read_text())
  self.assertEqual(tx['tx'],chain['hash']);self.assertEqual(int(tx['value'],16),int(chain['value'],16))
  self.assertEqual(tx['block_hash'].lower(),chain['blockHash'].lower());self.assertTrue(tx['raw_transaction'].startswith('0x64'))
  del msg['header']['requestId'];p=self.run_decode(row)
  self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')
 def test_truncated_deposit_stops_before_block_marker(self):
  import base64
  row=json.loads((ROOT/'tests/fixtures/nitro_eth_deposit.json').read_text());msg=row['payload']['messages'][0]['message']['message']
  msg['l2Msg']=base64.b64encode(base64.b64decode(msg['l2Msg'])[:-1]).decode()
  p=self.run_decode(row);self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')
 def test_batch_report_preserves_system_transaction(self):
  item=json.loads((ROOT/'captures/batch-report-message.json').read_text())
  row={'kind':'nitro_push','payload':{'messages':[item]},'recv_ns':123,'mono_ns':456}
  p=self.run_decode(row);self.assertEqual(p.returncode,0,p.stderr)
  marker,report=map(json.loads,p.stdout.splitlines())
  self.assertEqual(marker['transaction_count'],1);self.assertEqual(report['kind'],'feed_system_tx')
  self.assertEqual(report['sequence'],114521223)
  self.assertEqual((report['calldata_length'],report['calldata_nonzeros']),(137,116))
  self.assertEqual(report['batch_poster'],'0xdaa526086787d9debe1d7f3ffdb1fe50cf8687f4')
  del item['message']['message']['batchDataTokens']
  p=self.run_decode(row);self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')
 def test_confirmation_does_not_advance_execution(self):
  row={'kind':'nitro_push','payload':{'version':1,'confirmedSequenceNumberMessage':{'sequenceNumber':114518303}},'recv_ns':123,'mono_ns':456}
  p=self.run_decode(row);self.assertEqual(p.returncode,0,p.stderr)
  self.assertEqual(json.loads(p.stdout),dict(kind='feed_confirmation',sequence=114518303,recv_ns=123,mono_ns=456))
  row['payload']['unexpected_state_update']={}
  p=self.run_decode(row);self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')
 def run_decode(self,row):
  return subprocess.run([str(ROOT/'target/release/examples/decode_feed'),'--with-raw'],input=json.dumps(row)+'\n',text=True,capture_output=True)
 def test_real_multi_message_order_and_envelope(self):
  row=json.loads((ROOT/'tests/fixtures/nitro_two_messages.json').read_text());p=self.run_decode(row);self.assertEqual(p.returncode,0,p.stderr)
  active=None;markers=[];txs=0
  for r in map(json.loads,p.stdout.splitlines()):
   if r['kind']=='feed_block':active=r['sequence'];markers.append(active)
   else:
    txs+=1;self.assertEqual(r['sequence'],active)
    for key in ('gas_limit','nonce','value','raw_transaction','max_fee_per_gas'):self.assertIn(key,r)
  self.assertEqual(len(markers),2);self.assertGreater(txs,0)
 def test_unknown_kind_stops_before_marker(self):
  row=json.loads((ROOT/'tests/fixtures/nitro_two_messages.json').read_text());row['payload']['messages']=row['payload']['messages'][:1];row['payload']['messages'][0]['message']['message']['header']['kind']=999
  p=self.run_decode(row);self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'');self.assertIn('unsupported L1 message',p.stderr)
