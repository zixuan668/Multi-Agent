"""Run the integrated A/B/C server; optionally reuse C's configured model."""
import argparse
import os
from pathlib import Path

from src.agents.evaluation.provider import EvaluationConfig, load_env
from src.backend.strategy_web import main


def run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',type=Path)
    p.add_argument('--port',type=int,default=8766)
    p.add_argument('--share-model',action='store_true',help='A/B配置缺省时使用已配置C模型，仅在进程内映射')
    args=p.parse_args()
    if args.env_file:load_env(args.env_file)
    config=EvaluationConfig.from_env()
    if args.share_model:
        for prefix in ('MODEL_','CREATIVE_MODEL_'):
            for name,value in {'BASE_URL':config.base_url,'API_KEY':config.api_key,'NAME':config.model,
                               'TIMEOUT_SECONDS':str(config.timeout_seconds)}.items():
                os.environ.setdefault(prefix+name,value)
    return main(['--host','127.0.0.1','--port',str(args.port),'--evaluation'])


if __name__=='__main__':raise SystemExit(run())
