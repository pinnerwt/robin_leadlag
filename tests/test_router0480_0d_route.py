import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_0d_route import inspect
class ManagerRouteTest(unittest.TestCase):
 def row(self):return next(r for r in json.loads(Path('reports/amm/router0480-other-swaps.json').read_text())['cases'] if r['opcode']==13)
 def test_original_route(self):
  p=inspect(self.row()['original_tx']['data']);self.assertEqual(p['wrap']['value'],p['swaps'][0]['amount']);self.assertEqual(p['swaps'][1]['auxiliary_amount'],p['wrap']['value']);self.assertEqual(p['pools'][0],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca');self.assertFalse(p['execution_complete'])
 def test_guard_id_mutation(self):
  raw=bytearray.fromhex(self.row()['original_tx']['data'][2:]);first=int.from_bytes(raw[2:4],'big');raw[first+4]^=1
  with self.assertRaises(ValueError):inspect('0x'+raw.hex())
 def test_wrap_operand_mutation(self):
  raw=bytearray.fromhex(self.row()['original_tx']['data'][2:]);o=int.from_bytes(raw[10:12],'big');raw[o+1:o+3]=bytes(2)
  with self.assertRaises(ValueError):inspect('0x'+raw.hex())
 def test_all_fifteen_scope_identities(self):
  rows=json.loads(Path('reports/amm/router0480-route-corpus.json').read_text())['rows'];self.assertEqual(len(rows),15)
  for row in rows:self.assertIsNone(row['error']);self.assertEqual(row['unexplained'],[]);self.assertFalse(row['safe_to_skip']);self.assertFalse(row['plan']['execution_complete'])
