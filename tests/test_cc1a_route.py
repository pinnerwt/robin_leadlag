import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cc1a_route import plan,bind_output

class RouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tx=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith('0x741ba04c'))
    def test_first_call_matches_bytecode(self):
        op=plan(self.tx['data'])[0]
        c=json.loads(Path('reports/amm/routercc1-calldata-reads.jsonl').read_text())['calls'][0]
        raw=bytes.fromhex(c['data'][10:])
        self.assertEqual(op['pool'],c['to'])
        self.assertEqual(op['zero'],bool(int.from_bytes(raw[32:64],'big')))
        self.assertEqual(op['amount'],int.from_bytes(raw[64:96],'big',signed=True))
        self.assertEqual(op['limit'],int.from_bytes(raw[96:128],'big'))
    def test_dependent_amount_matches_callback_interventions(self):
        op=plan(self.tx['data'])[1]
        for case in json.loads(Path('reports/amm/routercc1-callback-probe.json').read_text())['cases']:
            c=case['result']['calls'][0];raw=bytes.fromhex(c['data'][10:])
            amount=bind_output(op,[dict(amount0=-case['synthetic_output'],unfilled=0)])
            self.assertEqual(op['pool'],c['to'])
            self.assertEqual(amount,int.from_bytes(raw[64:96],'big'))
            self.assertEqual(op['zero'],bool(int.from_bytes(raw[32:64],'big')))
    def test_partial_and_missing_results_rejected(self):
        op=plan(self.tx['data'])[1]
        for values in [[],[dict(amount0=-5,unfilled=1)],[dict(amount0=0,unfilled=0)]]:
            with self.assertRaises(ValueError):bind_output(op,values)
    def test_other_modes_and_truncation_rejected(self):
        raw=bytearray.fromhex(self.tx['data'][2:]);raw[10]=0x64
        for value in ['0x'+raw.hex(),self.tx['data'][:-2]]:
            with self.assertRaises(ValueError):plan(value)
if __name__=='__main__':unittest.main()
