import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from index4_observations import Ring
POOL='0x7615926023bb149f36095645c2a81dc367d39750'
class ObservationTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=json.loads(Path('reports/amm/routera3d-index4-ticks-dependencies.json').read_text());cls.storage=cls.seed['accounts'][POOL]['storage'];cls.ring=Ring.load(cls.storage)
 def test_all_bytecode_observe_reads(self):
  r=json.loads(Path('reports/amm/routera3d-index4-observation-validation.json').read_text());self.assertEqual(r['anchor_hash'],self.seed['anchor']['hash'])
  count=0
  for c in r['cases']:
   for ago,expected in zip(c['lookbacks'],c['values']):
    self.assertEqual(self.ring.observe(c['time'],ago,c['tick'],c['liquidity']),tuple(expected));count+=1
  self.assertEqual(count,99)
 def test_successful_swap_writes_use_pre_swap_tick_and_liquidity(self):
  raw={int(k,16):int(v,16) for k,v in self.storage.items()};tick=(raw[6]>>160)&((1<<24)-1);tick-=1<<24;liquidity=raw[13]&((1<<128)-1)
  r=json.loads(Path('reports/amm/routera3d-index4-crossing-probe.json').read_text());before=dict(self.ring.records)
  for c in r['cases']:
   result=c['stages'][-1];self.assertTrue(result['execution_success'])
   after=self.ring.after_swap(c['transaction']['timestamp'],tick,c['expected']['tick'],liquidity)
   writes=[w for w in result['storage_writes'] if w['address']==POOL and 17<=int(w['slot'],16)<17+self.ring.cardinality]
   if c['expected']['tick']==tick:self.assertEqual(writes,[]);self.assertIs(after,self.ring)
   else:
    self.assertEqual(len(writes),1);self.assertEqual(int(writes[0]['slot'],16),17+after.index)
    self.assertEqual(int(writes[0]['value'],16),after.records[after.index].pack())
    self.assertIs(after.after_swap(c['transaction']['timestamp'],tick,tick+1,liquidity),after)
  self.assertEqual(self.ring.records,before)
 def test_missing_history_and_growth_reject(self):
  bad=dict(self.storage);del bad[hex(17+self.ring.index)]
  with self.assertRaisesRegex(ValueError,'unknown observation'):Ring.load(bad)
  with self.assertRaisesRegex(ValueError,'older than history'):self.ring.observe(self.ring.times[-1],self.ring.times[-1]-self.ring.times[0]+1,0,1)
  ring=Ring(self.ring.records,self.ring.index,self.ring.cardinality,self.ring.cardinality+1)
  with self.assertRaisesRegex(ValueError,'cardinality growth'):ring.after_swap(ring.times[-1]+1,0,1,1)
