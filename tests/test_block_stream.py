import copy,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class BlockStream(unittest.TestCase):
 def setUp(self):
  self.f=json.loads((ROOT/'captures/system-pricing-fixture.json').read_text());h=self.f['header']
  self.marker=dict(kind='feed_block',sequence=int(h['number'],16),timestamp=int(h['timestamp'],16),l1_block=int(h['l1BlockNumber'],16),block_hash=h['hash'],transaction_count=0)
 def run_blocks(self,rows,mutate=None):
  seed=dict(accounts=copy.deepcopy(self.f['system_accounts']),parent_header=self.f['parent'])
  if mutate:mutate(seed)
  with tempfile.NamedTemporaryFile(mode='w') as f:
   json.dump(seed,f);f.flush()
   return subprocess.run([str(ROOT/'target/release/examples/router_execute'),f.name,'--commit','--units-mode=signed','--block-mode'],input=''.join(json.dumps(r)+'\n' for r in rows),text=True,capture_output=True)
 def test_start_block_uses_local_pricing_and_pinned_history_code(self):
  p=self.run_blocks([self.marker]);self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout)
  self.assertEqual(r['block_base_fee'],self.f['header']['baseFeePerGas']);self.assertFalse(r['executable'])
  expected={a:{hex(int(k,16)):hex(int(v,16)) for k,v in x['storage'].items()} for a,x in self.f['system_diff']['post'].items() if x.get('storage')}
  self.assertEqual(r['changed_storage'],expected)
 def test_missing_transactions_stop(self):
  p=self.run_blocks([dict(self.marker,transaction_count=1)]);self.assertNotEqual(p.returncode,0);self.assertIn('truncated final block',p.stderr)
 def test_delayed_message_time_clamps_to_parent(self):
  baseline=self.run_blocks([self.marker]);self.assertEqual(baseline.returncode,0,baseline.stderr)
  delayed=self.run_blocks([dict(self.marker,timestamp=int(self.f['parent']['timestamp'],16)-100)])
  self.assertEqual(delayed.returncode,0,delayed.stderr)
  self.assertEqual(json.loads(delayed.stdout),json.loads(baseline.stdout))
 def test_sequence_gap_stops_before_mutation(self):
  p=self.run_blocks([dict(self.marker,sequence=self.marker['sequence']+1)]);self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')
 def test_history_code_change_rejected(self):
  p=self.run_blocks([self.marker],lambda s:s['accounts']['0x0000f90827f1c53a10cb7a02335b175320002935'].update(code='0x00'))
  self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'');self.assertIn('history code changed',p.stderr)

 def test_mainnet_time_and_l1_boundary_writes(self):
  for name in ('second','l1'):
   path=ROOT/('captures/system-start-'+name+'.json');f=json.loads(path.read_text())
   p=subprocess.run([str(ROOT/'target/release/examples/arbos_start'),str(path)],text=True,capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout)
   expected={a:{hex(int(k,16)):hex(int(v,16)) for k,v in x.get('storage',{}).items()} for a,x in f['system_diff']['post'].items() if x.get('storage')}
   for a,x in f['system_diff']['pre'].items():
    for k in x.get('storage',{}):
     if k not in f['system_diff']['post'].get(a,{}).get('storage',{}):expected.setdefault(a,{})[hex(int(k,16))]='0x0'
   self.assertEqual(r['writes'],expected);self.assertEqual(int(r['current_base_fee'],16),int(f['header']['baseFeePerGas'],16))
