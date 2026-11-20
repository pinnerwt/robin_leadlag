import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_other_swaps import intent
from router0480_block_guard import decode,failed
class OtherSwapTest(unittest.TestCase):
 def test_full_actual0a_calls(self):
  rows=json.loads(Path('reports/amm/router0480-other-swaps.json').read_text())['cases']
  for row in rows:
   if row['opcode']!=10:continue
   p=intent(row['tx']['data'],row['offset'],row['stop']);c=row['result']['calls'][0];self.assertEqual(p['data'],c['data']);self.assertEqual(p['pool'],c['to']);self.assertEqual(c['value'],'0');self.assertFalse(p['execution_complete'])
 def test_explicit_limit_profile_rejected(self):
  row=json.loads(Path('reports/amm/router0480-other-swaps.json').read_text())['cases'][0];raw=bytearray.fromhex(row['tx']['data'][2:]);raw[row['offset']+7]=1
  with self.assertRaises(ValueError):intent('0x'+raw.hex(),row['offset'],row['stop'])
 def test_arb_block_equality(self):
  rows=json.loads(Path('reports/amm/router0480-block-guard.json').read_text())['cases']
  for row in rows:
   raw=bytes.fromhex(row['original_tx']['data'][2:]);o=row['offset'];g=decode(raw,o,o+3,2+2*raw[0],int.from_bytes(raw[2:4],'big'));self.assertEqual(g['block_number'],row['original_tx']['sequence'])
   for case in row['boundaries']:
    skip=failed(g,case['sequence']);r=case['result'];self.assertIsNone(r['error']);self.assertEqual(skip,r['execution_success']);self.assertEqual(len(r['calls']),0 if skip else 1)
 def test_block_number_required(self):
  with self.assertRaises(ValueError):failed({'block_number':1},None)
