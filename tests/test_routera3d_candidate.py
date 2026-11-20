import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from routera3d_candidate import Candidate,USDG,WETH,POOLS
from routera3d_price import PRICE_XOR

class CandidateTest(unittest.TestCase):
    def setUp(self):
        self.seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
        self.inv=dict(anchor_hash=self.seed['anchor']['hash'],balances={USDG:10**13,WETH:0})
        self.model=Candidate(self.seed,self.inv)
    def calldata(self,exponent=17,second=0x19):
        f=json.loads(Path('tests/fixtures/routera3d_price.json').read_text())[0]
        raw=bytearray.fromhex(f['calldata'][2:]); raw[0]=0xe2
        raw[1:6]=int(f'{1900000000 ^ PRICE_XOR:040b}'[::-1],2).to_bytes(5,'big')
        raw[6:9]=((65536<<7)|exponent).to_bytes(3,'big')
        return '0x'+(raw[:13]+bytes([0x09,0xf6,second,0xf6,0,5])).hex()
    def test_expired_or_far_future_envelope_never_updates_state(self):
        data=self.calldata();target=int.from_bytes(bytes.fromhex(data[2:])[9:13],'big')
        before=copy.deepcopy((self.model.states,self.model.inventory))
        for block in (target+1,target-4):
            with self.assertRaisesRegex(ValueError,'outside block window'):
                self.model.preview(data,block=block,router_slot9=3<<144)
        self.assertEqual((self.model.states,self.model.inventory),before)
    def test_partial_fill_debits_actual_spend_and_never_commits(self):
        before=copy.deepcopy((self.model.states,self.model.inventory))
        out=self.model.preview(self.calldata(24))
        self.assertTrue(all(f['result']['unfilled']>0 for f in out['fills']))
        actual=sum(f['result']['amount1'] for f in out['fills'])
        requested=sum(f['amount'] for f in out['fills'])
        self.assertLess(actual,requested)
        self.assertEqual(out['inventory'][USDG],10**13-actual)
        self.assertEqual((self.model.states,self.model.inventory),before)
        self.assertFalse(out['state_complete'])
    def test_second_failure_does_not_mutate_first_pool(self):
        self.model.states[POOLS[1][0]].bitmap={}
        before=copy.deepcopy((self.model.states,self.model.inventory))
        with self.assertRaisesRegex(ValueError,'unknown bitmap'):
            self.model.preview(self.calldata())
        self.assertEqual((self.model.states,self.model.inventory),before)
    def test_reused_pool_observes_first_fill(self):
        out=self.model.preview(self.calldata(second=0x09))
        first,second=out['fills']
        self.assertEqual(first['pool'],second['pool'])
        self.assertEqual(first['inventory_after'],second['inventory_before'])
        self.assertLess(-second['result']['amount0'],-first['result']['amount0'])
        self.assertGreater(second['result']['sqrt'],first['result']['sqrt'])
    def test_missing_route_pool_cannot_be_skipped(self):
        seed=copy.deepcopy(self.seed)
        seed['pools']=[p for p in seed['pools'] if p['pool']!=POOLS[1][0]]
        with self.assertRaisesRegex(ValueError,'even when not recorded'):
            Candidate(seed,self.inv).preview(self.calldata())
    def test_anchor_and_unknown_descriptor_reject(self):
        with self.assertRaises(ValueError):
            Candidate(self.seed,dict(self.inv,anchor_hash='different'))
        with self.assertRaisesRegex(ValueError,'unverified route'):
            self.model.preview(self.calldata(second=0x49))

