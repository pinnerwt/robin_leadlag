import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_batch_route import inspect,router_payload
from delegated_batch_envelope import inspect as envelope
class BatchRouteTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.pools=json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']
  cls.txs=[t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['data'].startswith('0xc3c16ee4')]
 def test_raw_transactions_match_executed_nested_payloads(self):
  evidence=json.loads(Path('reports/amm/delegated-batch-full-credit.json').read_text())['cases']
  for t,e in zip(self.txs,evidence):
   p=inspect(t['data'],self.pools)
   self.assertEqual(t['tx'],e['tx']['tx']);self.assertEqual(p['router']['payload'],e['result']['calls'][0]['data'])
   self.assertEqual(p['v4']['amount'],p['router']['amount'])
   self.assertEqual(p['v3']['pool'],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca')
   self.assertFalse(p['scope_verified']);self.assertFalse(p['execution_complete'])
 def test_inconsistent_approval_rejected(self):
  raw=self.txs[0]['data'];approval=envelope(raw)['calls'][0]['data'];changed=approval[:-2]+'01'
  self.assertNotEqual(approval,changed)
  with self.assertRaisesRegex(ValueError,'approval mismatch'):inspect(raw.replace(approval[2:],changed[2:],1),self.pools)
 def test_router_alias_and_trailer_rejected(self):
  data=envelope(self.txs[0]['data'])['calls'][1]['data'];b=bytearray.fromhex(data[2:])
  b[4+256:4+288]=(288).to_bytes(32,'big')
  for bad in ('0x'+b.hex(),data+'00',data[:-2]):
   with self.assertRaises(ValueError):router_payload(bad)
 def test_unknown_wrap_action_rejected(self):
  raw=self.txs[0]['data'];p=inspect(raw,self.pools);wrap=p['holder']['actions'][1]['data'];changed=wrap.replace('d0e30db0','ffffffff')
  with self.assertRaisesRegex(ValueError,'wrap action'):inspect(raw.replace(wrap[2:],changed[2:],1),self.pools)
