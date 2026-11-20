import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from routera3d_hook import same_block_reverse_fee,small_upward_block_transition,default_upward_block_transition,default_block_transition,reverse_update,DEFAULT_CONFIG,forward_same_block_fee,forward_update,directional_fees

class HookTest(unittest.TestCase):
    def test_same_block_bytecode_interventions(self):
        cases=json.loads(Path('reports/amm/routera3d-hook-blocks-probe.json').read_text())['cases']
        first=json.loads(Path('reports/amm/routera3d-hook-fee-probe.json').read_text())['cases'][0]
        state=int(first['result']['storage_writes'][0]['value'],16)
        reference=(state>>40)&((1<<160)-1);base=(state>>200)&0xffffff
        config=int(first['config_before'],16);coefficient=(config>>48)&0xffffff;cap=(config>>72)&0xffffff
        tested=0
        for case in cases:
            if case['block_offset']:continue
            # Actual manager extsload return, independent of local fee formula.
            returns=[x for x in case['result']['execution_returns'] if x['selector']=='0x1e2eaeaf']
            self.assertTrue(returns)
            current=int(returns[0]['output'],16)&((1<<160)-1)
            self.assertEqual(same_block_reverse_fee(reference,current,base,coefficient,cap),case['fee_override']&0x3fffff)
            self.assertFalse(case['result']['storage_writes']);tested+=1
        self.assertEqual(tested,9)
    def test_cross_block_state_writes_and_unmodeled_carry(self):
        cases=json.loads(Path('reports/amm/routera3d-hook-blocks-probe.json').read_text())['cases']
        first=json.loads(Path('reports/amm/routera3d-hook-fee-probe.json').read_text())['cases'][0]
        before=int(first['result']['storage_writes'][0]['value'],16)
        tested=rejected=0
        for case in cases:
            if not case['block_offset']:continue
            after=int(case['result']['storage_writes'][0]['value'],16)
            block=after&((1<<40)-1);sqrt=(after>>40)&((1<<160)-1)
            if case['price_state'] in ('up_100','up_1000','up_49','up_50','up_51'):
                with self.assertRaisesRegex(ValueError,'carry branch'):small_upward_block_transition(before,sqrt,block)
                rejected+=1
            else:
                result=small_upward_block_transition(before,sqrt,block)
                self.assertEqual(result['after'],after)
                self.assertEqual(result['fee'],case['fee_override']&0x3fffff);tested+=1
        self.assertEqual((tested,rejected),(16,20))
    def test_default_upward_carry_threshold_and_expiry(self):
        cases=json.loads(Path('reports/amm/routera3d-hook-blocks-probe.json').read_text())['cases']
        first=json.loads(Path('reports/amm/routera3d-hook-fee-probe.json').read_text())['cases'][0]
        before=int(first['result']['storage_writes'][0]['value'],16);count=0
        for case in cases:
            if not case['block_offset']:continue
            after=int(case['result']['storage_writes'][0]['value'],16)
            result=default_upward_block_transition(before,(after>>40)&((1<<160)-1),after&((1<<40)-1))
            self.assertEqual(result['after'],after)
            general=default_block_transition(before,(after>>40)&((1<<160)-1),after&((1<<40)-1))
            self.assertEqual(general['after'],after)
            self.assertEqual(general['fee'],result['fee'])
            self.assertEqual(result['fee'],case['fee_override']&0x3fffff);count+=1
        self.assertEqual(count,36)
        with self.assertRaisesRegex(ValueError,'initial hook profile'):
            default_upward_block_transition(before|(1<<224),1,1)
    def test_sequential_cross_block_transitions(self):
        cases=json.loads(Path('reports/amm/routera3d-hook-sequence-probe.json').read_text())['cases'];count=0
        previous=None
        for case in cases:
            if previous is not None:self.assertEqual(case['before'],previous)
            previous=case['after'];before=int(case['before'],16)
            if case['block']==before&((1<<40)-1):continue
            result=default_block_transition(before,case['sqrt'],case['block'])
            self.assertEqual(result['after'],int(case['after'],16))
            self.assertEqual(result['fee'],case['fee']);count+=1
        self.assertEqual(count,7)
    def test_unified_reverse_sequence_and_sameblock_matrix(self):
        sequence=json.loads(Path('reports/amm/routera3d-hook-sequence-probe.json').read_text())['cases']
        for case in sequence:
            result=reverse_update(int(case['before'],16),DEFAULT_CONFIG,case['sqrt'],case['block'])
            self.assertEqual(result['after'],int(case['after'],16))
            self.assertEqual(result['fee'],case['fee'])
        cases=json.loads(Path('reports/amm/routera3d-hook-sameblock-probe.json').read_text())['cases']
        self.assertEqual(len(cases),21)
        for case in cases:
            state=int(case['state'],16);block=state&((1<<40)-1)
            result=reverse_update(state,DEFAULT_CONFIG,case['sqrt'],block)
            self.assertEqual(result['fee'],case['fee'])
            self.assertEqual(result['after'],state)
            self.assertFalse(result['write_required'])
            with self.assertRaisesRegex(ValueError,'config'):reverse_update(state,0,case['sqrt'],block)
            with self.assertRaisesRegex(ValueError,'block order'):reverse_update(state,DEFAULT_CONFIG,case['sqrt'],block-1)
    def test_forward_sameblock_matrix(self):
        cases=json.loads(Path('reports/amm/routera3d-hook-sameblock-forward-probe.json').read_text())['cases']
        self.assertEqual(len(cases),21)
        for case in cases:
            state=int(case['state'],16);block=state&((1<<40)-1)
            result=forward_same_block_fee(state,DEFAULT_CONFIG,case['sqrt'],block)
            self.assertEqual(result['fee'],case['fee'])
            self.assertEqual(result['after'],state)
            self.assertFalse(result['write_required'])
        with self.assertRaisesRegex(ValueError,'cross-block'):
            forward_same_block_fee(state,DEFAULT_CONFIG,case['sqrt'],block+1)
    def test_forward_sequence_and_independent_directional_quotes(self):
        forward=json.loads(Path('reports/amm/routera3d-hook-sequence-forward-probe.json').read_text())['cases']
        reverse=json.loads(Path('reports/amm/routera3d-hook-sequence-probe.json').read_text())['cases']
        self.assertEqual(len(forward),10)
        for f,r in zip(forward,reverse):
            self.assertEqual((f['before'],f['after'],f['block'],f['sqrt']),(r['before'],r['after'],r['block'],r['sqrt']))
            before=int(f['before'],16)
            result=forward_update(before,DEFAULT_CONFIG,f['sqrt'],f['block'])
            self.assertEqual(result['after'],int(f['after'],16));self.assertEqual(result['fee'],f['fee'])
            both=directional_fees(before,DEFAULT_CONFIG,f['sqrt'],f['block'])
            self.assertEqual((both['buy_fee_ppm'],both['sell_fee_ppm']),(r['fee'],f['fee']))
            self.assertEqual(both['reference_after'],int(f['after'],16))
    def test_unknown_directions_and_widths_reject(self):
        for args in [(2,1,40,4000000,50),(0,1,40,4000000,50),(1,2,1<<24,1,50)]:
            with self.assertRaises(ValueError):same_block_reverse_fee(*args)

if __name__=='__main__':unittest.main()
