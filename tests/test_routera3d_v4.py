import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from routera3d_v4 import reverse_intent,forward_intent,dynamic_intent,settled_inventory,WETH,USDG
from v3_calldata import word,signed

class V4Test(unittest.TestCase):
    def test_real_manager_call_and_settlement_fixtures(self):
        for exponent in (8,10,12,14):
            d=json.loads(Path(f'reports/amm/routera3d-index6-probe-{exponent}-settlement.json').read_text())
            amount=65536<<exponent;spent=min(10**9,amount//2)
            intent=reverse_intent(d['transaction']['data'],1,10**12-spent,hook_fee_ppm=40)
            call=next(x for x in d['result']['execution_calls'] if x['data'].startswith('0xf3cd914c'))
            raw=bytes.fromhex(call['data'][10:])
            self.assertEqual(intent['amount'],signed(word(raw,6)))
            self.assertEqual(intent['limit'],word(raw,7))
            self.assertEqual(int(intent['currency0'],16),word(raw,0))
            self.assertEqual(int(intent['currency1'],16),word(raw,1))
            self.assertEqual(intent['fee'],word(raw,2))
            self.assertEqual(intent['tick_spacing'],word(raw,3))
            self.assertEqual(int(intent['hooks'],16),word(raw,4))
            self.assertEqual(intent['zero'],bool(word(raw,5)))
            native=int(d['synthetic_transfers'][0]['data'][-64:],16)
            before={WETH:spent*600000000,USDG:10**12-spent}
            after=settled_inventory(before,native,-amount)
            self.assertEqual(after[WETH],before[WETH]+native)
            self.assertEqual(after[USDG],before[USDG]-amount)
            self.assertEqual(before[USDG],10**12-spent)
    def test_forward_intent_and_curve_fixtures(self):
        from v3_state import State
        fixture=json.loads(Path('tests/fixtures/routera3d_v4_sell.json').read_text())
        self.assertEqual(len(fixture['cases']),6)
        for case in fixture['cases']:
            intent=forward_intent(case['calldata'],0,10**18,hook_fee_ppm=160)
            self.assertEqual(intent,case['intent'])
            state=State.load(fixture['state']);state.fee=160
            self.assertEqual(state.swap(True,-intent['amount'],intent['limit']),case['result'])
            with self.assertRaisesRegex(ValueError,'sell hook fee'):
                forward_intent(case['calldata'],0,10**18,hook_fee_ppm=40)
    def test_dynamic_router_limits_match_actual_bytecode(self):
        from routera3d_hook import DEFAULT_CONFIG
        cases=json.loads(Path('reports/amm/routera3d-dynamic-limits-probe.json').read_text())['cases']
        self.assertEqual(len(cases),6)
        for case in cases:
            intent=dynamic_intent(case['calldata'],0,10**18 if case['zero'] else 10**12,
                hook_state=int(case['state'],16),hook_config=DEFAULT_CONFIG,sqrt=case['sqrt'],block=case['block'])
            raw=bytes.fromhex(next(x for x in case['result']['execution_calls'] if x['data'].startswith('0xf3cd914c'))['data'][10:])
            self.assertEqual(intent['amount'],signed(word(raw,6)))
            self.assertEqual(intent['limit'],word(raw,7))
            self.assertEqual(intent['hook_fee_ppm'],case['fee'])
            self.assertFalse(intent['state_complete'])
    def test_unknown_fee_direction_and_balances_reject(self):
        d=json.loads(Path('reports/amm/routera3d-index6-probe-10-settlement.json').read_text())['transaction']['data']
        for fee in (None,0,41):
            with self.assertRaises(ValueError):reverse_intent(d,1,10**12,hook_fee_ppm=fee)
        with self.assertRaises(ValueError):reverse_intent(d,0,10**12,hook_fee_ppm=40)
        for inv,a,b in [({},1,-1),({WETH:0,USDG:0},1,-1),({WETH:0,USDG:1},-1,1),({WETH:(1<<256)-1,USDG:1},1,-1)]:
            with self.assertRaises(ValueError):settled_inventory(inv,a,b)

if __name__=='__main__':unittest.main()
