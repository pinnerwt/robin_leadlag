import json,unittest
from pathlib import Path
class OuterCompletionTest(unittest.TestCase):
 def test_clear_allowance_does_not_replace_output_credit(self):
  e=json.loads(Path('reports/amm/delegated-outer-completion-cleanup.json').read_text())
  self.assertEqual(e['result']['output'],'0xbb2875c3');self.assertFalse(e['result']['execution_success'])
 def test_unconsumed_input_triggers_refund(self):
  e=json.loads(Path('reports/amm/delegated-outer-completion-credited.json').read_text());call=e['result']['calls'][0]
  self.assertEqual(call['to'],'0x0ddcab9ae04bda0c87ecc1640636fa11e8e613e8')
  self.assertEqual(call['data'][:10],'0xa9059cbb');self.assertEqual(int(call['data'][-64:],16),15000000000000000000000)
 def test_consumed_input_finishes_with_accounting_writes(self):
  e=json.loads(Path('reports/amm/delegated-outer-completion-consumed.json').read_text());r=e['result']
  self.assertIsNone(r['error']);self.assertTrue(r['execution_success']);self.assertEqual(r['calls'],[])
  writes={w['slot']:int(w['value'],16) for w in r['storage_writes']}
  self.assertEqual(writes['0xf1784030984c3b51204f9cd0daef056424e35b53e41a98386f47475ce2732d21'],1)
  self.assertEqual(writes['0x9']-int('61cedba6b',16),1843011)
  self.assertEqual(writes['0x9b779b17422d0df92223018b32b4d1fa46e071723d6817e2486d003becc55f00'],1)
  transfers=[c for c in r['execution_calls'] if c['depth'] and c['data'].startswith('0xa9059cbb')]
  self.assertEqual(transfers,[])
 def test_actual_outer_minimum_is_inclusive_and_rejects_zero(self):
  e=json.loads(Path('reports/amm/delegated-outer-minimum.json').read_text())
  self.assertEqual(e['minimum'],1473362)
  for c in e['cases']:
   r=c['result'];self.assertIsNone(r['error']);self.assertEqual(r['calls'],[])
   amount=c['synthetic_usdg_credit'];passes=amount>0 and amount>=e['minimum']
   self.assertEqual(r['execution_success'],passes)
   self.assertEqual(r['output'],'0x' if passes else '0xbb2875c3')
