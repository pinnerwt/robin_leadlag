import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from packed_routers import decode_packed, ROUTER_610
from v3_calldata import word,signed,decode

class Router610Test(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.registry=json.loads(Path('config/optimistic-router-template.json').read_text())
  cls.cases=json.loads(Path('reports/amm/router610-prefix.json').read_text())
  cls.corpus={r['tx']['tx']:r for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines())}
 def test_actual_bytecode_arguments_and_log_bounds(self):
  self.assertEqual(len(self.cases),26)
  for case in self.cases:
   tx,r=case['tx'],case['result'];self.assertIsNone(r['error']);self.assertEqual(len(r['calls']),1)
   op=decode_packed(ROUTER_610,tx['data'],self.registry)[0];call=r['calls'][0]
   self.assertEqual(call['data'][:10],'0x128acb08');raw=bytes.fromhex(call['data'][10:])
   expected=dict(pool=call['to'],zero=bool(word(raw,1)),amount=signed(word(raw,2)),limit=word(raw,3))
   for k,v in expected.items():self.assertEqual(op[k],v)
   logs=[l for l in self.corpus[tx['tx']]['logs'] if l['address'].lower()==op['pool']]
   self.assertEqual(len(logs),1);raw=bytes.fromhex(logs[0]['data'][2:]);x,y=signed(word(raw,0)),signed(word(raw,1))
   filled=max(x,y) if op['amount']>0 else -min(x,y)
   self.assertEqual(x>0,op['zero']);self.assertGreater(filled,0);self.assertLessEqual(filled,abs(op['amount']))
   if filled<abs(op['amount']):self.assertEqual(word(raw,2),op['limit'])
 def test_scope_and_invalid_framing(self):
  data=self.cases[0]['tx']['data'];op=decode_packed(ROUTER_610,data,self.registry)[0]
  self.assertEqual(decode(ROUTER_610,data,{},[],packed_registry=self.registry),[])
  self.assertEqual(len(decode(ROUTER_610,data,{op['pool']:{}},[],packed_registry=self.registry)),1)
  for bad in (data[:-2],data+'00',data[:6]+'04'+data[8:]):
   with self.assertRaises(ValueError):decode_packed(ROUTER_610,bad,self.registry)
