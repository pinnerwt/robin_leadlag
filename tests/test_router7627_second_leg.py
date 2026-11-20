import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_second_leg import intent
class SecondLegTest(unittest.TestCase):
 def test_actual_output_dependency(self):
  base='reports/amm/router7627-local-getters-shift-50-inventory-1000000000000000000-unlock-synthetic-fill'
  for output,suffix in [(2000000,''),(3000000,'-output-3000000')]:
   rows=json.loads(Path(base+suffix+'.json').read_text())['cases']
   for row in rows:
    r=row['result'];ret=next(x['output'] for x in r['execution_returns'] if x['selector']=='0xf3cd914c' and x['result']=='Return');p=intent(ret);c=r['calls'][0];self.assertIsNone(r['error']);self.assertEqual(p['amount'],output);self.assertEqual(p['data'],c['data']);self.assertEqual(p['pool'],c['to']);self.assertFalse(r['execution_success'])
 def test_wrong_direction_rejected(self):
  with self.assertRaises(ValueError):intent('0x'+bytes(32).hex())
