import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_batch_envelope import inspect

class BatchEnvelopeTest(unittest.TestCase):
 def setUp(self):
  self.txs=[t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['data'].startswith('0xc3c16ee4')]
 def test_two_batches_approve_then_nested_router(self):
  self.assertEqual(len(self.txs),2)
  for t in self.txs:
   p=inspect(t['data']);a,b=p['calls']
   self.assertFalse(p['scope_verified']);self.assertFalse(p['execution_verified'])
   self.assertEqual(a['data'][:10],'0x095ea7b3')
   self.assertEqual('0x'+a['data'][34:74],b['target'])
   self.assertEqual(b['target'],'0x5399d94d2cab7c252a6034042e1917a0e5e17a18')
   self.assertEqual(b['data'][:10],'0x0a54da07')
   self.assertEqual(len(bytes.fromhex(b['data'][2:])),2468)
   self.assertEqual((a['value'],b['value']),(0,0))
 def test_reject_alias_truncation_and_trailing_bytes(self):
  data=self.txs[0]['data']
  for bad in (data[:-2],data+'00'):
   with self.assertRaises(ValueError):inspect(bad)
  raw=bytearray.fromhex(data[2:]);raw[4+352:4+384]=(64).to_bytes(32,'big')
  with self.assertRaises(ValueError):inspect('0x'+raw.hex())