class V4CandidateTest(unittest.TestCase):
    setUp=CandidateTest.setUp
    calldata=CandidateTest.calldata
    def model_with_v4(self):
        from routera3d_v4 import POOL_ID
        fixture=json.loads(Path('tests/fixtures/routera3d_v4_math.json').read_text())
        v4=dict(anchor_hash=self.seed['anchor']['hash'],pool_id=POOL_ID,state=fixture['state'],hook_fee_ppm=40)
        return Candidate(self.seed,self.inv,v4),fixture
    def test_v3_then_v4_prices_inventory_and_nonmutation(self):
        model,fixture=self.model_with_v4()
        before=copy.deepcopy((model.states,model.inventory))
        for case in fixture['cases']:
            result=model.preview(self.calldata(case['exponent'],0x69))
            first,second=result['fills']
            self.assertEqual(second['result'],case['result'])
            self.assertEqual(second['inventory_before'],first['inventory_after'])
            self.assertEqual(result['inventory'][WETH],sum(-x['result']['amount0'] for x in result['fills']))
            self.assertEqual(result['inventory'][USDG],10**13-sum(x['result']['amount1'] for x in result['fills']))
            self.assertFalse(result['state_complete'])
        self.assertEqual((model.states,model.inventory),before)
    def test_v4_sell_settlement_inventory_and_no_commit(self):
        fixture=json.loads(Path('tests/fixtures/routera3d_v4_sell.json').read_text())
        old_model,_=self.model_with_v4();v4=copy.deepcopy(old_model.v4_seed);v4['sell_hook_fee_ppm']=160
        inv=copy.deepcopy(self.inv);inv['balances']={WETH:10**18,USDG:10**12}
        model=Candidate(self.seed,inv,v4);before=copy.deepcopy((model.states,model.inventory))
        for case in fixture['cases']:
            result=model.preview(case['calldata']);fill=result['fills'][0]
            self.assertEqual(fill['result'],case['result'])
            self.assertTrue(fill['native_unwrapped']);self.assertFalse(fill['native_wrapped'])
            self.assertEqual(result['inventory'][WETH],10**18-case['result']['amount0'])
            self.assertEqual(result['inventory'][USDG],10**12-case['result']['amount1'])
            self.assertFalse(result['state_complete'])
        self.assertEqual((model.states,model.inventory),before)
        with self.assertRaisesRegex(ValueError,'sell hook fee'):old_model.preview(fixture['cases'][0]['calldata'])
    def test_dynamic_v4_pool_inventory_and_hook_rollback(self):
        from routera3d_hook import DEFAULT_CONFIG
        from routera3d_v4 import POOL_ID
        cases=json.loads(Path('reports/amm/routera3d-dynamic-limits-probe.json').read_text())['cases']
        for case in cases:
            old,_=self.model_with_v4();v4=copy.deepcopy(old.v4_seed)
            v4.update(hook_state=int(case['state'],16),hook_config=DEFAULT_CONFIG)
            inv=copy.deepcopy(self.inv);inv['balances']={WETH:10**18,USDG:10**12}
            model=Candidate(self.seed,inv,v4)
            before=copy.deepcopy((model.states,model.inventory,model.v4_seed))
            result=model.preview(case['calldata'],block=case['block'])
            fill=result['fills'][0]
            self.assertEqual(fill['limit'],case['actual_limit'])
            self.assertEqual(result['states'][POOL_ID].fee,case['fee'])
            returned=next(x for x in case['result']['execution_returns'] if x['selector']=='0xf3cd914c')
            self.assertEqual(returned['result'],'Return')
            n=int(returned['output'],16);d0=n>>128;d1=n&((1<<128)-1)
            d0=d0-(1<<128) if d0>>127 else d0;d1=d1-(1<<128) if d1>>127 else d1
            self.assertEqual((fill['result']['amount0'],fill['result']['amount1']),(-d0,-d1))
            self.assertEqual(result['inventory'],{WETH:10**18+d0,USDG:10**12+d1})
            writes=[x for x in case['result']['storage_writes'] if x['address']=='0x987e330f00b79864a07fe81dfac344d0078abcc0']
            self.assertEqual(result['hook_state'],int(writes[-1]['value'],16) if writes else v4['hook_state'])
            self.assertEqual((model.states,model.inventory,model.v4_seed),before)
            with self.assertRaisesRegex(ValueError,'explicit V4 block'):model.preview(case['calldata'])
            # Hook transition executes before a missing curve dependency;
            # none of it may leak back into the original preview model.
            model.states[POOL_ID].bitmap={};broken=copy.deepcopy((model.states,model.inventory,model.v4_seed))
            with self.assertRaisesRegex(ValueError,'unknown bitmap'):model.preview(case['calldata'],block=case['block']+1)
            self.assertEqual((model.states,model.inventory,model.v4_seed),broken)
    def test_repeated_v4_requires_hook_transition(self):
        model,_=self.model_with_v4()
        raw=bytearray.fromhex(self.calldata(10,0x69)[2:]);raw[13]=0x69
        with self.assertRaisesRegex(ValueError,'hook state transition'):model.preview('0x'+raw.hex())
    def test_missing_v4_bitmap_rolls_back_entire_preview(self):
        from routera3d_v4 import POOL_ID
        model,_=self.model_with_v4();model.states[POOL_ID].bitmap={}
        before=copy.deepcopy((model.states,model.inventory))
        with self.assertRaisesRegex(ValueError,'unknown bitmap'):model.preview(self.calldata(10,0x69))
        self.assertEqual((model.states,model.inventory),before)
    def test_v4_requires_seed_and_matching_anchor(self):
        with self.assertRaisesRegex(ValueError,'V4 route state required'):self.model.preview(self.calldata(10,0x69))
        model,_=self.model_with_v4();v4=model.v4_seed;v4['anchor_hash']='bad'
        with self.assertRaisesRegex(ValueError,'matching V4'):Candidate(self.seed,self.inv,v4)

if __name__=='__main__':unittest.main()
