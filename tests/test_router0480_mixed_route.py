import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_mixed_route import inspect
class MixedTest(unittest.TestCase):
 def fixture(self):
  r=json.loads(Path('reports/amm/router0480-v2-tokens.json').read_text());meta={r['pool']:dict(tokens=['0x'+r['getters'][k]['output'][-40:] for k in ('token0','token1')])};tx=json.loads(Path('reports/amm/router0480-a4.json').read_text())['tx'];return tx['data'],meta
 def test_original_funding_cycle(self):
  data,meta=self.fixture();p=inspect(data,meta);self.assertEqual(p['pools'][0],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca');self.assertEqual(p['swaps'][2]['amount1_out'],p['swaps'][1]['amount']);self.assertFalse(p['scope_verified'])
  r=json.loads(Path('reports/amm/router0480-v2-command.json').read_text());self.assertEqual(p['swaps'][2]['data'],r['result']['calls'][0]['data'])
 def test_missing_or_reversed_metadata_rejects(self):
  data,meta=self.fixture()
  with self.assertRaises(ValueError):inspect(data,{})
  for v in meta.values():v['tokens'].reverse()
  with self.assertRaises(ValueError):inspect(data,meta)
