"""Fail-closed checkpoint generations for the raw recorder, not a trading engine.

A replay-ready certificate proves a pinned anchor overlaps the uninterrupted
push buffer. It never asserts that a quote consumer has applied that buffer.
"""
import collections,json,subprocess,time
from pathlib import Path

def integer(v):return int(v,0) if isinstance(v,str) else int(v)

class RecoveryState:
 def __init__(self,emit,max_blocks=20000,join_timeout_seconds=15):
  self.emit=emit;self.max_blocks=max_blocks;self.generation=0;self.phase='waiting_streams';self.reason='startup';self.links={};self.subscriptions=set();self.heads=collections.OrderedDict();self.nitro=collections.OrderedDict();self.sequence=None;self.sequences=collections.OrderedDict();self.last_head=None;self.candidate=None;self.ready=None;self.last_mono=0;self.intervals=[];self.pending_heads=collections.OrderedDict();self.promoted_sequence=None;self.join_timeout_ns=int(join_timeout_seconds*1e9);self.waiting_since=None;self.last_invalidation_mono=0;self.confirmed_count=0
 def event(self,event,**data):
  self.emit(dict(kind='checkpoint_recovery',event=event,generation=self.generation,mono_ns=self.last_mono,recorded_utc_ns=time.time_ns(),state_valid=False,decision_ready=False,**data))
 def invalidate(self,reason):
  if self.ready:self.intervals[-1].update(end_mono_ns=self.last_mono,end_reason=reason)
  self.generation+=1;self.phase='waiting_streams';self.reason=reason;self.ready=None;self.candidate=None;self.heads.clear();self.nitro.clear();self.sequences.clear();self.sequence=None;self.last_head=None;self.pending_heads.clear();self.promoted_sequence=None;self.waiting_since=None;self.last_invalidation_mono=self.last_mono
  self.event('invalidated',reason=reason)
 def observe(self,r):
  self.last_mono=max(self.last_mono,r.get('mono_ns',0));kind=r.get('kind');stream=r.get('stream')
  if kind=='gap'and stream in ('chain','nitro'):
   self.links[stream]=None
   if stream=='chain':self.subscriptions.clear()
   self.invalidate(stream+'_gap');return
  if kind=='connected'and stream in ('chain','nitro'):
   old=self.links.get(stream);epoch=r.get('epoch',0)
   if old is not None and old!=epoch:self.invalidate(stream+'_epoch_changed')
   self.links[stream]=epoch
   if stream=='chain':self.subscriptions.clear()
  if kind=='subscribed'and r.get('epoch')==self.links.get('chain'):self.subscriptions.add(r['subscription_kind'])
  if kind=='chain_log'and r.get('payload',{}).get('removed'):
   key=r.get('payload',{}).get('blockHash','').lower()
   known=self.pending_heads.get(key);canonical=self.heads.get(known[0]) if known else None
   if not canonical or canonical[0]==key or key in self.nitro:self.invalidate('removed_log')
   return
  if kind=='head'and r.get('epoch')==self.links.get('chain'):
   h=r['payload'];key=h['hash'].lower();value=(integer(h['number']),h['parentHash'].lower())
   if key in self.pending_heads and self.pending_heads[key]!=value:self.invalidate('head_hash_conflict');return
   self.pending_heads[key]=value
   while len(self.pending_heads)>self.max_blocks*2:self.pending_heads.popitem(last=False)
  if kind=='nitro_push'and r.get('epoch')==self.links.get('nitro'):
   for m in r.get('payload',{}).get('messages',[]):
    if m.get('sequenceNumber') is None or not m.get('blockHash'):self.invalidate('nitro_metadata_missing');continue
    seq=integer(m['sequenceNumber']);key=m['blockHash'].lower()
    if seq in self.sequences:
     if self.sequences[seq]!=key:self.invalidate('nitro_sequence_conflict')
     else:continue
    elif self.sequence is not None and seq!=self.sequence+1:self.invalidate('nitro_sequence_gap')
    self.sequence=seq;self.sequences[seq]=key;self.nitro[key]=seq
    while len(self.sequences)>self.max_blocks:self.sequences.popitem(last=False)
    while len(self.nitro)>self.max_blocks:self.nitro.popitem(last=False)
  self.promote()
  outstanding=self.sequence is not None and (self.promoted_sequence is None or self.sequence>self.promoted_sequence)
  if outstanding:
   if self.waiting_since is None:self.waiting_since=self.last_mono
   if self.last_mono-self.waiting_since>self.join_timeout_ns:self.invalidate('canonical_head_timeout')
  else:self.waiting_since=None
 def promote(self):
  # Never assign canonicality from RPC arrival order. Both arrival orders are
  # supported, and an unmatched sibling never changes the accepted branch.
  if self.promoted_sequence is None:
   first=next((n for n,h in self.sequences.items() if h in self.pending_heads),None)
   if first is None:return
   self.promoted_sequence=first-1
  while self.promoted_sequence+1 in self.sequences:
   seq=self.promoted_sequence+1;key=self.sequences[seq]
   if key not in self.pending_heads:break
   n,parent=self.pending_heads[key]
   if self.last_head and (n!=self.last_head[0]+1 or parent!=self.last_head[1]):
    self.invalidate('canonical_head_discontinuity');return
   self.heads[n]=(key,parent);self.last_head=(n,key);self.promoted_sequence=seq;self.confirmed_count+=1;self.waiting_since=None
   while len(self.heads)>self.max_blocks:self.heads.popitem(last=False)
 def streams_ready(self):
  return all(self.links.get(s)is not None for s in ('chain','nitro'))and self.subscriptions=={'logs','heads'}and bool(self.heads)and bool(self.nitro)
 def accept(self,checkpoint,path,generation):
  if generation!=self.generation:return False
  if not checkpoint.get('anchor_verified')or checkpoint.get('failed')or not checkpoint.get('pools')or not checkpoint.get('accounts'):raise ValueError('incomplete/unverified checkpoint')
  h=checkpoint['anchor'];self.candidate=dict(path=str(path),block=integer(h['number']),hash=h['hash'].lower(),generation=generation)
  self.phase='aligning';self.event('snapshot_created',checkpoint=self.candidate);return True
 def align(self):
  c=self.candidate
  if not c or not self.streams_ready():return False
  n=c['block'];h=c['hash']
  if n in self.heads and self.heads[n][0]!=h:raise ValueError('checkpoint anchor conflicts with pushed head')
  if self.heads and min(self.heads)>n:raise ValueError('checkpoint anchor outside retained push window')
  if n not in self.heads or h not in self.nitro:return False
  end=n
  while end+1 in self.heads and self.heads[end+1][0]in self.nitro:
   if self.heads[end+1][1]!=self.heads[end][0]:raise ValueError('head ancestry mismatch')
   end+=1
  if end==n:return False
  self.ready=dict(c,through_block=end,through_hash=self.heads[end][0],available_mono_ns=self.last_mono,apply_rule='Load state after anchor block B; apply only subsequent events with block number > B, in block/transaction/log order. Consumer must catch up before enabling decisions.')
  self.intervals.append(dict(self.ready,end_mono_ns=None));self.candidate=None;self.phase='replay_ready';self.event('replay_ready',checkpoint=self.ready);return True
 def status(self):
  return dict(generation=self.generation,phase=self.phase,reason=self.reason,replay_ready=self.ready is not None,state_valid=False,decision_ready=False,consumer='not_connected',checkpoint=self.ready or self.candidate,intervals=self.intervals,canonical_head=self.last_head,canonical_heads_confirmed=self.confirmed_count,branch_selection='Nitro blockHash plus contiguous RPC ancestry; replay logs must match this hash')

