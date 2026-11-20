import json,unittest
from pathlib import Path
class WrapperV4Test(unittest.TestCase):
 def test_wrapper_trailer_is_forwarded_to_external_contract(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-v4-probe.json').read_text())
  self.assertTrue(any('unknown account' in (r['error'] or '') for r in e['stages']))
  self.assertEqual(e['synthetic_accounts'],['0xc348f6953705cd6dbf6d681b79b1e75f843d8a48'])
  call=e['result']['calls'][0];self.assertEqual(call['to'],e['synthetic_accounts'][0])
  self.assertEqual(call['data'][:10],'0xc90e8616')
  self.assertEqual(call['data'][10:],e['tx']['data'][-256:])
 def test_second_swap_uses_first_output_after_manager_take(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-v4-probe.json').read_text())
  self.assertEqual(e['stages'][0]['calls'][0]['data'][:10],'0x0b0d9c09')
  call=e['stages'][1]['calls'][0];self.assertEqual(call['to'],'0xc3c9f0171490ef0f4536fe493f3b0ebb5ee0cb5e')
  self.assertEqual(call['data'][:10],'0x128acb08');d=bytes.fromhex(call['data'][10:])
  self.assertEqual(int.from_bytes(d[64:96],'big'),e['synthetic_outputs'][0])
 def test_authorized_executor_calls_v4_with_empty_hook_data(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-v4-authorization-code.json').read_text())
  self.assertTrue(e['code_research_anchor']);a=e['plan']['actions'][-1]
  r=e['result'];self.assertIsNone(r['error']);self.assertEqual(len(r['calls']),1)
  call=r['calls'][0];self.assertEqual(call['data'][:10],'0xf3cd914c')
  self.assertEqual(call['caller'].lower(),'0xc348f6953705cd6dbf6d681b79b1e75f843d8a48')
  d=bytes.fromhex(call['data'][10:]);w=lambda i:int.from_bytes(d[i*32:(i+1)*32],'big')
  self.assertEqual([w(i) for i in range(6)],[int(a['currency0'],16),int(a['currency1'],16),a['fee'],a['spacing'],int(a['hook'],16),a['direction']])
  self.assertEqual(w(6)-(1<<256),-e['synthetic_outputs'][-1])
  self.assertEqual(w(7),4295128740);self.assertEqual(w(8),288);self.assertEqual(w(9),0);self.assertEqual(len(d),320)
  calls=[c for stage in e['stages'] for c in stage['calls']]
  self.assertTrue(any(c['data']=='0x3dd45adb'+'00'*12+'c348f6953705cd6dbf6d681b79b1e75f843d8a48' for c in calls))
