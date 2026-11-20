import json,unittest
from pathlib import Path
class KindEightTest(unittest.TestCase):
 def test_actual_getter_resolves_pool_before_unlock(self):
  evidence=json.loads(Path('reports/amm/delegated-kind8-probe.json').read_text())
  getter=evidence['getter'];self.assertTrue(getter['execution_success']);self.assertEqual(getter['calls'],[])
  self.assertEqual(getter['output'],'0x'+'00'*12+'72e46c9edf828002fdbfdd0952419790576c0f18')
  prefix=evidence['prefix'];self.assertEqual(len(prefix['calls']),1)
  self.assertEqual(prefix['calls'][0]['data'][:10],'0x48c89491')
  returns=[r for r in prefix['execution_returns'] if r['selector']=='0xbbd7edc5']
  self.assertEqual(len(returns),1);self.assertEqual(returns[0]['output'],getter['output'])
