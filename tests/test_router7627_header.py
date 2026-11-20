import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_header import inspect,expired
class HeaderTest(unittest.TestCase):
 def test_original_deadlines(self):
  for row in json.loads(Path('reports/amm/router7627-prefix.json').read_text())['cases']:
   t=row['tx'];p=inspect(t['data']);self.assertEqual(p['parameter'],15000);self.assertIn(p['deadline']-t['timestamp'],(0,1,2));self.assertFalse(expired(p,t['timestamp']))
 def test_five_actual_boundaries(self):
  report=json.loads(Path('reports/amm/router7627-deadline.json').read_text());p=inspect(report['tx']['data'])
  for row in report['cases']:
   skip=expired(p,row['timestamp']);r=row['result'];self.assertIsNone(r['error']);self.assertEqual(skip,r['execution_success']);self.assertEqual(len(r['calls']),0 if skip else 1)
 def test_unverified_format(self):
  for raw in ('0x','0x6af9ac3400003a9801','0x6af9ac3400003a98'):
   with self.assertRaises(ValueError):inspect(raw)
