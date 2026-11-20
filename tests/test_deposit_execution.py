import copy,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ARB='0xa4b05fffffffffffffffffffffffffffffffffff';FILTER='0xa4b0500000000000000000000000000000000001'
class DepositExecution(unittest.TestCase):
 def fixture(self):return json.loads((ROOT/'captures/eth-deposit-execution-fixture.json').read_text())
 def run_fixture(self,f):
  with tempfile.NamedTemporaryFile(mode='w') as out:
   json.dump(f,out);out.flush();return subprocess.run([str(ROOT/'target/release/examples/arbos_deposit'),out.name],text=True,capture_output=True)
 def test_real_deposit_balance_diff(self):
  f=self.fixture();p=self.run_fixture(f);self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout)
  d=json.loads((ROOT/'captures/eth-deposit-chain-diff.json').read_text());expected={a:v['balance'] for a,v in d['post'].items()}
  self.assertEqual(r['balances'],expected);self.assertFalse(r['filtered']);self.assertEqual(r['gas_used'],0)
 def test_missing_filter_witness_fails(self):
  f=self.fixture();f['accounts'][FILTER]['storage']={};p=self.run_fixture(f)
  self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'');self.assertIn('unseeded deposit slot',p.stderr)
 def test_ordinary_filter_gate_stops_before_evm(self):
  import sys
  sys.path.insert(0,str(ROOT/'scripts'));from bootstrap_state import hashhex
  b=json.loads((ROOT/'captures/batch-report-fixture.json').read_text());accounts=copy.deepcopy(b['pre'][0]['result'])
  for a,v in b['pre'][1]['result'].items():
   dst=accounts.setdefault(a,copy.deepcopy(v))
   for k,x in v.get('storage',{}).items():dst.setdefault('storage',{}).setdefault(k,x)
  tx={k:b['message'][k] for k in ('sequence','block_hash','timestamp','l1_block','recv_ns','mono_ns')};tx.update(kind='feed_tx',tx='0x'+'ab'*32)
  marker=dict(tx,kind='feed_block',transaction_count=1)
  raw=bytes.fromhex(tx['tx'][2:]);slot=bytes.fromhex(hashhex(raw[:31])[2:])[:31]+raw[31:]
  for filtered in (False,True):
   seed=dict(accounts=copy.deepcopy(accounts),anchor=b['parent'],parent_header=b['parent'])
   if filtered:seed['accounts'][FILTER]={'complete_hashed_storage':{hashhex(slot):'0x1'}}
   with tempfile.NamedTemporaryFile(mode='w') as out:
    json.dump(seed,out);out.flush();p=subprocess.run([str(ROOT/'target/release/examples/router_execute'),out.name,'--commit','--units-mode=signed','--block-mode','--require-filter-state'],input=json.dumps(marker)+'\n'+json.dumps(tx)+'\n',text=True,capture_output=True)
   self.assertNotEqual(p.returncode,0);self.assertEqual(len(p.stdout.splitlines()),1)
   self.assertIn('filtered ordinary transaction' if filtered else 'transaction filter entry',p.stderr)
 def test_start_block_then_deposit_dispatch(self):
  # Composition test using the existing StartBlock fixture context. It is not
  # a claim of full-chain parity at the captured deposit's real block.
  b=json.loads((ROOT/'captures/batch-report-fixture.json').read_text());f=self.fixture();accounts=copy.deepcopy(b['pre'][0]['result'])
  for source in (b['pre'][1]['result'],f['accounts']):
   for a,v in source.items():
    dst=accounts.setdefault(a,copy.deepcopy(v))
    for k,x in v.get('storage',{}).items():dst.setdefault('storage',{}).setdefault(k,x)
  tx=copy.deepcopy(f['message'])
  for k in ('sequence','block_hash','timestamp','l1_block','recv_ns','mono_ns'):tx[k]=b['message'][k]
  marker={k:tx[k] for k in ('sequence','block_hash','timestamp','l1_block','recv_ns','mono_ns')};marker.update(kind='feed_block',transaction_count=1)
  seed=dict(accounts=accounts,anchor=b['parent'],parent_header=b['parent'])
  with tempfile.NamedTemporaryFile(mode='w') as out:
   json.dump(seed,out);out.flush();p=subprocess.run([str(ROOT/'target/release/examples/router_execute'),out.name,'--commit','--units-mode=signed','--block-mode'],input=json.dumps(marker)+'\n'+json.dumps(tx)+'\n',text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stderr);rows=list(map(json.loads,p.stdout.splitlines()));self.assertEqual(len(rows),2)
  self.assertTrue(rows[1]['committed']);self.assertTrue(rows[1]['success']);self.assertEqual(rows[1]['system_kind'],'eth_deposit')
  to=tx['to'];expected=int(accounts[to]['balance'],16)+int(tx['value'],16)
  self.assertEqual(int(rows[1]['accounts'][to]['balance'],16),expected)
 def test_filtered_redirect_and_default_recipient(self):
  for fallback in (False,True):
   with self.subTest(fallback=fallback):
    f=self.fixture();s=f['accounts'][FILTER]['storage'];s[next(iter(s))]='0x1';slots=f['accounts'][ARB]['storage'];root=next(iter(slots))[:-2];recipient=f['message']['from'].lower()
    slots[root+'0a']='0x0' if fallback else recipient
    if fallback:slots[root+'03']=recipient
    p=self.run_fixture(f);self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout)
    expected=int(f['accounts'][recipient]['balance'],16)+int(f['message']['value'],16)
    self.assertTrue(r['filtered']);self.assertEqual(r['recipient'],recipient);self.assertEqual(r['balances'],{recipient:hex(expected)})
 def test_missing_recipient_and_overflow_fail(self):
  for overflow in (False,True):
   f=self.fixture();to=f['message']['to'].lower()
   if overflow:f['accounts'][to]['balance']=hex(2**256-1)
   else:del f['accounts'][to]
   p=self.run_fixture(f);self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')
