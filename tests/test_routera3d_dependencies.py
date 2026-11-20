import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_routera3d_dependencies import classify, ROUTE_POOLS


class DependencyTest(unittest.TestCase):
    def data(self,indices):
        fixture=json.loads(Path('tests/fixtures/routera3d_price.json').read_text())[0]
        raw=bytearray.fromhex(fixture['calldata'][2:]);raw[0]=0x40|len(indices)
        descriptors=b''.join(bytes([index<<4|9,246]) for index in indices)
        mask=sum(1<<(2*i) for i in range(len(indices))).to_bytes(2,'big')
        return '0x'+(raw[:13]+descriptors+mask+(b'\x00\xbb' if 4 in indices else b'')).hex()

    def test_trailing_vs_upstream_and_unknown(self):
        recorded={ROUTE_POOLS[0],ROUTE_POOLS[1]}
        for indices,category in [([0],'recorded_only'),([0,4,6],'recorded_with_unrecorded_suffix'),
                                 ([0,4,1],'unrecorded_before_recorded'),([0,3],'unknown_route_identity'),
                                 ([4,6],'only_unrecorded')]:
            with self.subTest(indices=indices):
                r=classify(self.data(indices),recorded)
                self.assertEqual(r['category'],category)
                self.assertFalse(r['continuous_inventory_complete'])
        self.assertEqual(classify(self.data([0,4,1]),recorded)['upstream_unrecorded'],[1])

    def test_recorded_set_changes_relevance(self):
        r=classify(self.data([0,4]),{ROUTE_POOLS[0],ROUTE_POOLS[4]})
        self.assertEqual(r['category'],'recorded_only')
        self.assertEqual(r['fee_hint'],dict(limit_fee_hint_ppm=187,fallback_required=False))
        r=classify(self.data([0,4,3]),{ROUTE_POOLS[0]})
        self.assertEqual(r['category'],'unknown_route_identity')
        self.assertEqual(r['unknown_identity'],[2])

    def test_new_identities_and_both_direction_bounds_from_bytecode(self):
        from routera3d_price import reverse_v3_limit,forward_v3_limit
        cases=json.loads(Path('reports/amm/routera3d-identities-probe.json').read_text())['cases']
        selected=[c for c in cases if c['index'] in (2,5)]
        self.assertEqual(len(selected),4)
        for c in selected:
            r=c['result'];self.assertIsNone(r['error'])
            call=r['calls'][0];self.assertEqual(len(r['calls']),1)
            data=bytes.fromhex(call['data'][10:])
            words=[int.from_bytes(data[i:i+32],'big') for i in range(0,len(data),32)]
            if c['index']==2:
                self.assertEqual(call['to'],'0x8366a39cc670b4001a1121b8f6a443a643e40951')
                self.assertEqual(call['data'][:10],'0x48c89491')
                preimage=ROUTE_POOLS[2]+(6).to_bytes(32,'big').hex()
                self.assertTrue(any(h['preimage']==preimage for h in r['hash_preimages']))
                amount,limit=words[5:7];selector='0x15452022';fee=700
            else:
                self.assertEqual(call['to'],ROUTE_POOLS[5])
                self.assertEqual(call['data'][:10],'0x128acb08')
                amount,limit=words[2:4];selector='0xddca3f43';fee=300
            fees=[int(x['output'],16) for x in r['execution_returns'] if x['selector']==selector]
            self.assertTrue(fees);self.assertEqual(set(fees),{fee})
            price=1900000000 if c['side']==1 else 1750000000
            expected=(reverse_v3_limit if c['side']==1 else forward_v3_limit)(price,10,fee,10)
            self.assertEqual(limit,expected)
            self.assertEqual(amount,16777216 if c['side']==1 else 16777216*10**18//(price*99990//100000))
