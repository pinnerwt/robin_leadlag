"""Real interpreter bytecode tests for the explicit CLZ research extension."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from probe_delegated_kind8 import run
class ClzTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tx=json.loads(Path('reports/amm/router0480-0d-manager.json').read_text())['tx'];base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());keep={cls.tx['to'].lower(),cls.tx['from'].lower(),'0x'+'00'*20};cls.seed=dict(base,accounts={a:v for a,v in base['accounts'].items() if a in keep},trace_execution=True)
 def execute(self,code,enabled=True):
  seed=dict(self.seed,enable_clz=enabled,accounts=dict(self.seed['accounts']));a=self.tx['to'].lower();seed['accounts'][a]=dict(seed['accounts'][a],code='0x'+code.hex());return run(seed,self.tx)
 def test_vectors(self):
  for x,want in [(0,256),(1,255),(1<<255,0),((1<<256)-1,0),(1<<254,1)]:
   r=self.execute(b'\x7f'+x.to_bytes(32,'big')+bytes.fromhex('1e5f5260205ff3'));self.assertIsNone(r['error']);self.assertTrue(r['execution_success']);self.assertEqual(int(r['output'],16),want)
 def test_disabled_and_underflow(self):
  r=self.execute(bytes.fromhex('5f1e00'),False);self.assertFalse(r['execution_success']);self.assertTrue(any(x['result']=='OpcodeNotFound' for x in r['execution_returns']))
  r=self.execute(bytes.fromhex('1e00'));self.assertFalse(r['execution_success']);self.assertTrue(any(x['result']=='StackUnderflow' for x in r['execution_returns']))
