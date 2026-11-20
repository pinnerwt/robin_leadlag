import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from index4_local import PoolState,POOL
class LocalIndex4Test(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=json.loads(Path('reports/amm/routera3d-index4-ticks-dependencies.json').read_text())
  cls.report=json.loads(Path('reports/amm/routera3d-index4-crossing-probe.json').read_text())
  cls.initial=PoolState.initialize(cls.seed,bitmap_words=[cls.seed['tick_initialization']['bitmap_word']],caller_discount=0)
 def test_composed_transition_matches_four_bytecode_swaps(self):
  for case in self.report['cases']:
   with self.subTest(tx=case['transaction']['tx']):
    state=copy.deepcopy(self.initial);before=copy.deepcopy(state)
    data=bytes.fromhex(case['transaction']['data'][10:]);limit=int.from_bytes(data[96:128],'big')
    out=state.preview_exact_input(block=state.last_block,timestamp=state.last_timestamp,zero=case['zero'],amount=case['amount'],limit=limit)
    self.assertEqual(out['fee'],case['fee']);self.assertEqual(out['result'],case['expected'])
    writes={int(w['slot'],16):int(w['value'],16) for w in case['stages'][-1]['storage_writes'] if w['address']==POOL}
    after=out['state'];index=(writes[6]>>184)&65535
    self.assertEqual(after.observations.index,index)
    if 17+index in writes:self.assertEqual(after.observations.records[index].pack(),writes[17+index])
    self.assertEqual(after.fee_cache[state.last_block],case['fee'])
    self.assertEqual(state.curve,before.curve);self.assertEqual(state.observations.records,before.observations.records);self.assertEqual(state.fee_cache,before.fee_cache)
 def test_same_block_sequence_uses_only_previous_local_state(self):
  report=json.loads(Path('reports/amm/routera3d-index4-sequence-probe.json').read_text())
  self.assertTrue(report['sequence']);self.assertEqual(len(report['cases']),4)
  self.assertEqual(report['anchor']['hash'],self.seed['anchor']['hash'])
  state=copy.deepcopy(self.initial)
  for case in report['cases']:
   data=bytes.fromhex(case['transaction']['data'][10:]);limit=int.from_bytes(data[96:128],'big')
   out=state.preview_exact_input(block=case['transaction']['sequence'],timestamp=case['transaction']['timestamp'],zero=case['zero'],amount=case['amount'],limit=limit)
   self.assertEqual(out['result'],case['expected']);self.assertEqual(out['fee'],case['fee'])
   state=out['state']
   writes={int(w['slot'],16):int(w['value'],16) for w in case['stages'][-1]['storage_writes'] if w['address']==POOL}
   self.assertEqual(state.observations.index,writes[6]>>184&65535)
   if 17+state.observations.index in writes:self.assertEqual(state.observations.records[state.observations.index].pack(),writes[17+state.observations.index])
  self.assertEqual(report['cases'][-1]['expected']['steps'],9)
 def test_cross_block_fee_recomputation_matches_bytecode(self):
  seed=json.loads(Path('reports/amm/routera3d-index4-blocks-dependencies.json').read_text())
  report=json.loads(Path('reports/amm/routera3d-index4-cross-block-probe.json').read_text())
  self.assertTrue(report['cross_block']);self.assertEqual(len(report['cases']),4)
  state=PoolState.initialize(seed,bitmap_words=[seed['tick_initialization']['bitmap_word']],caller_discount=0,cache_blocks=seed['fee_cache_initialized_blocks'])
  fees=[]
  for case in report['cases']:
   data=bytes.fromhex(case['transaction']['data'][10:]);limit=int.from_bytes(data[96:128],'big')
   out=state.preview_exact_input(block=case['transaction']['sequence'],timestamp=case['transaction']['timestamp'],zero=case['zero'],amount=case['amount'],limit=limit)
   self.assertEqual(out['fee'],case['fee']);self.assertEqual(out['result'],case['expected']);fees.append(out['fee']);state=out['state']
   writes={int(w['slot'],16):int(w['value'],16) for w in case['stages'][-1]['storage_writes'] if w['address']==POOL}
   self.assertEqual(state.observations.index,writes[6]>>184&65535)
   if 17+state.observations.index in writes:self.assertEqual(state.observations.records[state.observations.index].pack(),writes[17+state.observations.index])
  self.assertGreater(len(set(fees)),1)
 def test_failures_leave_all_quote_state_unchanged(self):
  state=copy.deepcopy(self.initial);state.observations.cardinality_next+=1;before=copy.deepcopy(state)
  with self.assertRaisesRegex(ValueError,'cardinality growth'):
   state.preview_exact_input(block=state.last_block,timestamp=state.last_timestamp,zero=False,amount=10**9)
  self.assertEqual(state.curve,before.curve);self.assertEqual(state.fee_cache,before.fee_cache);self.assertEqual(state.observations.records,before.observations.records)
  with self.assertRaisesRegex(ValueError,'unknown block fee-cache'):
   state.preview_exact_input(block=state.last_block+1,timestamp=state.last_timestamp,zero=False,amount=10**9)
 def test_cached_fee_does_not_require_old_twap_reads(self):
  state=copy.deepcopy(self.initial);state.fee_cache[state.last_block]=263;state.window_seconds=1<<31
  out=state.preview_exact_input(block=state.last_block,timestamp=state.last_timestamp,zero=False,amount=10**9)
  self.assertEqual(out['fee'],263)
