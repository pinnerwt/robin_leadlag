import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_0d import intent,withdrawal,payment_calls,settlement_call,validate_settlement
class SettlementTest(unittest.TestCase):
 def plan(self):
  r=next(r for r in json.loads(Path('reports/amm/router0480-other-swaps.json').read_text())['cases'] if r['opcode']==13)
  return intent(r['original_tx']['data'],r['offset'],r['stop'])
 def test_actual_output_boundaries(self):
  p=self.plan()
  for shift in (-1,0,1):
   row=json.loads(Path(f"reports/amm/router0480-0d-settlement-{p['minimum_output']+shift}.json").read_text());r=row['result'];self.assertIsNone(r['error']);ret=next(x['output'] for x in r['execution_returns'] if x['to']==p['manager'] and x['selector']=='0x00000000' and x['result']=='Return')
   if shift<0:
    with self.assertRaises(ValueError):withdrawal(p,ret)
    self.assertEqual(r['calls'],[]);self.assertFalse(r['execution_success'])
   else:
    w=withdrawal(p,ret);c=r['calls'][0];self.assertEqual(w['data'],c['data']);self.assertEqual(w['to'],c['to']);self.assertEqual(w['amount'],row['synthetic_native_output'])
 def test_short_and_wrong_input(self):
  p=self.plan()
  with self.assertRaises(ValueError):withdrawal(p,'0x'+bytes(32).hex())
  raw=(-p['minimum_output']).to_bytes(16,'big',signed=True)+(p['amount']+1).to_bytes(16,'big')+bytes(32)
  with self.assertRaises(ValueError):withdrawal(p,'0x'+raw.hex())

 def test_actual_payment_sequence(self):
  p=self.plan();row=json.loads(Path(f"reports/amm/router0480-0d-settlement-{p['minimum_output']}-advance.json").read_text());expected=payment_calls(p)
  sync=row['stages'][1]['calls'][0];transfer=next(c for c in row['result']['calls'] if c['data'].startswith('0xa9059cbb'))
  for want,call in zip(expected,(sync,transfer)):
   self.assertEqual(want['to'],call['to']);self.assertEqual(want['data'],call['data']);self.assertEqual(want['value'],int(call['value']))
  balance=next(c for c in row['result']['calls'] if c['data'].startswith('0x70a08231'));self.assertEqual(balance['caller'].lower(),p['manager']);self.assertEqual(balance['data'][-40:],p['manager'][2:]);self.assertFalse(row['result']['execution_success'])

 def test_actual_settlement_and_underpayment(self):
  p=self.plan();base=f"reports/amm/router0480-0d-settlement-{p['minimum_output']}-advance-paid"
  intercepted=json.loads(Path(base+'.json').read_text())['result']['calls'][0];want=settlement_call(p);self.assertEqual(want['data'],intercepted['data']);self.assertEqual(want['to'],intercepted['to'])
  for suffix,credit in [('',p['amount']),('-credit-7',7)]:
   r=json.loads(Path(base+'-settled'+suffix+'.json').read_text())['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);ret=next(x for x in r['execution_returns'] if x['selector']=='0x12e103f1');self.assertEqual(ret['result'],'Return');self.assertEqual(int(ret['output'],16),credit)
   cb=next(x for x in r['execution_returns'] if x['to']== '0x0480bafac5547926e8697de90d124b97d4a13f75' and x['selector']=='0x00000000')
   if credit==p['amount']:self.assertEqual(validate_settlement(p,ret['output']),credit);self.assertEqual(cb['result'],'Stop')
   else:
    with self.assertRaises(ValueError):validate_settlement(p,ret['output'])
    self.assertEqual(cb['result'],'Revert')
