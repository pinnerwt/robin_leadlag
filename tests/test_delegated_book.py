import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from amm_feed_state import Book
from delegated_book import PROFILE,IMPLEMENTATION,CODE_HASH,IMPLEMENTATION_HASH
class DelegatedBookTest(unittest.TestCase):
 def setUp(self):
  self.seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
  cases=json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases']
  self.tx=next(c['tx'] for c in cases if c['tx']['tx'].startswith('0x7b104a4de6'))
  self.profile=dict(profile=PROFILE,code_hash=CODE_HASH,dependencies=[dict(address=IMPLEMENTATION,code_hash=IMPLEMENTATION_HASH)])
  self.registry=dict(anchor_hash=self.seed['anchor']['hash'],routers={self.tx['to'].lower():self.profile})
 def test_book_applies_verified_curve(self):
  b=Book(self.seed,self.registry,True);touched=b.proposal(self.tx)
  evidence=json.loads(Path('reports/amm/delegated-single-curve-probe.json').read_text())['expected']
  self.assertEqual(touched,[evidence['pool']]);self.assertEqual(b.states[touched[0]].sqrt,evidence['sqrt'])
  self.assertIn(self.tx['tx'],b.partial)
 def test_wrong_pin_and_no_success_opt_in(self):
  for assumed,bad in [(False,False),(True,True)]:
   registry=copy.deepcopy(self.registry)
   if bad:registry['routers'][self.tx['to'].lower()]['code_hash']='0x00'
   b=Book(self.seed,registry,assumed);before=copy.deepcopy(b.states)
   self.assertEqual(b.proposal(self.tx),[]);self.assertEqual(b.states,before)
   self.assertIn(self.tx['tx'],b.unsupported)
 def test_any_authorization_or_missing_envelope_disables_pin(self):
  for raw in ('0x04c0',''):
   b=Book(self.seed,self.registry,True)
   b.proposal(dict(self.tx,tx='other',to='0x'+'11'*20,raw_transaction=raw))
   self.assertEqual(b.proposal(self.tx),[])
   self.assertIn('delegation may have changed',b.unsupported[self.tx['tx']])
 def test_invalid_pool_not_reused(self):
  b=Book(self.seed,self.registry,True);pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
  b.invalid[pool]='gap';before=copy.deepcopy(b.states)
  self.assertEqual(b.proposal(self.tx),[]);self.assertEqual(b.states,before)
