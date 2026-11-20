import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from packed_routers import ROUTER_769,decode_packed
from v3_calldata import decode

class Router769Tests(unittest.TestCase):
    def setUp(self):
        self.registry=json.loads((ROOT/'config/optimistic-router-template.json').read_text())
        self.fixtures=json.loads((ROOT/'tests/fixtures/router769.json').read_text())

    def test_both_directions_match_archived_call_arguments(self):
        self.assertEqual({f['expected']['zero'] for f in self.fixtures},{False,True})
        for f in self.fixtures:
            op=decode_packed(ROUTER_769,f['tx']['data'],self.registry)[0]
            self.assertEqual({k:op[k] for k in f['expected']},f['expected'])
            self.assertIn('callback',op['coverage_note'])

    def test_nested_truncation_rejects(self):
        for f in self.fixtures:
            with self.assertRaises(ValueError):decode_packed(ROUTER_769,f['tx']['data'][:402],self.registry)

    def test_unknown_settlement_selector_rejects(self):
        data=self.fixtures[0]['tx']['data'].replace('67557586','deadbeef',1)
        with self.assertRaisesRegex(ValueError,'callback selector'):
            decode_packed(ROUTER_769,data,self.registry)

    def test_unrecorded_outer_pool_does_not_hide_unresolved_callback(self):
        f=self.fixtures[0]
        with self.assertRaisesRegex(ValueError,'unresolved callback'):
            decode(ROUTER_769,f['tx']['data'],{},set(),packed_registry=self.registry)

    def test_partial_evidence_is_not_silently_dropped_by_book(self):
        from amm_feed_state import Book
        from v3_state import Q96
        f=self.fixtures[0];pool=f['expected']['pool'];token0='0x'+'11'*20;token1='0x'+'22'*20
        p=dict(pool=pool,tokens=[token0,token1],base_token=token0,quote_token=token1,
               base_index=0,decimals=[18,18],fee=500,spacing=1,sqrt=str(Q96),tick=0,
               liquidity='0',bitmap={},ticks={})
        registry=dict(self.registry,anchor_hash='anchor')
        book=Book(dict(complete=True,anchor=dict(hash='anchor'),pools=[p]),registry,assume_success=True)
        book.proposal(f['tx'])
        self.assertIn(f['tx']['tx'],book.partial)
        self.assertIn('callback',book.partial[f['tx']['tx']][0])

if __name__=='__main__':unittest.main()
