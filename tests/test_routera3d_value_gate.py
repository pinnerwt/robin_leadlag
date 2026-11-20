import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from routera3d_value_gate import sell_value_gate

class ValueGateTest(unittest.TestCase):
    def test_actual_parent_success_and_revert_values(self):
        fill=json.loads(Path('tests/fixtures/routera3d_v4_sell.json').read_text())['cases'][0]['result']
        cases=json.loads(Path('reports/amm/routera3d-value-gate-validation.json').read_text())['cases']
        self.assertEqual(len(cases),5)
        for c in cases:
            r=sell_value_gate(fill['amount0'],-fill['amount1'],c['price']*10**8,c['bps']<<176)
            self.assertEqual(r,dict(marked=c['marked'],delta=c['delta'],tolerance=c['tolerance'],passes=c['root_success']))
    def test_exact_allowance_boundary(self):
        # One ETH valued at 100 USDG; tolerance 10 USDG plus ten raw units.
        marked=100*10**6;allowance=marked//10+10
        self.assertTrue(sell_value_gate(10**18,marked-allowance,100*10**8,1000<<176)['passes'])
        self.assertFalse(sell_value_gate(10**18,marked-allowance-1,100*10**8,1000<<176)['passes'])
    def test_unmodeled_inputs_reject(self):
        for args in [(0,1,1,0),(1,1,0,0),(1,1,1,1001<<176),(-1,1,1,0)]:
            with self.assertRaises(ValueError):sell_value_gate(*args)

if __name__=='__main__':unittest.main()
