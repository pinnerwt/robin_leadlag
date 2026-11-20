"""Run uninterrupted push-only capture until a UTC deadline, with streaming zstd."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('deadline', help='ISO UTC timestamp, e.g. 2026-11-15T00:00:00Z')
    p.add_argument('directory', type=Path)
    p.add_argument('--config', type=Path, default=ROOT/'config/push.json')
    p.add_argument('--python', default='/tmp/push-ws-env/bin/python')
    args=p.parse_args()
    deadline=dt.datetime.fromisoformat(args.deadline.replace('Z','+00:00'))
    if deadline.tzinfo is None: p.error('deadline must include timezone')
    args.directory.mkdir(parents=True,exist_ok=True)
    config=json.loads(args.config.read_text())
    config['feed_url']='ws://127.0.0.1:19648'
    config_path=args.directory/'config.json'
    config_path.write_text(json.dumps(config,indent=2)+'\n')
    (args.directory/'supervisor.pid').write_text(str(os.getpid())+'\n')
    (args.directory/'deadline').write_text(deadline.isoformat()+'\n')
    children=[]
    def stop(*_):
        for child in children:
            if child.poll() is None: child.send_signal(signal.SIGINT)
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    with (args.directory/'relay.log').open('ab') as log:
        relay=subprocess.Popen([args.python,str(ROOT/'examples/push_ws_relay.py'),'19648','--timestamp'],stdout=log,stderr=log)
        children.append(relay)
        try:
            time.sleep(1)
            while (remaining:=int(deadline.timestamp()-time.time()))>0:
                if relay.poll() is not None: raise RuntimeError('relay process ended')
                stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
                path=args.directory/f'{stamp}.bin.zst'
                with path.open('xb') as tape, path.with_suffix('.log').open('xb') as errors:
                    compressor=subprocess.Popen(['zstd','-q','-3','-c'],stdin=subprocess.PIPE,stdout=tape)
                    capture=subprocess.Popen([str(ROOT/'target/release/examples/push_capture'),str(config_path),str(remaining)],stdout=compressor.stdin,stderr=errors)
                    children.extend([capture])
                    compressor.stdin.close()
                    (args.directory/'recorder.pid').write_text(str(capture.pid)+'\n')
                    status=capture.wait()
                    children.remove(capture)
                    compressed_status=compressor.wait()
                path.with_suffix('.status.json').write_text(json.dumps(dict(capture_exit=status,zstd_exit=compressed_status))+'\n')
                if compressed_status: raise RuntimeError('compression failed')
                if status: time.sleep(1)
            (args.directory/'finished-utc').write_text(dt.datetime.now(dt.timezone.utc).isoformat()+'\n')
        finally:
            for child in children:
                if child.poll() is None: child.send_signal(signal.SIGINT)
            for child in children:
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:child.kill();child.wait()

if __name__=='__main__': main()
