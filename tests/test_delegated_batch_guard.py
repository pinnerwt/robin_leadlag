import json,unittest
from pathlib import Path
class BatchGuardTest(unittest.TestCase):
 def test_guard_branch_and_attempted_write(self):
  e=json.loads(Path('reports/amm/delegated-batch-guard.json').read_text())
  self.assertEqual(len(e['cases']),6)
  for c in e['cases']:
   r=c['result']
   if c['synthetic_guard']==2:
    self.assertEqual(r['output'],'0x3ee5aeb5');self.assertFalse(r['execution_success'])
   else:
    self.assertIn('unknown slot',r['error'])
    self.assertEqual(r['storage_writes'][0]['slot'],e['slot'])
    self.assertEqual(r['storage_writes'][0]['value'],'0x2')
 def test_explicit_gate_branch_outcomes(self):
  for name,blocked,selector in [('gates',1,'0x887541a8'),('allow-profile',0,'0xa263a538')]:
   e=json.loads(Path('reports/amm/delegated-batch-'+name+'.json').read_text())
   self.assertEqual(len(e['cases']),4)
   for c in e['cases']:
    value=int(list(c['synthetic_patches'].values())[-1],16);r=c['result']
    if value==blocked:
     self.assertEqual(r['output'],selector);self.assertFalse(r['execution_success'])
    else:self.assertIn('unknown slot',r['error'])
    self.assertEqual(r['calls'],[])
 def test_mapping6_signer_gate_and_real_recovery(self):
  e=json.loads(Path('reports/amm/delegated-batch-allow-signer.json').read_text())
  for c in e['cases']:
   value=int(list(c['synthetic_patches'].values())[-1],16);r=c['result']
   if value==0:self.assertEqual(r['output'],'0x0a6cbecd')
   else:self.assertIn('unknown account 0x94448',r['error'])
  e=json.loads(Path('reports/amm/delegated-batch-signature.json').read_text())
  self.assertEqual(len(e['cases']),2)
  for c in e['cases']:
   r=c['result'];self.assertIsNone(r['error'])
   returns=[x for x in r['execution_returns'] if x['to']=='0x'+'00'*19+'01']
   self.assertEqual(len(returns),1)
   self.assertEqual(returns[0]['output'],'0x'+('0'*24)+'94448c4a58691358e567f8b741871a2ab7e71963')
   self.assertEqual(r['calls'][0]['data'][:10],'0x70a08231')
 def test_full_credit_forwards_exact_nested_bytes(self):
  e=json.loads(Path('reports/amm/delegated-batch-full-credit.json').read_text())
  for c in e['cases']:
   data=bytes.fromhex(c['tx']['data'][10:]);offset=int.from_bytes(data[192:224],'big')
   n=int.from_bytes(data[offset:offset+32],'big');payload=data[offset+32:offset+32+n]
   call=c['result']['calls'][0]
   self.assertEqual(call['to'],'0x0000000000001ff3684f28c67538d4d072c22734')
   self.assertEqual(call['data'],'0x'+payload.hex())
   self.assertEqual(call['data'][:10],'0x2213bc0b')
   self.assertIsNone(c['result']['error'])
