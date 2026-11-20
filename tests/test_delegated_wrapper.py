import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_wrapper import inspect
class WrapperTest(unittest.TestCase):
 def setUp(self):
  self.tx=next(t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['data'].startswith('0x31abd933'))
 def test_payload_matches_actual_delegatecall(self):
  p=inspect(self.tx['data'])
  r=next(r for r in map(json.loads,Path('reports/amm/delegated-router-prefix.jsonl').read_text().splitlines()) if r['tx']==self.tx['tx'])
  self.assertEqual(len(r['calls']),1);call=r['calls'][0]
  self.assertEqual(call['scheme'],'DelegateCall');self.assertEqual(call['to'],self.tx['to'].lower())
  self.assertEqual(p['inner_calldata'],call['data'])
  self.assertEqual(p['plan']['header'][3],141324316)
  self.assertEqual(p['plan']['actions'][0]['target'],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca')
  self.assertFalse(p['authorization_verified']);self.assertFalse(p['execution_complete'])
 def test_bad_framing_rejects(self):
  raw=bytes.fromhex(self.tx['data'][2:])
  for data in (raw[:132],raw[:-1],raw+b'\x00',b'\x00'*4+raw[4:]):
   with self.assertRaises(ValueError):inspect(data.hex())
 def test_actual_inner_expansion_including_nonzero_reserved(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-prefix-probe.json').read_text())
  self.assertIsNone(e['result']['error']);self.assertEqual(len(e['result']['calls']),1)
  call=e['result']['calls'][0];self.assertEqual(call['data'][:10],'0x48c89491')
  raw=bytes.fromhex(call['data'][10:]);self.assertEqual(int.from_bytes(raw[:32],'big'),32)
  size=int.from_bytes(raw[32:64],'big');body=raw[64:64+size];w=lambda offset:int.from_bytes(body[offset:offset+32],'big')
  plan=e['plan']['plan'];actions=plan['actions']
  self.assertEqual([w(i) for i in (0,32,64,96,128)],[1,128,plan['header'][3],1,len(actions)])
  keys=('kind','target','direction','token_in','token_out','currency0','currency1','fee','spacing','hook','reserved')
  for i,action in enumerate(actions):
   for j,key in enumerate(keys):
    value=action[key];self.assertEqual(w(160+i*352+j*32),int(value,16) if isinstance(value,str) else value)
  self.assertNotEqual(actions[-1]['reserved'],0)
 def test_wrapper_reaches_expected_recorded_first_swap(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-prefix-probe.json').read_text())
  r=e['callback_stages'][-1];self.assertIsNone(r['error']);self.assertEqual(len(r['calls']),1)
  call=r['calls'][0];self.assertEqual(call['to'],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca')
  self.assertEqual(call['data'][:10],'0x128acb08');d=bytes.fromhex(call['data'][10:])
  self.assertEqual(int.from_bytes(d[32:64],'big'),0);self.assertEqual(int.from_bytes(d[64:96],'big'),141324316)
