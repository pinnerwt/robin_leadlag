import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v3_state import State
class V4ArithmeticTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.f=json.loads(Path('tests/fixtures/v4_arithmetic.json').read_text())
 def state(self):
  d=copy.deepcopy(self.f['state']);d['bitmap']={int(k):v for k,v in d['bitmap'].items()};d['ticks']={int(k):tuple(v) for k,v in d['ticks'].items()}
  return State(**d)
 def test_nine_bytecode_amounts(self):
  s=self.state();before=copy.deepcopy(s)
  for c in self.f['cases']:self.assertEqual(s.swap(c['zero'],c['amount'],c['limit']),c['expected'])
  self.assertEqual(s,before)
 def test_commit_affects_next_price(self):
  s=self.state();c=self.f['cases'][0]
  a=s.swap(c['zero'],c['amount'],c['limit'],True)
  b=s.swap(c['zero'],c['amount'],c['limit'])
  self.assertLess(-min(b['amount0'],b['amount1']),-min(a['amount0'],a['amount1']))
 def test_missing_bitmap_rejected(self):
  s=self.state();s.bitmap={};c=self.f['cases'][0]
  with self.assertRaisesRegex(ValueError,'bitmap'):s.swap(c['zero'],c['amount'],c['limit'])
if __name__=='__main__':unittest.main()
