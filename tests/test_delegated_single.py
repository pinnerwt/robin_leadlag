import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_single import inspect

class SingleRouteTest(unittest.TestCase):
 def test_actual_bytecode_expansion(self):
  cases=json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases']
  verified=0
  keys=('kind','target','direction','token_in','token_out','currency0','currency1','fee','spacing','hook','reserved')
  addresses={'target','token_in','token_out','currency0','currency1','hook'}
  for case in cases:
   plan=inspect(case['tx']['data'])
   self.assertFalse(plan['execution_complete'])
   for call in case['result']['calls']:
    raw=bytes.fromhex(call['data'][2:])
    if raw[:4].hex()!='48c89491':continue
    self.assertEqual(int.from_bytes(raw[4:36],'big'),32)
    body=raw[68:68+int.from_bytes(raw[36:68],'big')]
    w=lambda pos:int.from_bytes(body[pos:pos+32],'big')
    self.assertEqual([w(i) for i in (0,32,64,96,128)], [1,128,plan['header'][3],plan['header'][4],len(plan['actions'])])
    self.assertEqual(len(body),160+352*len(plan['actions']))
    for i,a in enumerate(plan['actions']):
     for j,key in enumerate(keys):
      self.assertEqual(w(160+352*i+32*j),int(a[key],16) if key in addresses else a[key],(case['tx']['tx'],i,key))
    verified+=1
  self.assertEqual(verified,6)
 def test_truncation_and_unknown_mode(self):
  cases=json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases']
  for case in cases:
   raw=bytes.fromhex(case['tx']['data'][2:])
   for end in (0,4,5,len(raw)-1):
    with self.assertRaises(ValueError):inspect(raw[:end].hex())
   with self.assertRaises(ValueError):inspect((raw+b'\x00').hex())
   changed=bytearray(raw);changed[4]=129
   with self.assertRaises(ValueError):inspect(changed.hex())
 def test_kind_eight_is_syntax_not_execution(self):
  case=json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases'][0]
  plan=inspect(case['tx']['data'])
  self.assertEqual(plan['actions'][2]['kind'],8)
  self.assertFalse(plan['execution_complete'])
 def test_first_swap_actual_callback(self):
  from v3_state import MIN_SQRT,MAX_SQRT
  cases=json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases']
  self.assertEqual(len(cases),6)
  for case in cases:
   p=inspect(case['tx']['data']);a=p['actions'][0];calls=case['result']['calls']
   self.assertEqual(len(calls),1)
   call=calls[0];d=bytes.fromhex(call['data'][10:]);w=lambda i:int.from_bytes(d[32*i:32*(i+1)],'big')
   limit=MIN_SQRT+1 if a['direction'] else MAX_SQRT-1
   if a['kind']==0:
    self.assertEqual(call['data'][:10],'0xf3cd914c')
    self.assertEqual([w(i) for i in range(6)],[int(a['currency0'],16),int(a['currency1'],16),a['fee'],a['spacing'],int(a['hook'],16),a['direction']])
    self.assertEqual(w(6)-(1<<256),-p['header'][3]);self.assertEqual(w(7),limit)
   else:
    self.assertEqual(call['data'][:10],'0x128acb08');self.assertEqual(call['to'],a['target'])
    self.assertEqual([w(i) for i in (1,2,3)],[a['direction'],p['header'][3],limit])
