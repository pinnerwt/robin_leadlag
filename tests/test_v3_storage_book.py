import copy,json,subprocess,sys,unittest
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from v3_state import State,Q96
from v3_storage_book import StorageBook
class StorageQuoteTests(unittest.TestCase):
 def fixture(self):
  a='0x'+'11'*20;s=State(Q96,0,0,500,1,{-1:0,0:0},{})
  p=dict(pool=a,sqrt=str(Q96),tick=0,liquidity='0',fee=500,spacing=1,bitmap=s.bitmap,ticks={},base_index=0,decimals=[18,18]);layout={a:dict(bitmap={'0x10000':-1,'0x10001':0},ticks={})}
  seed=dict(complete=True,anchor={'hash':'test'},pools=[p],accounts={a:{'storage':{'0x0':hex(Q96),'0x4':'0x0','0x10000':'0x0','0x10001':'0x0'}}})
  return a,StorageBook(seed,layout)
 def test_new_lp_ticks_then_remove(self):
  a,b=self.fixture();l=10**18;lo=1<<200;hi=lo+100
  hints=[dict(pool=a,slot=5,index=hex((-100)%(1<<256)),key=hex(lo)),dict(pool=a,slot=5,index=hex(100),key=hex(hi))]
  writes={a:{'0x4':hex(l),'0x10000':hex(1<<156),'0x10001':hex(1<<100),hex(lo):hex(l+(l<<128)),hex(hi):hex(l+((-l)%(1<<128)<<128))}}
  b.apply(writes,hints);q=b.quote_raw(a,10**12);self.assertGreater(q['ask_amount_raw'],q['bid_amount_raw'])
  b.apply({a:{k:'0x0' for k in writes[a]}});self.assertEqual(b.states[a].liquidity,0);self.assertFalse(b.states[a].ticks)
 def test_unknown_mapping_and_bad_liquidity_are_atomic(self):
  a,b=self.fixture();before=copy.deepcopy(b.states)
  for writes in ({a:{hex(1<<240):'0x1'}},{a:{'0x4':'0x1'}}):
   with self.assertRaises(ValueError):b.apply(writes)
   self.assertEqual(before,b.states)
 def test_same_anchor_mainnet_storage_quotes(self):
  seed=json.loads((ROOT/'captures/amm-evm-checkpoint.json').read_text());layout=json.loads((ROOT/'captures/amm-evm-layout.json').read_text());b=StorageBook(seed,layout)
  for c in seed['checks']:
   p=b.meta[c['pool']];amount=int(Decimal(c['size_tokens'])*10**p['decimals'][p['base_index']]);q=b.quote_raw(c['pool'],amount)
   self.assertEqual(str(q[c['side']+'_amount_raw']),c['remote_amount'])
 def test_evm_emits_new_tick_mapping_preimage(self):
  import tempfile
  a='0x'+'11'*20;caller='0x'+'22'*20;key='0xad66b8e7ab72f450ddfdaf1c5bc10e3a3fabf9f63ad8aa07b8743b93722f0a45'
  seed=dict(pools=[{'pool':a}],accounts={'0x'+'00'*20:{'balance':'0x0','nonce':'0x0','code':'0x'},a:{'code':'0x60405f5f37600160405f205500','storage':{key:'0x0'}},caller:{'balance':'0xffff'}})
  tx=dict(to=a,**{'from':caller},data='0x'+((100).to_bytes(32,'big')+(5).to_bytes(32,'big')).hex(),sequence=1,l1_block=1,timestamp=1,tx='fixture')
  with tempfile.NamedTemporaryFile(mode='w') as f:
   json.dump(seed,f);f.flush();p=subprocess.run([str(ROOT/'target/release/examples/router_execute'),f.name],input=json.dumps(tx)+'\n',text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout);self.assertTrue(r['success']);self.assertEqual(r['changed_storage'][a][key],'0x1')
  h=r['mapping_preimages'];self.assertEqual(len(h),1);self.assertEqual((h[0]['pool'],h[0]['slot'],int(h[0]['index'],16),h[0]['key']),(a,5,100,key))
 def test_system_storage_bypasses_simulated_getter(self):
  from bootstrap_storage import read_slots
  a='0xa4b05fffffffffffffffffffffffffffffffffff';calls=[]
  def rpc(method,params):calls.append((method,params));return '0x123'
  self.assertEqual(read_slots(rpc,'0x1',{a:[6]}),{a:{'0x6':'0x123'}})
  self.assertEqual(calls,[('eth_getStorageAt',[a,'0x6','0x1'])])
