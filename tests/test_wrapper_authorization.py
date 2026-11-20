import json,unittest
from pathlib import Path
class WrapperAuthorizationTest(unittest.TestCase):
 def test_current_code_accepts_archived_signature_in_archived_context(self):
  e=json.loads(Path('reports/amm/delegated-wrapper-authorization-probe.json').read_text())
  r=e['result'];self.assertIsNone(r['error']);self.assertTrue(r['execution_success']);self.assertEqual(r['calls'],[])
  calls=[c for c in r['execution_calls'] if c['depth']>0];self.assertEqual(len(calls),1)
  self.assertEqual(calls[0]['to'],'0x'+'00'*19+'01');self.assertEqual(calls[0]['scheme'],'StaticCall')
  self.assertEqual(r['storage_writes'],[])
