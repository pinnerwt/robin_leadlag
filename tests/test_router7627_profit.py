import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_profit import required_balance,payout
class ProfitTest(unittest.TestCase):
 def base(self,p=None):
  return 'reports/amm/router7627-local-getters-shift-50-inventory-1000000000000000000-unlock'+('' if p is None else '-parameter-'+str(p))+'-synthetic-fill-v3-transfer-balance-native--1000000000000000-usdg-2000000-take'
 def test_three_actual_thresholds(self):
  for p in (0,15000,30000):
   report=json.loads(Path(self.base(None if p==15000 else p)+'.json').read_text());want=required_balance(10**18,10**15,p)
   for row in report['cases']:
    r=row['result'];c=next(c for c in reversed(r['control_ops']) if c['pc']==9236);self.assertEqual(int(c['b']),want['required']);self.assertFalse(r['execution_success'])
 def test_boundary_and_native_unwrap(self):
  needed=required_balance(10**18,10**15,15000)['required']
  for delta in (-1,0,1):
   report=json.loads(Path(self.base()+'-after-'+str(needed+delta)+'.json').read_text())
   for row in report['cases']:
    r=row['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success'])
    if delta<0:self.assertEqual(r['calls'],[])
    else:self.assertEqual(r['calls'][0]['data'],'0x2e1a7d4d'+(10**15).to_bytes(32,'big').hex())

 def test_actual_terminal_payout_and_nested_returns(self):
  prefix=self.base()+'-after-1001007500000000000-unwrap-settle-paid-final-'
  for final in (1000007500000000000,1000010000000000000):
   for row in json.loads(Path(prefix+str(final)+'.json').read_text())['cases']:
    r=row['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);want=payout(10**18,final);c=r['calls'][0];self.assertEqual(want['data'],c['data']);self.assertEqual(want['to'],c['to'])
    for selector in ('0x128acb08','0x91dd7346','0x48c89491'):self.assertTrue(any(x['selector']==selector and x['result']=='Return' for x in r['execution_returns']))
