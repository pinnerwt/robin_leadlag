import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_route import inspect
class RouteTest(unittest.TestCase):
 def test_original_route_and_payment_inputs(self):
  r=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());p=inspect(r['tx']['data']);self.assertEqual(len(p['pools']),3);self.assertEqual(p['terminal']['minimum'],0)
  self.assertEqual(p['swaps'][1]['token_in'],'0x61a10e8556bed032ea176330e7f17d6a12a10000');self.assertFalse(p['scope_verified'])
  actual=json.loads(Path('reports/amm/router0480-nested-paid.json').read_text())['synthetic_transfers']
  for x,c in zip(p['payments'],actual):self.assertEqual(x['token'],c['to']);self.assertEqual(x['data'],c['data'])
 def test_different_payment_pointer_rejected(self):
  r=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());raw=bytearray.fromhex(r['tx']['data'][2:]);raw[329:331]=(142).to_bytes(2,'big')
  with self.assertRaisesRegex(ValueError,'payment'):inspect('0x'+raw.hex())
