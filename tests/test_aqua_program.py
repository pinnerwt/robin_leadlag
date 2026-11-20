import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from aqua_program import quote_exact_input,parse,MAX
class AquaProgramTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.cases=json.loads(Path('tests/fixtures/aqua_program.json').read_text())
 def test_bytecode_outputs_and_state_interventions(self):
  for case in self.cases:
   inputs={k:case[k] for k in ('token_in','token_out','balance_in','balance_out','amount')}
   self.assertEqual(quote_exact_input(bytes.fromhex(case['program']),**inputs),case['expected'])
 def test_unknown_or_truncated_program_rejected(self):
  p=bytes.fromhex(self.cases[0]['program'])
  for raw in [p[:-1],bytes([34])+p[1:],p+b'\x00\x00']:
   with self.assertRaises(ValueError):parse(raw)
 def test_fee_and_bounds_rejected(self):
  p=bytearray.fromhex(self.cases[0]['program']);p[24:28]=(10**9).to_bytes(4,'big')
  with self.assertRaises(ValueError):parse(p)
  c=self.cases[0];inputs={k:c[k] for k in ('token_in','token_out','balance_in','balance_out','amount')}
  for field,value in [('amount',0),('amount',MAX+1),('balance_in',0)]:
   with self.assertRaises(ValueError):quote_exact_input(bytes.fromhex(c['program']),**dict(inputs,**{field:value}))
if __name__=='__main__':unittest.main()
