import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_v4 import intent
from bootstrap_state import hashhex,word
class V4CommandTest(unittest.TestCase):
 def test_actual_manager_swap_and_pool_id(self):
  r=json.loads(Path('reports/amm/router0480-v4-command.json').read_text());self.assertEqual(len(r['cases']),2)
  for row in r['cases']:
   p=intent(row['original_tx']['data'],row['command_offset'],row['command_stop']);c=row['result']['calls'][0];self.assertEqual(p['manager'],c['to']);self.assertEqual(p['data'],c['data']);k=p['key'];self.assertEqual(p['pool_id'],hashhex(b''.join(word(x) for x in [int(k['currency0'],16),int(k['currency1'],16),k['fee'],k['tick_spacing'],int(k['hooks'],16)])));self.assertLess(p['amount'],0)
 def test_nonempty_hook_data_profile_rejected(self):
  row=json.loads(Path('reports/amm/router0480-v4-command.json').read_text())['cases'][0];raw=bytearray.fromhex(row['original_tx']['data'][2:]);raw[row['command_stop']-1]=1
  with self.assertRaises(ValueError):intent('0x'+raw.hex(),row['command_offset'],row['command_stop'])
