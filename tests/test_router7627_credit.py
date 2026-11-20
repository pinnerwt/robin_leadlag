import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_credit import *
from bootstrap_state import hashhex,word
class CreditTest(unittest.TestCase):
 def test_actual_transient_keys(self):
  self.assertEqual(hashhex(word(int(ROUTER,16))+word(0))[2:],NATIVE_SLOT);self.assertEqual(hashhex(word(int(ROUTER,16))+word(int(USDG,16)))[2:],USDG_SLOT)
  name='reports/amm/router7627-local-getters-shift-50-inventory-1000000000000000000-unlock-synthetic-fill-v3-transfer-balance-native--1000000000000000.json'
  for row in json.loads(Path(name).read_text())['cases']:self.assertEqual(row['result']['calls'][0]['data'],'0xf135baaa'+USDG_SLOT)
 def test_actual_credit_withdrawal(self):
  name='reports/amm/router7627-local-getters-shift-50-inventory-1000000000000000000-unlock-synthetic-fill-v3-transfer-balance-native--1000000000000000-usdg-2000000.json'
  for row in json.loads(Path(name).read_text())['cases']:
   r=row['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);want=take_usdg(row['synthetic_usdg_delta']);call=r['calls'][0];self.assertEqual(want['data'],call['data']);self.assertEqual(want['to'],call['to'])

 def test_actual_repayment_call_order(self):
  prefix='reports/amm/router7627-local-getters-shift-50-inventory-1000000000000000000-unlock-synthetic-fill-v3-transfer-balance-native--1000000000000000-usdg-2000000-take-after-1001007500000000000-unwrap'
  for row in json.loads(Path(prefix+'-settle.json').read_text())['cases']:
   r=row['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);calls=r['execution_calls'];cursor=0
   for want in repayment_calls(10**15,2000000):
    matches=[i for i,c in enumerate(calls) if i>=cursor and c['to']==want['to'] and c['data']==want['data'] and int(c['value'])==want['value']];self.assertTrue(matches);cursor=matches[0]+1
   self.assertEqual(r['calls'][0]['data'],repayment_calls(10**15,2000000)[-1]['data'])
  for row in json.loads(Path(prefix+'.json').read_text())['cases']:
   call=row['result']['calls'][0];self.assertEqual(call['data'],'0x11da60b4');self.assertEqual(int(call['value']),10**15)

 def test_reverse_take_uses_actual_transient_credit(self):
  name='reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4-transient.json'
  for row in json.loads(Path(name).read_text())['cases']:
   self.assertTrue(row['actual_v4_transient']);self.assertIsNone(row['synthetic_native_delta']);self.assertIsNone(row['synthetic_usdg_delta'])
   r=row['result'];self.assertIsNone(r['error'])
   swap=next(c for c in r['execution_returns'] if c['selector']=='0xf3cd914c' and c['result']=='Return')
   credit=int.from_bytes(bytes.fromhex(swap['output'][2:])[:16],'big',signed=True)
   reads=[c for c in r['execution_returns'] if c['selector']=='0xf135baaa'];self.assertEqual(len(reads),1);self.assertEqual(reads[0]['result'],'Return');self.assertEqual(int(reads[0]['output'],16),credit)
   want=take_native(credit);actual=r['calls'][0];self.assertEqual(actual['to'],want['to']);self.assertEqual(actual['data'],want['data']);self.assertFalse(r['execution_success'])
  for value in (0,-1,1<<127,True):
   with self.assertRaises(ValueError):take_native(value)

 def test_actual_native_take_then_wrap(self):
  name='reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4-transient-actual-take.json'
  for row in json.loads(Path(name).read_text())['cases']:
   self.assertTrue(row['actual_v4_take']);self.assertFalse(row['synthetic_take_success'])
   r=row['result'];self.assertIsNone(r['error'])
   returned=[c for c in r['execution_returns'] if c['selector']=='0x0b0d9c09'];self.assertEqual(len(returned),1);self.assertEqual(returned[0]['result'],'Stop')
   receive=[c for c in r['execution_calls'] if c['to']==ROUTER and c['data']=='0x'];self.assertEqual(len(receive),1)
   credit=int(receive[0]['value']);self.assertGreater(credit,0)
   actual=r['calls'][0];want=wrap_native(credit)
   self.assertEqual(actual['to'],want['to']);self.assertEqual(actual['data'],want['data']);self.assertEqual(int(actual['value']),want['value']);self.assertFalse(r['execution_success'])

 def test_deposit_gap_is_router_weth_balance(self):
  from bootstrap_state import mapping
  slot=mapping(int(ROUTER,16),0x33)
  getter=json.loads(Path('reports/amm/router7627-weth-balance-slot.json').read_text())
  deposit=json.loads(Path('reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4-transient-actual-take-deposit.json').read_text())
  for result in [getter['result']]+[row['result'] for row in deposit['cases']]:
   self.assertIn('unknown slot',result['error']);self.assertTrue(result['error'].endswith(slot))
   matching=[h for h in result['hash_preimages'] if h['hash']==slot];self.assertEqual(len(matching),1)
   self.assertEqual(matching[0]['preimage'],'0x'+int(ROUTER,16).to_bytes(32,'big').hex()+(0x33).to_bytes(32,'big').hex())
   self.assertIsNone(result['execution_success'])

 def test_deposit_storage_deltas_and_sync_dependency(self):
  token='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
  prefix='reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4-transient-actual-take-deposit-seed-inventory'
  for suffix in ('','-sync'):
   for row in json.loads(Path(prefix+suffix+'.json').read_text())['cases']:
    r=row['result'];self.assertIsNone(r['error']);credit=int(next(c for c in r['execution_calls'] if c['data']=='0xd0e30db0')['value'])
    writes={w['slot']:int(w['value'],16) for w in r['storage_writes'] if w['address']==token}
    self.assertEqual(writes['0x35'],int(seed['accounts'][token]['storage']['0x35'],16)+credit)
    self.assertEqual(writes['0x95d0bd652bf16a514a6cceccc328a4f34e8f6e1eb7feb07492942361a296b60a'],row['synthetic_weth_storage_inventory']+credit)
    returned=[c for c in r['execution_returns'] if c['selector']=='0xd0e30db0'];self.assertTrue(returned);self.assertTrue(all(c['result'] in ('Return','Stop') for c in returned))
    c=r['calls'][0]
    if suffix:
     self.assertEqual(c['to'],USDG);self.assertEqual(c['data'],'0x70a08231'+int(MANAGER,16).to_bytes(32,'big').hex())
    else:
     self.assertEqual(c['to'],MANAGER);self.assertEqual(c['data'],'0xa5841194'+int(USDG,16).to_bytes(32,'big').hex())
    self.assertFalse(r['execution_success'])

 def test_actual_usdg_sync_and_payment_dependency(self):
  prefix='reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4-transient-actual-take-deposit-seed-inventory-sync-usdg-balance'
  for row in json.loads(Path(prefix+'.json').read_text())['cases']:
   r=row['result'];self.assertIsNone(r['error']);returns=[c for c in r['execution_returns'] if c['selector']=='0xa5841194'];self.assertEqual(len(returns),1);self.assertIn(returns[0]['result'],('Stop','Return'))
   swap=next(c for c in r['execution_returns'] if c['selector']=='0xf3cd914c' and c['result']=='Return');debt=-int.from_bytes(bytes.fromhex(swap['output'][2:])[16:],'big',signed=True)
   c=r['calls'][0];self.assertEqual(c['to'],USDG);self.assertEqual(c['data'],'0xa9059cbb'+int(MANAGER,16).to_bytes(32,'big').hex()+debt.to_bytes(32,'big').hex());self.assertFalse(r['execution_success'])
  from bootstrap_state import mapping
  slot=mapping(int(ROUTER,16),6)
  for row in json.loads(Path(prefix+'-usdg-pay.json').read_text())['cases']:
   r=row['result'];self.assertTrue(r['error'].endswith(slot));self.assertIn('unknown slot',r['error'])
   hashes=[h for h in r['hash_preimages'] if h['hash']==slot];self.assertEqual(len(hashes),1);self.assertEqual(hashes[0]['storage_address'],USDG);self.assertIsNone(r['execution_success'])

 def test_usdg_slot6_transfer_gate(self):
  from bootstrap_state import mapping
  report=json.loads(Path('reports/amm/router7627-usdg-transfer-flag.json').read_text());cases={c['synthetic_flag']:c['result'] for c in report['cases']}
  self.assertTrue(cases[None]['error'].endswith(mapping(int(ROUTER,16),6)))
  self.assertIsNone(cases[1]['error']);self.assertFalse(cases[1]['execution_success']);self.assertEqual(cases[1]['output'],'0x1fd1cc44')
  for flag in (0,256):
   self.assertTrue(cases[flag]['error'].endswith(mapping(int(ROUTER,16),1)));self.assertIsNone(cases[flag]['execution_success'])

 def test_actual_settlement_and_inventory_reject_loss(self):
  prefix='reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4-transient-actual-take-deposit-seed-inventory-sync-usdg-balance-usdg-pay-usd-4548949483-settled-actual-inv.json'
  for row in json.loads(Path(prefix).read_text())['cases']:
   r=row['result'];self.assertIsNone(r['error']);self.assertFalse(r['execution_success']);self.assertEqual(r['calls'],[])
   self.assertTrue(row['actual_inventory']);self.assertTrue(row['actual_settle']);self.assertFalse(row['synthetic_settle_success'])
   settled=[c for c in r['execution_returns'] if c['selector']=='0x11da60b4'];self.assertEqual(len(settled),1);self.assertEqual(settled[0]['result'],'Return');self.assertEqual(int(settled[0]['output'],16),row['synthetic_usdg_storage_balance'])
   swap=next(c for c in r['execution_returns'] if c['selector']=='0xf3cd914c' and c['result']=='Return');credit=int.from_bytes(bytes.fromhex(swap['output'][2:])[:16],'big',signed=True)
   callback=next(c for c in r['execution_calls'] if c['data'].startswith('0xfa461e33'));owed=int(callback['data'][10:74],16);self.assertLess(credit,owed)
   balances=[int(c['output'],16) for c in r['execution_returns'] if c['selector']=='0x70a08231' and c['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and c['result']=='Return']
   self.assertEqual(balances[-1],row['synthetic_weth_storage_inventory']+credit)
   self.assertEqual(r['output'],'0x88215f9c'+(0).to_bytes(32,'big').hex()+(7500000000000).to_bytes(32,'big').hex())
