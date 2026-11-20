import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hub_state import primary_keys,withdraw,deposit,deposit_call,MASK248
class HubTest(unittest.TestCase):
 def test_bytecode_keys_and_writes(self):
  for row in json.loads(Path('tests/fixtures/hub_state.json').read_text()):
   self.assertEqual(primary_keys(row['primary']),row['keys'])
   for w in row['withdrawals']:self.assertEqual(withdraw(int(w['old'],16),w['amount']),int(w['expected'],16))
 def test_bounds_and_flags(self):
  self.assertEqual(withdraw((255<<248)|5,5),255<<248)
  for state,amount in [(1,2),(1,-1),(1,MASK248+1),(-1,0),(1<<256,0)]:
   with self.assertRaises(ValueError):withdraw(state,amount)
 def test_deposit_bytecode_interventions(self):
  for case in json.loads(Path('reports/amm/hub-deposit-validation.json').read_text())['cases']:
   value=(case['flags']<<248)|int(case['balance']);amount=int(case['amount'])
   if case['expected_pending_value'] is None:
    with self.assertRaises(ValueError):deposit(value,amount)
   else:self.assertEqual(deposit(value,amount),int(case['expected_pending_value'],16))
 def test_deposit_key_from_actual_trace(self):
  case=json.loads(Path('reports/amm/hub-deposit-prefix.json').read_text())
  op=deposit_call(case['request']['data'])
  write=case['result']['storage_writes'][0]
  self.assertEqual(int(op['slot'],16),int(write['slot'],16))
  self.assertEqual(op['amount'],12345)
  with self.assertRaises(ValueError):deposit_call(case['request']['data'][:-2])
 def test_malformed_descriptor(self):
  row=json.loads(Path('tests/fixtures/hub_state.json').read_text())[0]
  raw=bytearray.fromhex(row['primary'][2:]);raw[4:36]=(0).to_bytes(32,'big')
  with self.assertRaises(ValueError):primary_keys('0x'+raw.hex())
 def test_withdrawal_decode_against_bytecode(self):
  from hub_state import withdrawal_fields
  from unittest.mock import patch
  cases=json.loads(Path('tests/fixtures/hub_withdrawals.json').read_text())
  with patch('hub_state.storage_key',side_effect=AssertionError('hot path hashing')):
   for c in cases:self.assertEqual(withdrawal_fields(c['calldata'],c['caller']),c['expected'])
  with self.assertRaises(ValueError):withdrawal_fields(cases[0]['calldata'][:-2],cases[0]['caller'])
if __name__=='__main__':unittest.main()
