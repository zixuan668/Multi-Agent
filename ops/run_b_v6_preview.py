"""Load an existing external secret file into process memory; never create a secret .env."""
import argparse
import os
from pathlib import Path
from src.agents.creative.provider import load_env
from src.backend.strategy_web import main

def run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--credential-file',type=Path)
    p.add_argument('--port',type=int,default=8003)
    p.add_argument('--demo-c',action='store_true')
    a=p.parse_args()
    if a.credential_file:
        load_env(a.credential_file)
        for field in ('BASE_URL','API_KEY','NAME','TIMEOUT_SECONDS','TEMPERATURE'):
            value=os.environ.get('CREATIVE_MODEL_'+field)
            if value:os.environ.setdefault('MODEL_'+field,value)
    return main(['--host','127.0.0.1','--port',str(a.port),'--provider','compatible','--creative-provider','compatible']+(['--creative-demo'] if a.demo_c else []))

if __name__=='__main__':raise SystemExit(run())
