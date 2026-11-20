import json,unittest
from pathlib import Path
class V3ChainTest(unittest.TestCase):
 def test_upstream_outputs_size_next_swaps(self):
  e=json.loads(Path('reports/amm/delegated-v3-chain-probe.json').read_text())
  for stage,pool,amount,direction in [(e['stages'][0],'0x05afb8e895e77ce70f79056137ea606b05bf5abd',e['synthetic_first_output'],0),(e['stages'][-1],'0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca',e['synthetic_second_output'],1)]:
   self.assertIsNone(stage['error']);self.assertEqual(len(stage['calls']),1);call=stage['calls'][0]
   self.assertEqual(call['to'],pool);self.assertEqual(call['data'][:10],'0x128acb08')
   d=bytes.fromhex(call['data'][10:]);self.assertEqual(int.from_bytes(d[32:64],'big'),direction)
   self.assertEqual(int.from_bytes(d[64:96],'big'),amount)
  self.assertEqual(e['stages'][1]['calls'][0]['data'][:10],'0xa5841194')
  manager='0x8366a39cc670b4001a1121b8f6a443a643e40951'
  final=bytes.fromhex(e['stages'][-1]['calls'][0]['data'][10:])
  self.assertEqual(int.from_bytes(final[:32],'big'),int(manager,16))
