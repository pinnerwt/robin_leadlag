import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_swap_scope import classify, dependency_scope, SWAP, A3D

POOL = '0x' + '11' * 20
TX = dict(to='0x'+'22'*20, data='0x12345678')
LOG = dict(address=POOL, topics=[SWAP])

class SwapScopeTest(unittest.TestCase):
    def test_route_scope_never_promotes_numeric_coverage(self):
        tx = dict(to=A3D, data='0x12345678')
        scope = dict(category='only_unrecorded')
        with patch('audit_swap_scope.route_scope', return_value=scope), patch('audit_swap_scope.decode', side_effect=ValueError('unknown')):
            self.assertEqual(dependency_scope(tx, {POOL: {}}), scope)
            self.assertEqual(classify(tx, [LOG], {POOL: {}}, {})['status'], 'recorded_pool_unresolved')
        self.assertIsNone(dependency_scope(TX, {POOL: {}}))
        self.assertIsNone(dependency_scope(tx, {POOL: {}}))

    def test_unknown_without_logs_is_not_unrecorded(self):
        with patch('audit_swap_scope.decode', side_effect=ValueError('unknown')):
            assert classify(TX, [], {POOL: {}}, {})['status'] == 'scope_unknown'
    
    def test_verified_unrecorded_route_must_not_contradict_logs(self):
        with patch('audit_swap_scope.decode', return_value=[]):
            assert classify(TX, [], {POOL: {}}, {})['status'] == 'verified_decoder_no_recorded_operation'
            assert classify(TX, [LOG], {POOL: {}}, {})['status'] == 'recorded_pool_missing_from_decoder'
    
    def test_partial_callback_is_not_complete(self):
        with patch('audit_swap_scope.decode', return_value=[dict(pool=POOL, coverage_note='callback')]):
            assert classify(TX, [LOG], {POOL: {}}, {})['status'] == 'recorded_pool_partial'

    def test_actual0480_routes_remain_numeric_unresolved(self):
        metadata=json.loads(Path('reports/amm/router0480-v2-tokens.json').read_text())
        v2={metadata['pool']:dict(tokens=['0x'+metadata['getters'][k]['output'][-40:] for k in ('token0','token1')])}
        recorded='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca';count=0
        for line in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines():
            row=json.loads(line);tx=row['tx']
            if (tx.get('to') or '').lower()!='0x0480bafac5547926e8697de90d124b97d4a13f75':continue
            count+=1;scope=dependency_scope(tx,{recorded:{}},v2)
            self.assertEqual(scope['recorded_pools'],[recorded]);self.assertFalse(scope['safe_to_skip']);self.assertFalse(scope['execution_complete'])
            self.assertEqual(classify(tx,row['logs'],{recorded:{}},{})['status'],'recorded_pool_unresolved')
            absent=dependency_scope(tx,{},v2);self.assertEqual(absent['category'],'0480_structural_no_recorded_identity');self.assertFalse(absent['safe_to_skip'])
        self.assertEqual(count,15)

    def test_unknown0480_is_not_classified(self):
        self.assertIsNone(dependency_scope(dict(to='0x0480bafac5547926e8697de90d124b97d4a13f75',data='0x12345678'),{}))
