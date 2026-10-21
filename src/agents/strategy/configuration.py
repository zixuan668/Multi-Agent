"""不含密钥的实现指纹，区分同一提示词下不同的校验/编辑实现。"""
import hashlib
from pathlib import Path


def implementation_fingerprint():
    digest=hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(path.name.encode('utf-8'))
        digest.update(b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()
