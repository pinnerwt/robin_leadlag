import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from variant_v3_checkpoint import load as load_v3
from v4_pool_state import load as load_v4
from router7627_reverse_preview import preview
from router7627_calldata_preview import decode,CODE_HASH
from router7627_second_leg import POOL
from router7627_credit import MANAGER
class PreviewTest(unittest.TestCase):
 def test_two_pool_state_predictions_match_complete_evm(self):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());name='reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-obs-0-v4-transient-actual-take-deposit-seed-inventory-sync-usdg-balance-usdg-pay-usd-0-settled-actual-inv-state-shift-weth-pay-out.json'
  key=dict(currency0='0x'+'00'*20,currency1='0x5fc5360d0400a0fd4f2af552add042d716f1d168',fee=0x800000,tick_spacing=1,hooks='0x987e330f00b79864a07fe81dfac344d0078abcc0');slot='0xa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8'
  for row in json.loads(Path(name).read_text())['cases']:
   storage=copy.deepcopy(seed['accounts'][MANAGER]['storage']);storage[slot]=row['price_intervention']['synthetic']
   v3=load_v3(seed['accounts'][POOL]['storage'],100,1);v4=load_v4(storage,key,effective_lp_fee=40,bitmap_words=range(-788,-784));before=copy.deepcopy((v3,v4));r=row['result']
   call=next(c for c in r['execution_calls'] if c['data'].startswith('0x128acb08'));limit=int(call['data'][10+96*2:10+128*2],16)
   decoded=decode(row['tx']['to'],row['tx']['data'],row['tx']['timestamp'],v3,v4,code_hash=CODE_HASH);self.assertEqual(decoded['status'],'reverse_prediction');p=decoded['prediction'];self.assertEqual((v3,v4),before);self.assertEqual(p['v3_calldata'],call['data'])
   v4call=next(c for c in r['execution_calls'] if c['data'].startswith('0xf3cd914c'));self.assertEqual(p['v4_calldata'],v4call['data'])
   writes={(w['address'],w['slot']):int(w['value'],16) for w in r['storage_writes']}
   for address,base,liq,result in [(POOL,'0x0','0x4',p['v3']),(MANAGER,slot,hex(int(slot,16)+3),p['v4'])]:
    packed=writes[address,base];self.assertEqual(packed&((1<<160)-1),result['sqrt']);self.assertEqual((packed>>160)&((1<<24)-1),result['tick']%(1<<24))
    initial=seed['accounts'][address]['storage'][liq];self.assertEqual(writes.get((address,liq),int(initial,16)),result['liquidity'])
   self.assertEqual(p['gross_native_profit'],1137112724888458);self.assertTrue(p['profit_gate_passed']);self.assertFalse(p['execution_complete'])
   v4.fee=90
   with self.assertRaisesRegex(ValueError,'unverified fee'):preview(v3,v4,limit,15000)
