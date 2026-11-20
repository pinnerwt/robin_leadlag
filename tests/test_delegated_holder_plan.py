import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_holder_plan import inspect
class HolderPlanTest(unittest.TestCase):
 def test_actual_forwarding_appends_outer_sender(self):
  source=json.loads(Path('reports/amm/delegated-batch-full-credit.json').read_text())
  holder=json.loads(Path('reports/amm/delegated-batch-holder.json').read_text())
  for original,observed in zip(source['cases'],holder['cases']):
   p=inspect(original['result']['calls'][0]['data'])
   calls=[c for c in observed['result']['calls'] if c['data'].startswith('0x1fff991f')]
   self.assertEqual(len(calls),1);self.assertEqual(calls[0]['to'],p['target'])
   self.assertEqual(calls[0]['data'],p['inner_calldata']+original['tx']['to'][2:].lower())
   self.assertEqual([a['selector'] for a in p['actions']],['0x6a92dacb','0x38c9c147','0x8d68a156','0x5f80abae'])
   self.assertFalse(p['scope_verified'])
 def test_settler_reaches_actual_v4_unlock(self):
  e=json.loads(Path('reports/amm/delegated-batch-settler.json').read_text())
  for c in e['cases']:
   self.assertIsNone(c['result']['error'])
   self.assertEqual([(x['to'],x['data'][:10]) for x in c['result']['calls']],[('0x8366a39cc670b4001a1121b8f6a443a643e40951','0x48c89491')])
 def test_reject_truncated_or_aliased_actions(self):
  c=json.loads(Path('reports/amm/delegated-batch-full-credit.json').read_text())['cases'][0]['result']['calls'][0]['data']
  for bad in (c[:-2],c+'00'):
   with self.assertRaises(ValueError):inspect(bad)
  b=bytearray.fromhex(c[2:]);start=4+192+4+192
  b[start+32:start+64]=b[start:start+32]
  with self.assertRaises(ValueError):inspect('0x'+b.hex())