class RecoveryRunner:
 def __init__(self,directory,config,options,emit,children):
  self.directory=Path(directory);self.config=str(config);self.options=options;self.state=RecoveryState(emit,options['max_buffer_blocks'],options.get('canonical_join_timeout_seconds',15));self.children=children;self.job=None;self.attempts=0;self.next_try=0;self.failure=None;self.history=[];self.align_started=0
 def fail(self,reason,now):
  self.failure=reason;self.state.candidate=None;self.state.ready=None;self.state.phase='retry_wait'
  self.next_try=now+min(self.options['retry_max_seconds'],self.options['retry_seconds']*2**min(20,max(0,self.attempts-1)));self.state.event('snapshot_failed',reason=reason,attempt=self.attempts)
 def poll(self,now=None):
  now=time.monotonic()if now is None else now
  if self.job:
   job=self.job;p=job['process'];stale=job['generation']!=self.state.generation
   timeout=now-job['started']>self.options['bootstrap_timeout_seconds']
   if stale or timeout:
    p.kill();p.wait();job['log'].close();self.job=None;self.history.append(dict(path=str(job['path']),generation=job['generation'],status='discarded'if stale else'timeout'))
    self.fail('generation_changed_during_snapshot'if stale else'bootstrap_timeout',now)
   elif p.poll()is not None:
    job['log'].close();self.job=None
    try:
     if p.returncode:raise ValueError('bootstrap_exit_'+str(p.returncode))
     seed=json.loads(job['path'].read_text())
     expected=len(json.loads(Path(self.config).read_text())['pools'])
     if len(seed.get('pools',[]))!=expected:raise ValueError('checkpoint_pool_count')
     self.state.accept(seed,job['path'],job['generation']);self.align_started=now;self.history.append(dict(path=str(job['path']),generation=job['generation'],status='aligning'))
    except Exception as e:self.fail(str(e),now)
  if self.state.candidate:
   try:
    if self.state.align():self.failure=None;self.attempts=0;self.next_try=0
    elif now-self.align_started>self.options['alignment_timeout_seconds']:self.fail('push_alignment_timeout',now)
   except ValueError as e:self.fail(str(e),now)
  stable=self.state.last_mono-self.state.last_invalidation_mono>=self.options.get('stable_stream_seconds',5)*1e9
  if not self.job and not self.state.candidate and not self.state.ready and self.attempts>=self.options['max_attempts']:
   self.state.phase='retry_wait'
   if now>=self.next_try and stable and self.state.streams_ready():
    self.attempts=0;self.state.event('retry_budget_reset',reason='cooldown_and_stable_stream')
  if not self.job and not self.state.candidate and not self.state.ready and self.state.streams_ready()and stable and now>=self.next_try and self.attempts<self.options['max_attempts']:
   self.attempts+=1;generation=self.state.generation;path=self.directory/f'checkpoint-g{generation:06d}-a{len(self.history)+self.attempts:06d}.json';log=open(path.with_suffix('.log'),'xb')
   command=['python3','scripts/bootstrap_batch.py','--config',self.config,'--sizes','0.02,0.1','--rpc',self.options['rpc'],'--output',str(path)]
   if self.options.get('backend')=='known_slots':command[1]='scripts/bootstrap_known_slots.py';command.extend(['--template',self.options['template'],'--batch-size',str(self.options.get('rpc_batch_size',5)),'--batch-interval',str(self.options.get('rpc_batch_interval_seconds',1.2))])
   p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT);self.children.append(('bootstrap_'+str(len(self.children)),p));self.job=dict(process=p,log=log,path=path,generation=generation,started=now);self.state.phase='snapshotting';self.state.event('snapshot_started',path=str(path),attempt=self.attempts)
 def status(self):return dict(self.state.status(),attempts=self.attempts,failure=self.failure,history=self.history,bootstrap_pid=None if self.job is None else self.job['process'].pid)
 def close(self):
  if self.job:
   p=self.job['process']
   if p.poll()is None:p.kill();p.wait()
   self.job['log'].close();self.job=None
