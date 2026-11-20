import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from router777_plan import plan,bind_callback
class Router777CallbackTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.f=json.loads(Path('tests/fixtures/router777_callback.json').read_text())
 def test_eight_bytecode_callbacks(self):
  for c in self.f['cases']:self.assertEqual(bind_callback(plan(c['calldata']),c['aqua_output'],self.f['pools']),c['expected'])
 def test_unknown_pool_and_invalid_input(self):
  c=self.f['cases'][0];r=plan(c['calldata'])
  with self.assertRaises(ValueError):bind_callback(r,c['aqua_output'],{})
  for amount in [0,-1,1<<255]:
   with self.assertRaises(ValueError):bind_callback(r,amount,self.f['pools'])
if __name__=='__main__':unittest.main()
