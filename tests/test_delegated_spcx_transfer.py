"""Full token-transfer bytecode execution under explicit recipient interventions."""
import json,unittest
from pathlib import Path
TOKEN='0x4a0e65a3eccec6dbe60ae065f2e7bb85fae35eea'
SENDER='0x4fcabac3c531c99dce8b519ec88dc724429b569b41c47efdcb8969c70cb4e7ed'
RECIPIENT='0xb92fa9fa771c8c6f4cb9b772cf5ec06af5b8f4bd8794f2a485b727543df51b80'
class SpcxTransferTest(unittest.TestCase):
 def test_full_credit_and_no_extra_balance_writes(self):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
  before=int(seed['accounts'][TOKEN]['storage'][SENDER],16)
  for name,initial in [('zero',0),('nonzero',1000)]:
   case=json.loads(Path('reports/amm/delegated-spcx-accounting-'+name+'.json').read_text());r=case['result']
   amount=int(case['transaction']['data'][-64:],16)
   self.assertIsNone(r['error']);self.assertTrue(r['execution_success']);self.assertEqual(r['calls'],[])
   self.assertEqual(int(r['output'],16),1);self.assertEqual(len(r['storage_writes']),2)
   writes={w['slot']:int(w['value'],16) for w in r['storage_writes']}
   self.assertEqual(writes[SENDER],before-amount);self.assertEqual(writes[RECIPIENT],initial+amount)
 def test_restricted_recipient_reverts_without_writes(self):
  r=json.loads(Path('reports/amm/delegated-spcx-accounting-restricted.json').read_text())['result']
  self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);self.assertEqual(r['calls'],[])
  self.assertTrue(r['output'].startswith('0x75e91ce7'));self.assertEqual(r['storage_writes'],[])
