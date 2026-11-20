import copy,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class BatchReport(unittest.TestCase):
 def test_deposit_is_not_silently_applied_as_batch_report(self):
  f=self.fixture();f['message']['system_kind']='eth_deposit'
  with tempfile.NamedTemporaryFile(mode='w') as file:
   json.dump(f,file);file.flush()
   p=subprocess.run([str(ROOT/'target/release/examples/arbos_report'),file.name],text=True,capture_output=True)
  self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'');self.assertIn('unsupported report type',p.stderr)
 def fixture(self):return json.loads((ROOT/'captures/batch-report-fixture.json').read_text())
 def expected(self,f):
  d=f['diff'][1]['result'];writes={a:{hex(int(k,16)):hex(int(v,16)) for k,v in x['storage'].items()} for a,x in d['post'].items() if x.get('storage')}
  for a,x in d['pre'].items():
   for k in x.get('storage',{}):
    if k not in d['post'].get(a,{}).get('storage',{}):writes.setdefault(a,{})[hex(int(k,16))]='0x0'
  return writes,{a:hex(int(x['balance'],16)) for a,x in d['post'].items() if 'balance' in x}
 def test_mainnet_report_storage_and_payments(self):
  f=self.fixture();p=subprocess.run([str(ROOT/'target/release/examples/arbos_report'),str(ROOT/'captures/batch-report-fixture.json')],text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout);writes,balances=self.expected(f)
  self.assertEqual(r['writes'],writes);self.assertEqual(r['balances'],balances)
 def test_start_block_then_report_without_reseeding(self):
  f=self.fixture();accounts=copy.deepcopy(f['pre'][0]['result'])
  for a,v in f['pre'][1]['result'].items():
   dst=accounts.setdefault(a,{k:x for k,x in v.items() if k!='storage'})
   for k,x in v.get('storage',{}).items():dst.setdefault('storage',{}).setdefault(k,x)
  seed=dict(accounts=accounts,anchor=f['parent'],parent_header=f['parent']);tx=f['message'];marker={k:tx[k] for k in ('sequence','block_hash','timestamp','l1_block','recv_ns','mono_ns')};marker.update(kind='feed_block',transaction_count=1)
  with tempfile.NamedTemporaryFile(mode='w') as file:
   json.dump(seed,file);file.flush()
   p=subprocess.run([str(ROOT/'target/release/examples/router_execute'),file.name,'--commit','--units-mode=signed','--block-mode'],input=json.dumps(marker)+'\n'+json.dumps(tx)+'\n',text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stderr);rows=list(map(json.loads,p.stdout.splitlines()));self.assertEqual(len(rows),2)
  r=rows[1];self.assertEqual(r['kind'],'system_state');self.assertTrue(r['committed']);writes,balances=self.expected(f)
  self.assertEqual(r['changed_storage'],writes);self.assertEqual({a:v['balance'] for a,v in r['accounts'].items()},balances)
 def test_missing_storage_fails_before_output(self):
  f=self.fixture();f['pre'][1]['result']['0xa4b05fffffffffffffffffffffffffffffffffff']['storage']={}
  with tempfile.NamedTemporaryFile(mode='w') as file:
   json.dump(f,file);file.flush();p=subprocess.run([str(ROOT/'target/release/examples/arbos_report'),file.name],text=True,capture_output=True)
  self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'');self.assertIn('unseeded report slot',p.stderr)

if __name__=='__main__':unittest.main()
