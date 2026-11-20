"""Causality regressions: early calldata, immutable limits, exact execution timer."""
import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal as D
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import causal_spcx_backtest as bt

class FakeWorker:
 pool_headers=[]
 def __init__(self,path):self.price=D('102');self.errors={};self.version=0
 def change(self,r):
  self.version+=1
  if r['kind']=='v3_price':self.price=D(r['log']['price']);return {'changed':True}
  if r['kind']=='source':self.price=D(r['word']);return {'changed':True}
  if r['kind']=='pool':self.price=D('104');self.pool_headers.append(r['header'])
  return {'patch':[],'diagnostic':{}}
 def quote(self,q,now,header,origin):return dict(status='priced',state_valid=True,size_tokens=str(q),bid_usdg=str(q*self.price),ask_usdg=str(q*self.price),available_ns=now)
 def close(self):pass

class CausalTests(unittest.TestCase):
 def run_case(self,extra=None,inventory=False,drop_source=False,grid=None,cache=False,phase_grid=None,tail=None,shared=False,entry_side="sell",baseline=False,observer=None,quote_only=False,invalid_at=None,assume_id=True):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'seed.json';path.write_text(json.dumps({'anchor':{'number':'0x1','timestamp':'0x0','l1BlockNumber':'0x1'},'finished_ns':0}))
   c=dict(checkpoint=str(path),warmup_seconds=0,max_position_usdg='500',edges_bps=['10'],exit_edge_bps=None,slippage_bps='1',max_bbo_age_ms=1000,gas_usdg='0',usdg_per_usdt='1',assume_tracked_word_id=assume_id)
   events=[{'kind':'session','start_utc_ns':0},{'kind':'oracle_candidate','mono_ns':50_000_000,'accepted_log_ns':500_000_000,'block_number':'0x2','from':'sender','word':'100','header':{'timestamp':'0x0','l1BlockNumber':'0x1'}}]
   c['cache_no_order']=cache;c['share_candidate_evaluations']=shared
   if observer is not None:c.update(hy_fixed_quantity='1',quote_only=quote_only)
   if phase_grid is not None:c['open_close_grid']=phase_grid;c['entry_side']=entry_side
   if grid is not None:c['threshold_grid']=grid
   if inventory:c.update(initial_inventory_usdg='500',initial_cash_usdg='0')
   if baseline:c.update(fixed_baseline=True,initial_inventory_usdg='500',initial_cash_usdg='500')
   if drop_source:events=events[:1]
   if extra:events.extend(extra if isinstance(extra,list) else [extra])
   bbos=[dict(kind='bbo',mono_ns=t,bid=p,ask=p) for t,p in [(0,'101'),(100_000_000,'99'),(300_000_000,'99')]]
   if invalid_at is not None:bbos.append(dict(mono_ns=invalid_at,invalid=True))
   if tail:bbos.extend(dict(kind='bbo',mono_ns=t,bid=v,ask=v)for t,v in tail)
   with patch.object(bt,'Worker',FakeWorker):return bt.run(c,dict(name='test',chain_shift_ms=0,binance_shift_ms=0,execution_ms=150),events,bbos,pool_observer=observer)
 def test_quote_clock_never_precedes_applied_state(self):
  self.assertEqual(bt.advance_header({'timestamp':'0x10','l1BlockNumber':'0x30'}, {'timestamp':'0x20','l1BlockNumber':'0x40'}),{'timestamp':'0x20','l1BlockNumber':'0x40'})
  self.assertEqual(bt.advance_header({'timestamp':'0x20','l1BlockNumber':'0x40'}, {'timestamp':'0x10','l1BlockNumber':'0x30'}),{'timestamp':'0x20','l1BlockNumber':'0x40'})
 def test_v3_dependency_is_visible_only_at_pushed_log_arrival(self):
  observed=[]
  event=dict(kind='v3_price',tx='v3',mono_ns=50_000_000,log_mono_ns=250_000_000,block_number='0x2',transaction_index='0x0',header={'timestamp':'0x0','l1BlockNumber':'0x1'},log={'price':'90'})
  result=self.run_case(extra=event,drop_source=True,observer=lambda t,q,v:observed.append((t,v)),quote_only=True)
  self.assertFalse(any(t<250_000_000 and v.get('bid_usdg')=='90' for t,v in observed))
  self.assertTrue(any(t==250_000_000 and v.get('bid_usdg')=='90' for t,v in observed))
  self.assertEqual(result['statistics']['v3_updates'],1)
  self.assertEqual(result['statistics']['truth_v3_updates'],1)
 def test_equal_word_id_from_unknown_writer_cannot_change_bound_pool(self):
  observed=[]
  extra=[dict(kind='oracle_candidate',mono_ns=600_000_000,block_number='0x3',**{'from':'other-writer'},word='1',header={'timestamp':'0x0','l1BlockNumber':'0x1'}),dict(kind='oracle_candidate',mono_ns=700_000_000,accepted_log_ns=900_000_000,block_number='0x4',**{'from':'sender'},word='103',header={'timestamp':'0x0','l1BlockNumber':'0x1'})]
  r=self.run_case(extra=extra,assume_id=False,observer=lambda t,q,v:observed.append((t,v)),quote_only=True,tail=[(1_000_000_000,'99')])
  self.assertTrue(all(v['bid_usdg']!='1' for t,v in observed))
  self.assertTrue(any(t==700_000_000 and v['bid_usdg']=='103' for t,v in observed))
  self.assertFalse(any(t<500_000_000 and v['bid_usdg']=='100' for t,v in observed))
  self.assertEqual(r['statistics']['unknown_sender_candidates'],2)
 def test_invalid_reference_blocks_until_fresh_quote(self):
  # Source moves at 50ms. A 25ms invalid quote must suppress that signal,
  # while the next valid BBO at 100ms re-enables evaluation.
  r=self.run_case(invalid_at=25_000_000)
  self.assertFalse(any(f['signal_ns']==50_000_000 for x in r['results'] for f in x['fills']))
  normal=self.run_case()
  self.assertGreater(sum(len(x['fills']) for x in normal['results']),sum(len(x['fills']) for x in r['results']))
 def test_pool_clock_observes_update_even_with_stale_reference(self):
  observed=[]
  event=dict(kind='oracle_candidate',mono_ns=2_000_000_000,accepted_log_ns=2_500_000_000,block_number='0x3',**{'from':'sender'},word='103',header={'timestamp':'0x2','l1BlockNumber':'0x1'})
  r=self.run_case(extra=event,observer=lambda t,q,v:observed.append((t,v)),quote_only=True,tail=[(3_000_000_000,'99')])
  self.assertEqual(r['status'],'quote_only')
  self.assertTrue(any(t==2_000_000_000 and v['ask_usdg']=='103' for t,v in observed))
 def test_fixed_baseline_closes_to_exact_initial_shares(self):
  r=self.run_case(baseline=True,drop_source=True,phase_grid=[dict(open_bps='10',close_bps='-400')],tail=[(500_000_000,'99'),(800_000_000,'99')])
  x=r['results'][0];base=D(r['initial_portfolio']['base_tokens']);position=base
  self.assertTrue(x['cycles'])
  for f in x['fills']:
   q=D(f['size_tokens']);position+=q if f['side']=='buy' else -q
   self.assertGreaterEqual(position,0)
   if f['phase']=='close':self.assertEqual(position,base)
  shared=self.run_case(baseline=True,drop_source=True,phase_grid=[dict(open_bps='10',close_bps='-400')],tail=[(500_000_000,'99'),(800_000_000,'99')],shared=True)
  self.assertEqual(x,shared['results'][0])
 def test_buy_first_opens_with_cash_then_sells_without_hedge(self):
  grid=[dict(open_bps='10',close_bps='-500',execution_ms=220)]
  args=dict(phase_grid=grid,entry_side='buy',tail=[(500_000_000,'99'),(800_000_000,'99'),(1200_000_000,'99')])
  r=self.run_case(**args);shared=self.run_case(**args,shared=True)
  self.assertEqual(r['results'],shared['results']);self.assertEqual(r['initial_portfolio']['base_tokens'],'0');self.assertEqual(r['initial_portfolio']['cash_usdg'],'500')
  fs=r['results'][0]['fills'];self.assertGreaterEqual(len(fs),2);self.assertEqual([x['side']for x in fs[:2]],['buy','sell'])
 def test_shared_candidates_preserve_independent_delay_grid(self):
  grid=[dict(open_bps=o,close_bps=c,execution_ms=t)for t in (200,210,220,230,240,250,260)for o,c in [('10','-400'),('400','-400'),('10','0')]]
  args=dict(inventory=True,drop_source=True,phase_grid=grid,tail=[(500_000_000,'99'),(800_000_000,'99'),(1200_000_000,'99')])
  plain=self.run_case(**args)['results'];shared=self.run_case(**args,shared=True)['results'];self.assertEqual(plain,shared)
  for r in shared:
   for f in r['fills']:self.assertEqual(f['fill_ns']-f['signal_ns'],int(r['execution_ms']*1e6))
 def test_negative_close_restores_exposure_within_cash_budget(self):
  r=self.run_case(inventory=True,drop_source=True,phase_grid=[dict(open_bps='10',close_bps='-400')],tail=[(500_000_000,'99'),(800_000_000,'99')])
  x=r['results'][0]
  self.assertEqual([f['phase'] for f in x['fills']],['open','close','open'])
  self.assertEqual([f['side'] for f in x['fills']],['sell','buy','sell'])
  self.assertEqual(len(x['cycles']),1)
  self.assertLess(D(x['fills'][1]['edge_at_signal_bps']),0)
  self.assertLessEqual(D(x['fills'][1]['amount_usdg']),D(x['fills'][0]['amount_usdg']))
  self.assertGreaterEqual(D(x['cash_usdg']),0)
 def test_rejected_open_does_not_advance_to_close(self):
  x=self.run_case(inventory=True,phase_grid=[dict(open_bps='10',close_bps='-400')])['results'][0]
  self.assertEqual(x['fills'],[])
  self.assertFalse(x['open_episode_at_end'])
  self.assertEqual(x['cycles'],[])
 def test_negative_close_does_not_change_open_threshold(self):
  x=self.run_case(inventory=True,drop_source=True,phase_grid=[dict(open_bps='400',close_bps='-400')],tail=[(500_000_000,'99')])['results'][0]
  self.assertEqual(x['fills'],[])
 def test_early_pool_log_is_reduced_without_waiting_for_nitro(self):
  pool=dict(kind='pool_transaction',tx='early',mono_ns=250_000_000,log_mono_ns=100_000_000,block_number='0x3',transaction_index='0x0',logs=[],header={'timestamp':'0x0','l1BlockNumber':'0x1'})
  pool['header']['timestamp']='0x2';FakeWorker.pool_headers.clear()
  r=self.run_case(pool)
  self.assertEqual([h['timestamp'] for h in FakeWorker.pool_headers],['0x0','0x2'])
  self.assertTrue(r['decision_valid'])
  self.assertEqual(r['statistics']['early_log_depth_updates'],1)
  self.assertNotIn('decision_pool_missing_patch',r['statistics'])
 def test_no_order_cache_preserves_fills_and_rejections(self):
  cases=[{},dict(inventory=True),dict(inventory=True,drop_source=True),dict(extra={'kind':'oracle_candidate','mono_ns':200_000_000,'accepted_log_ns':600_000_000,'block_number':'0x3','from':'sender','word':'104','header':{'timestamp':'0x0','l1BlockNumber':'0x1'}})]
  for case in cases:
   a=self.run_case(**case)['results'];b=self.run_case(**case,cache=True)['results']
   self.assertEqual(a,b)
 def test_execution_respects_transaction_order_within_same_receipt(self):
  pool=dict(kind='pool_transaction',tx='pool',mono_ns=200_000_000,log_mono_ns=500_000_000,block_number='0x3',transaction_index='0x0',logs=[],header={'timestamp':'0x0','l1BlockNumber':'0x1'})
  source=dict(kind='oracle_candidate',mono_ns=200_000_000,accepted_log_ns=600_000_000,block_number='0x3',transaction_index='0x1',word='100',**{'from':'sender'},header=pool['header'])
  self.assertEqual(len(self.run_case([source,pool])['results'][0]['fills']),1)
  pool['transaction_index']='0x1';source['transaction_index']='0x0'
  self.assertEqual(self.run_case([source,pool])['results'][0]['cancelled']['submitted_limit'],1)
 def test_asymmetric_sell_threshold_is_independent_of_buy(self):
  r=self.run_case(inventory=True,drop_source=True,grid=[dict(buy_bps='400',sell_bps='0'),dict(buy_bps='0',sell_bps='400')])
  self.assertEqual(len(r['results'][0]['fills']),1)
  self.assertEqual(r['results'][0]['fills'][0]['side'],'sell')
  self.assertEqual(r['results'][1]['fills'],[])
 def test_route_translation_separates_observation_from_chain_time(self):
  r=bt.resolve_route(dict(name='ohio',latency_ms=dict(tokyo_to_taiwan=25,tokyo_to_ohio=125,chain_to_taiwan=175,chain_to_ohio_machine=2,ohio_machine_to_chain=20)))
  self.assertEqual(r['binance_shift_ms'],100)
  self.assertEqual(r['chain_shift_ms'],-173)
  self.assertEqual(r['truth_chain_shift_ms'],-175)
  self.assertEqual(r['execution_ms'],20)
 def test_negative_network_latency_rejected(self):
  with self.assertRaises(ValueError):bt.resolve_route(dict(latency_ms=dict(tokyo_to_taiwan=-1,tokyo_to_ohio=125,chain_to_taiwan=175,chain_to_ohio_machine=0,ohio_machine_to_chain=20)))
 def test_calldata_signal_does_not_wait_for_future_log(self):
  r=self.run_case();f=r['results'][0]['fills'][0]
  self.assertEqual(f['signal_ns'],50_000_000)
  self.assertEqual(f['fill_ns'],200_000_000)
  self.assertEqual(r['statistics'].get('aliases_learned',0),0)
 def test_future_binance_does_not_cancel_submitted_order(self):
  r=self.run_case();self.assertEqual(len(r['results'][0]['fills']),1)
  self.assertEqual(r['results'][0]['fills'][0]['side'],'buy')
 def test_inventory_hold_is_not_zero_cost_or_double_funded(self):
  r=self.run_case(inventory=True);s=r['results'][0]
  self.assertEqual(r['initial_portfolio']['cash_usdg'],'0')
  self.assertGreater(D(r['initial_portfolio']['equity_usdg']),D('499.99'))
  self.assertEqual(s['fills'],[])
  self.assertLess(D(s['binance_mark_pnl_usdg']),0)
  self.assertEqual(D(s['excess_vs_hold_usdg']),0)
 def test_inventory_sale_books_gain_not_gross_proceeds(self):
  r=self.run_case(inventory=True,drop_source=True);s=r['results'][0]
  self.assertEqual(len(s['fills']),1)
  self.assertEqual(s['fills'][0]['side'],'sell')
  self.assertGreater(D(s['cash_usdg']),D('500'))
  self.assertLess(D(s['realized_pnl_usdg']),D('5'))
  self.assertGreater(D(s['realized_pnl_usdg']),D('4'))
  self.assertEqual(D(s['base_tokens']),0)
 def test_chain_price_move_at_execution_rejects_old_limit(self):
  r=self.run_case({'kind':'oracle_candidate','mono_ns':200_000_000,'accepted_log_ns':600_000_000,'block_number':'0x3','from':'sender','word':'104','header':{'timestamp':'0x0','l1BlockNumber':'0x1'}})
  self.assertEqual(r['results'][0]['fills'],[])
  self.assertEqual(r['results'][0]['cancelled']['submitted_limit'],1)

if __name__=='__main__':unittest.main()
