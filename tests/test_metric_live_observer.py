import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from metric_live_observer import Projection,POOL,PYTH,FEED
class Worker:
 def __init__(self):self.requests=[];self.transactions=[]
 def call(self,**r):
  self.requests.append(r)
  if r['kind']=='decode':return {'transactions':self.transactions}
  return {'update':{'diagnostic':{'swap_count':0,'max_price_error_bps':0}}}
class ProjectionTests(unittest.TestCase):
 def make(self):
  w=Worker();p=Projection(w);p.initialize({'anchor':{'number':'0x1','hash':'a','timestamp':'0x1','l1BlockNumber':'0x1'},'pools':[{'v3_price_pools':[]}]});return p,w
 def log(self,tx,index,address=POOL):return {'transactionHash':tx,'blockHash':'b','blockNumber':'0x2','transactionIndex':hex(index),'logIndex':hex(index),'address':address,'topics':['0xfee'],'data':'0x'}
 def test_waits_for_transaction_barrier_and_nitro_metadata(self):
  p,w=self.make();p.update('log',self.log('tx',0),1)
  self.assertEqual(len(w.requests),1)
  p.update('log',self.log('next',1,'other'),2)
  self.assertEqual(len(w.requests),1)
  p.heads['b']={'number':'0x2'};p.metadata['b']={'timestamp':'0x2','l1BlockNumber':'0x2'};p.drain()
  self.assertEqual(w.requests[-1]['request']['kind'],'pool');self.assertEqual(len(p.logs),1)
 def test_removed_or_reordered_log_invalidates(self):
  p,w=self.make();l=self.log('tx',0);p.update('log',l,1)
  with self.assertRaisesRegex(ValueError,'reordered'):p.update('log',l,2)
  with self.assertRaisesRegex(ValueError,'removed'):p.update('log',dict(l,removed=True),3)
 def test_batch_report_is_not_an_oracle_update(self):
  p,w=self.make();w.transactions=[{'kind':'feed_system_tx','system_kind':'batch_posting_report_v2'}]
  m={'sequenceNumber':1,'blockHash':'b','message':{'message':{'header':{'timestamp':2,'blockNumber':2}}}}
  p.update('nitro',{'messages':[m]},1)
  self.assertEqual(p.counts['batch_reports'],1);self.assertFalse(p.pending)
  m['sequenceNumber']=3
  with self.assertRaisesRegex(ValueError,'sequence gap'):p.update('nitro',{'messages':[m]},2)
 def test_accepted_oracle_requires_matching_calldata(self):
  p,w=self.make();p.heads['b']={'number':'0x2'};p.metadata['b']={'timestamp':'0x2','l1BlockNumber':'0x2'}
  l=self.log('tx',0,PYTH);l['topics']=[FEED]
  p.update('log',l,1)
  with self.assertRaisesRegex(ValueError,'missing calldata'):p.update('log',self.log('next',1,'other'),2)
 def test_silent_nitro_and_silent_logs_force_recovery(self):
  p,w=self.make();p.last_head=100;p.last_nitro=0
  with self.assertRaisesRegex(RuntimeError,'pushed data'):p.check_progress(100,50)
  p.last_nitro=100;p.unlogged_heads={'b':0}
  with self.assertRaisesRegex(RuntimeError,'logs subscription'):p.check_progress(100,50)
 def test_quote_audit_enforces_tolerance_and_availability(self):
  from metric_pool_audit import compare
  self.assertLess(compare('10001','10000',2),2)
  with self.assertRaisesRegex(ValueError,'divergence'):compare('10010','10000',2)
  with self.assertRaisesRegex(ValueError,'availability'):compare(None,'10000',2)
if __name__=='__main__':unittest.main()
