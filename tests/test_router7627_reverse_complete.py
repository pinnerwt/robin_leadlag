"""Complete execution of explicit counterfactual, not historical replay."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from bootstrap_state import mapping
from router7627_second_leg import ROUTER,POOL
from router7627_credit import USDG,MANAGER
class ReverseCompleteTest(unittest.TestCase):
 def test_actual_transfers_and_balance_conservation(self):
  name='reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-obs-0-v4-transient-actual-take-deposit-seed-inventory-sync-usdg-balance-usdg-pay-usd-0-settled-actual-inv-state-shift-weth-pay-out.json'
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
  weth='0x0bd7d308f8e1639fab988df18a8011f41eacad73';recipient='0xac6d42b13660fe34ffb1d79e54506530a7878418'
  for row in json.loads(Path(name).read_text())['cases']:
   r=row['result'];self.assertTrue(r['execution_success']);self.assertIsNone(r['error']);self.assertEqual(r['calls'],[])
   self.assertFalse(row['synthetic_v3_transfer']);self.assertFalse(row['synthetic_reverse_balance']);self.assertTrue(row['actual_usdg_output']);self.assertEqual(row['synthetic_usdg_storage_balance'],0)
   v3=next(c for c in r['execution_returns'] if c['selector']=='0x128acb08' and c['result']=='Return');raw=bytes.fromhex(v3['output'][2:]);owed=int.from_bytes(raw[:32],'big',signed=True);usdg=-int.from_bytes(raw[32:],'big',signed=True)
   v4=next(c for c in r['execution_returns'] if c['selector']=='0xf3cd914c' and c['result']=='Return');credit=int.from_bytes(bytes.fromhex(v4['output'][2:])[:16],'big',signed=True)
   final={(w['address'],w['slot']):int(w['value'],16) for w in r['storage_writes']}
   def delta(token,account,index):
    slot=mapping(int(account,16),index)
    return final[token,slot]-int(seed['accounts'][token]['storage'][slot],16)
   self.assertEqual(delta(USDG,POOL,1),-usdg);self.assertEqual(delta(USDG,MANAGER,1),usdg);self.assertEqual(final[USDG,mapping(int(ROUTER,16),1)],0)
   self.assertEqual(delta(weth,POOL,0x33),owed);self.assertEqual(delta(weth,recipient,0x33),credit-owed)
   self.assertEqual(final[weth,mapping(int(ROUTER,16),0x33)],row['synthetic_weth_storage_inventory']);self.assertGreater(credit-owed,7500000000000)
   self.assertTrue(any(c['selector']=='0x48c89491' and c['result']=='Return' for c in r['execution_returns']))
