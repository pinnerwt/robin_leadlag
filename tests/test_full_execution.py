import json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FullExecution(unittest.TestCase):
 def run_probe(self,code,storage,txdata,hashed=None):
  caller='0x1111111111111111111111111111111111111111';target='0x2222222222222222222222222222222222222222'
  seed={'accounts':{'0x'+'00'*20:{'balance':'0x0','nonce':'0x0','code':'0x'},caller:{'code':'0x','balance':'0xffffffffffffffff','nonce':'0x0'},target:{'code':code,'storage':storage}}}
  if hashed is not None:seed['accounts'][target]['complete_hashed_storage']=hashed
  txs=[dict(tx=str(i),to=target,**{'from':caller},data=d,value='0x0',sequence=1,l1_block=1,timestamp=1,gas_limit=100000,nonce=i) for i,d in enumerate(txdata)]
  with tempfile.NamedTemporaryFile(mode='w') as f:
   json.dump(seed,f);f.flush()
   return subprocess.run([str(ROOT/'target/release/examples/router_execute'),f.name,'--commit'],input=''.join(json.dumps(t)+'\n' for t in txs),text=True,capture_output=True)
 def test_atomic_revert_and_nonce_commit(self):
  # Nonempty calldata: SSTORE(0,1), REVERT. Empty calldata: return SLOAD(0).
  p=self.run_probe('0x3615600c5760016000555ffd5b6000545f5260205ff3',{'0x0':'0x0'},['0x01','0x'])
  self.assertEqual(p.returncode,0,p.stderr);rows=list(map(json.loads,p.stdout.splitlines()))
  self.assertFalse(rows[0]['success']);self.assertTrue(rows[1]['success']);self.assertEqual(int(rows[1]['output'],16),0)
 def test_missing_slot_stops_committed_stream(self):
  p=self.run_probe('0x6000545f5260205ff3',{},['0x','0x'])
  self.assertNotEqual(p.returncode,0);rows=list(map(json.loads,p.stdout.splitlines()));self.assertEqual(len(rows),1);self.assertIn('unknown slot',rows[0]['error']);self.assertFalse(rows[0]['committed'])
 def test_complete_hashed_storage_and_committed_override(self):
  import sys
  sys.path.insert(0,str(ROOT/'scripts'));from bootstrap_state import hashhex
  hashed={hashhex(bytes(32)):'0x7'}
  p=self.run_probe('0x6000545f5260205ff3',{},['0x'],hashed);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(int(json.loads(p.stdout)['output'],16),7)
  p=self.run_probe('0x6001545f5260205ff3',{},['0x'],hashed);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(int(json.loads(p.stdout)['output'],16),0)
  p=self.run_probe('0x3615600b576001600055005b6000545f5260205ff3',{},['0x01','0x'],hashed);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(int(json.loads(p.stdout.splitlines()[-1])['output'],16),1)
