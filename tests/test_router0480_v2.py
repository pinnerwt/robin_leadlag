import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_v2 import intent
class V2Test(unittest.TestCase):
 def test_actual_v2_call_from_original_command(self):
  r=json.loads(Path('reports/amm/router0480-v2-command.json').read_text());raw=bytes.fromhex(r['original_tx']['data'][2:]);o=r['command_offset'];p=intent(r['original_tx']['data'],o,o+8);c=r['result']['calls'][0]
  self.assertEqual(p['pool'],c['to']);self.assertEqual(p['data'],c['data']);self.assertEqual(p['amount0_out'],0);self.assertGreater(p['amount1_out'],0);self.assertFalse(p['execution_complete'])
  offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];self.assertEqual(raw[offsets[offsets.index(o)-1]],254)
 def test_nonzero_recipient_rejected(self):
  r=json.loads(Path('reports/amm/router0480-v2-command.json').read_text());raw=bytearray.fromhex(r['original_tx']['data'][2:]);o=r['command_offset'];raw[o+6:o+8]=(22).to_bytes(2,'big')
  with self.assertRaises(ValueError):intent('0x'+raw.hex(),o,o+8)
