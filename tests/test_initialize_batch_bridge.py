import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from initialize_batch_bridge import initialize,HOOK
from delegated_batch_preview import preview_raw
class InitializeBatchBridgeTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());cls.quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
  cls.data=next(t['data'] for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['tx'].startswith('0x99fa4228'))
  cls.inventory=dict(anchor=cls.seed['anchor']['hash'],weth_balance=0,native_balance=0,usdg_balance=0)
 def test_direct_initialization_to_raw_preview(self):
  params=initialize(self.seed,self.quotes,self.data,inventory=self.inventory,transaction_target='0xd261e95ffed263a7d63a357ff0e67a760ddec8c5')
  result=preview_raw(self.data,**params,assume_success=True)
  self.assertEqual(result['v3_fill']['amount1'],-1454595);self.assertEqual(result['hook_fee']['net'],796969091046830)
 def test_mixed_inventory_anchor_rejected(self):
  with self.assertRaisesRegex(ValueError,'checkpoint mismatch'):initialize(self.seed,self.quotes,self.data,inventory=dict(self.inventory,anchor='different'),transaction_target='0xd261e95ffed263a7d63a357ff0e67a760ddec8c5')
 def test_changed_hook_code_rejected(self):
  seed=copy.deepcopy(self.seed);seed['accounts'][HOOK]['code']='0x00'
  with self.assertRaisesRegex(ValueError,'code pin mismatch'):initialize(seed,self.quotes,self.data,inventory=self.inventory,transaction_target='0xd261e95ffed263a7d63a357ff0e67a760ddec8c5')
 def test_unsupported_hook_branch_rejected(self):
  seed=copy.deepcopy(self.seed);base='0xe18381f46b2c53f0e43ad1952216bbe3fb27345d4b2a467118dab1a305caa6f5';seed['accounts'][HOOK]['storage'][base]=hex(int(seed['accounts'][HOOK]['storage'][base],16)|256)
  with self.assertRaisesRegex(ValueError,'configuration branch'):initialize(seed,self.quotes,self.data,inventory=self.inventory,transaction_target='0xd261e95ffed263a7d63a357ff0e67a760ddec8c5')
 def test_every_nested_code_pin_is_checked(self):
  from initialize_batch_bridge import validate_router_pins,ROUTER_PINS
  target='0xd261e95ffed263a7d63a357ff0e67a760ddec8c5'
  self.assertEqual(validate_router_pins(self.seed,target.upper()),target)
  for address in ROUTER_PINS:
   accounts=dict(self.seed['accounts']);accounts[address]=dict(accounts[address],code='0x00')
   with self.assertRaisesRegex(ValueError,'router code pin mismatch'):validate_router_pins(dict(self.seed,accounts=accounts),target)
 def test_missing_or_changed_entry_delegation_rejected(self):
  from initialize_batch_bridge import validate_router_pins
  target='0xd261e95ffed263a7d63a357ff0e67a760ddec8c5'
  for code in ('0x','0xef0100'+'11'*20):
   accounts=dict(self.seed['accounts']);accounts[target]=dict(accounts[target],code=code)
   with self.assertRaisesRegex(ValueError,'entry delegation'):validate_router_pins(dict(self.seed,accounts=accounts),target)
