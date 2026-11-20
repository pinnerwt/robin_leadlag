import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_hook_fee import native_output_fee
class NewCheckpointTest(unittest.TestCase):
 def test_coherent_initialization_and_actual_swap_parity(self):
  s=json.loads(Path('reports/amm/settler-upstream-new-checkpoint.json').read_text());p=json.loads(Path('reports/amm/settler-upstream-new-probe.json').read_text())
  self.assertTrue(s['anchor_verified']);self.assertIsNone(s['error']);self.assertTrue(all(s['code_matches'].values()))
  self.assertEqual(p['anchor'],s['seed']['anchor']['hash']);self.assertEqual(len(s['reads']),14)
  for read in s['reads']:self.assertEqual(s['seed']['accounts'][read['address']]['storage'][read['slot']],read['value'])
  r=p['result'];self.assertIsNone(r['error']);self.assertEqual(r['calls'],[]);self.assertIsNone(p['curve_error'])
  hook=s['plan']['hook'];slot=next(x['slot'] for x in r['storage_reads'] if x['address']==hook and x['pc']==12864)
  config=int(s['seed']['accounts'][hook]['storage'][slot],16);gross=-p['expected']['amount0'];local=native_output_fee(config,gross)
  ret=next(x for x in r['execution_returns'] if x['selector']=='0xf3cd914c' and x['result']=='Return');packed=int(ret['output'],16)
  self.assertEqual(packed>>128,local['net'])
  fee=int(next(x['output'][-64:] for x in r['execution_returns'] if x['selector']=='0xb47b2fb1' and x['result']=='Return'),16)
  self.assertEqual(fee,local['fee'])
  self.assertEqual((packed&((1<<128)-1))-(1<<128),-p['expected']['amount1'])
  writes=[w for w in r['storage_writes'] if w['address']=='0x8366a39cc670b4001a1121b8f6a443a643e40951']
  self.assertTrue(any((int(w['value'],16)&((1<<160)-1))==p['expected']['sqrt'] for w in writes))
