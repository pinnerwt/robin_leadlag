import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from nested_routers import ROUTER_426
from v3_calldata import decode,word

class Router426Tests(unittest.TestCase):
    def setUp(self):
        self.registry=json.loads((ROOT/'config/optimistic-router-template.json').read_text())
        self.fixtures=json.loads((ROOT/'tests/fixtures/router426.json').read_text())

    def parse(self,f,data=None,pools=None):
        return decode(ROUTER_426,data or f['tx']['data'],f['pools'] if pools is None else pools,set(),packed_registry=self.registry)

    def route_positions(self,f):
        raw=bytearray.fromhex(f['tx']['data'][2:]);outer=raw[4:]
        inner=4+word(outer,11)+32+4
        off=word(raw[inner:],8);base=inner+off+32
        n=word(raw[inner+off:],0)
        return raw,[base+word(raw[base:],i) for i in range(n)]

    def test_single_and_split_routes_match_real_logs(self):
        self.assertEqual({len(f['expected']) for f in self.fixtures},{1,2})
        for f in self.fixtures:self.assertEqual(self.parse(f),f['expected'])

    def test_unrecorded_first_leg_does_not_replace_second_with_total_amount(self):
        f=next(f for f in self.fixtures if len(f['expected'])==2)
        pools=copy.deepcopy(f['pools']);del pools[f['expected'][0]['pool']]
        self.assertEqual(self.parse(f,pools=pools),f['expected'][1:])
        self.assertEqual(self.parse(f,pools={}),[])

    def test_allocation_mismatch_is_not_ignored(self):
        f=self.fixtures[0];raw,positions=self.route_positions(f);p=positions[0]+64
        raw[p:p+32]=(1).to_bytes(32,'big')
        with self.assertRaisesRegex(ValueError,'allocations'):self.parse(f,data=raw)

    def test_unverified_adapter_is_not_assumed_unrecorded(self):
        f=self.fixtures[0];raw,positions=self.route_positions(f);raw[positions[0]:positions[0]+32]=(123).to_bytes(32,'big')
        with self.assertRaisesRegex(ValueError,'adapter'):self.parse(f,data=raw,pools={})

    def test_dependent_routes_reject_even_if_pool_not_recorded(self):
        f=self.fixtures[0];raw,positions=self.route_positions(f);p=positions[0]+32
        raw[p:p+32]=(123).to_bytes(32,'big')
        with self.assertRaisesRegex(ValueError,'dependent'):self.parse(f,data=raw,pools={})

    def test_other_outer_family_and_truncation_reject(self):
        f=self.fixtures[0]
        with self.assertRaisesRegex(ValueError,'outer selector'):self.parse(f,data='0x6abd02ce'+f['tx']['data'][10:])
        with self.assertRaises(ValueError):self.parse(f,data=f['tx']['data'][:250])

if __name__=='__main__':unittest.main()
