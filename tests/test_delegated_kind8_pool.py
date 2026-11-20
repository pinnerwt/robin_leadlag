import json,unittest
from pathlib import Path
class KindEightPoolTest(unittest.TestCase):
 def test_saved_quote_is_read_only_and_zero(self):
  e=json.loads(Path('reports/amm/delegated-kind8-pool-probe.json').read_text())
  call=e['stages'][0]['calls'][0]
  self.assertEqual(call['scheme'],'StaticCall');self.assertEqual(call['data'][:10],'0xac8b0bb9')
  returns=e['result']['execution_returns']
  quote=next(r for r in returns if r['selector']=='0xac8b0bb9')
  self.assertEqual(quote['result'],'Return');self.assertEqual(int(quote['output'],16),0)
  swap=next(r for r in returns if r['selector']=='0x7c6c84af')
  self.assertEqual(swap['result'],'Revert');self.assertIn(b'insufficient output',bytes.fromhex(swap['output'][2:]))
 def test_synthetic_quote_drives_output_transfer(self):
  e=json.loads(Path('reports/amm/delegated-kind8-pool-quote-1000000000000000000.json').read_text())
  call=e['quoted']['calls'][0]
  self.assertEqual(call['to'],'0x0bd7d308f8e1639fab988df18a8011f41eacad73')
  self.assertEqual(call['data'][:10],'0xa9059cbb');d=bytes.fromhex(call['data'][10:])
  self.assertEqual(int.from_bytes(d[:32],'big'),int(e['tx']['to'],16))
  self.assertEqual(int.from_bytes(d[32:],'big'),e['synthetic_quote_output'])
 def test_full_credit_reaches_exact_unwrap_then_settle(self):
  e=json.loads(Path('reports/amm/delegated-kind8-pool-quote-1000000000000000000-credited.json').read_text())
  self.assertTrue(e['synthetic_credit'])
  call=e['credited']['calls'][0];self.assertEqual(call['data'][:10],'0x2e1a7d4d')
  self.assertEqual(int(call['data'][10:],16),e['synthetic_quote_output'])
  returns=e['credited']['execution_returns']
  target=next(r for r in returns if r['selector']=='0x9908fc8b')
  self.assertEqual(target['result'],'Return');self.assertEqual(int(target['output'],16),e['synthetic_quote_output'])
  self.assertEqual(e['withdrawn']['calls'][0]['data'],'0x11da60b4')
 def test_settlement_takes_end_callback_without_more_pool_calls(self):
  e=json.loads(Path('reports/amm/delegated-kind8-pool-quote-30000000000000000000-credited.json').read_text())
  self.assertTrue(e['synthetic_take_returns']);self.assertEqual(len(e['take_stages']),2)
  takes=[e['settled']['calls'][0],e['take_stages'][0]['calls'][0]]
  for call in takes:
   self.assertEqual(call['to'],'0x8366a39cc670b4001a1121b8f6a443a643e40951')
   self.assertEqual(call['data'][:10],'0x0b0d9c09')
   self.assertEqual(int.from_bytes(bytes.fromhex(call['data'][10:])[:32],'big'),0)
  terminal=e['terminal'];self.assertEqual(terminal['calls'],[])
  cb=next(r for r in terminal['execution_returns'] if r['selector']=='0x91dd7346')
  self.assertEqual(cb['result'],'Return')
  root=terminal['execution_returns'][-1]
  self.assertEqual(root['selector'],'0x0c89e77a');self.assertEqual(root['result'],'Revert')
