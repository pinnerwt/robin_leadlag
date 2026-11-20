import json,unittest
from pathlib import Path
class SettlerTailTest(unittest.TestCase):
 def test_mock_swap_without_callback_rejected(self):
  e=json.loads(Path('reports/amm/delegated-settler-tail-796969091046830-1454595.json').read_text())
  for c in e['cases']:
   self.assertFalse(c['result']['execution_success'])
   self.assertTrue(c['result']['output'].startswith('0xd66fcc38fa461e33'))
 def test_real_callback_reaches_minimum_output_check(self):
  e=json.loads(Path('reports/amm/delegated-settler-tail-callback.json').read_text());r=e['result']
  self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);self.assertEqual(r['calls'],[])
  callbacks=[x for x in r['execution_returns'] if x['selector']=='0xfa461e33']
  self.assertEqual(len(callbacks),1);self.assertEqual(callbacks[0]['result'],'Return')
  plan=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions'][1]['plan']
  d=bytes.fromhex(r['output'][10:]);self.assertEqual(r['output'][:10],'0x97a6f3b9')
  self.assertEqual(int.from_bytes(d[:32],'big'),int(plan['buy_token'],16))
  self.assertEqual(int.from_bytes(d[32:64],'big'),plan['min_output'])
  self.assertEqual(int.from_bytes(d[64:96],'big'),1454595)
 def test_surplus_transfer_intent_matches_actual(self):
  import sys
  sys.path.insert(0,str(Path('scripts').resolve()))
  from delegated_settler_tail import intent
  p=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions'][1]['plan']
  e=json.loads(Path('reports/amm/delegated-settler-tail-callback-output-4000000.json').read_text())
  i=intent(p['actions'][3]['data'],e['synthetic_v3_output']);call=e['result']['calls'][0]
  self.assertEqual(call['to'],i['token']);self.assertEqual(call['data'][:10],'0xa9059cbb')
  self.assertEqual(int(call['data'][10:74],16),int(i['recipient'],16))
  self.assertEqual(int(call['data'][-64:],16),i['amount'])
  self.assertEqual(i['remaining'],1843012)
 def test_paid_tail_success_has_consistent_remaining_balance(self):
  e=json.loads(Path('reports/amm/delegated-settler-tail-callback-output-4000000-paid.json').read_text())
  self.assertTrue(e['result']['execution_success']);self.assertEqual(e['result']['calls'],[])
  transfers=[c for s in e['stages'] for c in s['calls'] if c['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and c['data'].startswith('0xa9059cbb')]
  self.assertEqual([int(c['data'][-64:],16) for c in transfers],[2156988,1843011])
  self.assertEqual(sum(int(c['data'][-64:],16) for c in transfers)+1,e['synthetic_v3_output'])
