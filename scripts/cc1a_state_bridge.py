"""Offline experimental state bridge for verified cc1a V3 -> recorded Metric.

No RPC/log inputs. Not live-recorder integration. V3 state is kept in Python;
Metric/provider state stays in one local REVM worker. Cross-engine reads of
modified V3 accounts are rejected rather than using an obsolete checkpoint.
Transport ambiguity invalidates this whole bridge until a new checkpoint.
"""
import copy
from decimal import Decimal, localcontext
import json
import subprocess
from pathlib import Path
from cc1a_route import plan,bind_output
from v3_state import State

METRIC_POOL='0xaf2640f82a499abfcf143fec309f1d8953b4a3ab'

class Bridge:
    def __init__(self,v3_seed,metric_seed_path,executable='target/release/examples/metric_transition',scope='config/metric-weth-research-scope.json'):
        metric=json.loads(Path(metric_seed_path).read_text())
        if v3_seed['anchor']['hash']!=metric['anchor']['hash']:
            raise ValueError('checkpoint anchors differ')
        self.states={p['pool']:State.load(p) for p in v3_seed['pools']}
        self.header=metric['parent_header']
        self.valid=True
        command=[executable,str(metric_seed_path)]+([str(scope)] if scope else [])
        self.worker=subprocess.Popen(command,stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,text=True,bufsize=1)
    def apply(self,calldata,header=None):
        if not self.valid:raise RuntimeError('bridge invalid; new checkpoint required')
        operations=plan(calldata)
        first,second=operations
        if second['pool']!=METRIC_POOL:
            raise ValueError('downstream pool outside verified recorded bridge')
        if first['pool'] not in self.states:raise ValueError('upstream checkpoint missing')
        candidate=copy.deepcopy(self.states[first['pool']])
        result=candidate.swap(first['zero'],first['amount'],first['limit'],True)
        amount=bind_output(second,[result])
        request=dict(header=header or self.header,pool=second['pool'],zero=second['zero'],
                     amount=str(amount),sender=second['sender'],recipient=second['recipient'],
                     unavailable_accounts=[first['pool']],commit=True)
        metric=self._request(request)
        if int(metric['amount0'])!=amount:
            self.valid=False;self.close()
            raise RuntimeError('Metric input differs from upstream output')
        self.states[first['pool']]=candidate
        return dict(v3=result,metric=metric,upstream_amount=str(amount),
                    experimental=True,transaction_success_assumed=True)
    def _request(self,request):
        if not self.valid:raise RuntimeError('bridge invalid; new checkpoint required')
        try:
            self.worker.stdin.write(json.dumps(request)+'\n');self.worker.stdin.flush()
            raw=self.worker.stdout.readline()
            if not raw:raise RuntimeError('Metric worker exited before acknowledgement')
            response=json.loads(raw)
            if not isinstance(response,dict):raise ValueError('invalid worker response')
            if 'error' in response:raise RejectedTransition(response['error'])
            metric=response['result']
            if metric.get('committed') is not bool(request.get('commit',False)):raise ValueError('wrong commit acknowledgement')
        except RejectedTransition:
            # Worker guarantees its candidate was not committed on an error.
            raise
        except Exception:
            self.valid=False
            self.close()
            raise
        return metric
    def quotes(self,sizes,header=None):
        """WETH/USDG arbitrary exact base sizes; both simulations are read-only."""
        records=[]
        for size in sizes:
            with localcontext() as context:
                context.prec=80
                units=Decimal(str(size))*10**18
                if not units.is_finite() or units<=0 or units!=units.to_integral_value():
                    raise ValueError('invalid WETH size')
                amount=int(units)
                record=dict(pool=METRIC_POOL,size_tokens=str(size),executable=False,
                            state_complete=False,experimental=True)
                try:
                    common=dict(pool=METRIC_POOL,header=header or self.header,
                                sender='0xcc1ae96cd8479f896a8dba85eab09a694b929b6c',
                                recipient='0xcc1ae96cd8479f896a8dba85eab09a694b929b6c',commit=False)
                    sell=self._request(dict(common,zero=True,amount=str(amount)))
                    buy=self._request(dict(common,zero=False,amount=str(-amount)))
                    bid_raw=-int(sell['amount1']);ask_raw=int(buy['amount1'])
                    record.update(bid=str(Decimal(bid_raw)/10**6/Decimal(str(size))),
                                  ask=str(Decimal(ask_raw)/10**6/Decimal(str(size))),
                                  bid_amount_raw=str(bid_raw),ask_amount_raw=str(ask_raw))
                except RejectedTransition as error:record['reason']=str(error)
                records.append(record)
        return records
    def update_oracle(self,transaction):
        header=dict(l1BlockNumber=hex(transaction['l1_block']),timestamp=hex(transaction['timestamp']))
        request=dict(kind='oracle_update',header=header,
                     transaction={k:transaction[k] for k in ('to','from','data')},commit=True)
        try:
            result=self._request(request)
            if result.get('kind')!='oracle_update':raise RuntimeError('wrong update acknowledgement')
        except Exception:
            # A presumed-success update that we cannot apply leaves pricing uncertain.
            self.valid=False;self.close()
            raise
        self.header=header
        return result
    def close(self):
        if self.worker.poll() is None:
            self.worker.terminate()
            try:self.worker.wait(timeout=5)
            except subprocess.TimeoutExpired:self.worker.kill();self.worker.wait()
        for stream in (self.worker.stdin,self.worker.stdout):
            if stream:stream.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

class RejectedTransition(ValueError):
    pass
