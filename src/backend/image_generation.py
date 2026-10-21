import base64
import binascii
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import struct
import threading
from urllib import error, request
from urllib.parse import urlparse
from uuid import uuid4

from src.agents.strategy.errors import ConfigurationError, ContractValidationError, ModelAuthError, ModelOutputError, ModelTimeoutError, ModelUnavailableError, StrategyAgentError
from src.agents.strategy.model_clients import NoModelRedirect
from src.agents.evaluation.agent import content_risks
from src.contracts.campaign import now
from src.contracts.poster import POSTER_VERSION
from .image_briefs import poster_plan, compile_image_prompt


ROOT = Path(__file__).resolve().parents[2]
IMAGE_SETTINGS = {"IMAGE_BASE_URL", "IMAGE_API_KEY", "IMAGE_MODEL", "IMAGE_SIZE", "IMAGE_TIMEOUT_SECONDS", "IMAGE_WATERMARK"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
RESOLUTIONS_2K = {'1:1': '2048x2048', '3:4': '1728x2304', '4:5': '1856x2320', '16:9': '2560x1440', '9:16': '1440x2560'}


def load_image_settings(path=None):
    values = {}
    path = Path(path or ROOT / ".env.images")
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or key.strip() not in IMAGE_SETTINGS:
                raise ConfigurationError("生图配置包含未知变量，请检查.env.images")
            values[key.strip()] = value.strip().strip('\"\'')
    return {key: os.environ.get(key, values.get(key, "")) for key in IMAGE_SETTINGS}


def image_info(data):
    if not 24 <= len(data) <= MAX_IMAGE_BYTES:
        raise ModelOutputError("生图返回的图片为空、损坏或超过20MB")
    if data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16] == b'IHDR':
        width, height = struct.unpack('>II', data[16:24])
        mime, extension = 'image/png', 'png'
    elif data.startswith(b'\xff\xd8'):
        offset = 2
        width = height = 0
        while offset + 4 <= len(data):
            if data[offset] != 255:
                break
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset:offset+2], 'big')
            if length < 2 or offset + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2) and length >= 7:
                height, width = struct.unpack('>HH', data[offset+3:offset+7])
                break
            offset += length
        mime, extension = 'image/jpeg', 'jpg'
    else:
        raise ModelOutputError("生图接口没有返回有效PNG或JPEG图片")
    if not 1 <= width <= 16384 or not 1 <= height <= 16384:
        raise ModelOutputError("生图返回的图片尺寸无效")
    return {"mime_type": mime, "extension": extension, "width": width, "height": height}


class VolcengineImageClient:
    def __init__(self, *, base_url, api_key, model, size="2K", timeout=180, watermark=False):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or parsed.hostname != "ark.cn-beijing.volces.com" or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigurationError("生图服务只能使用火山引擎官方HTTPS地址")
        path = parsed.path.rstrip('/')
        if path.endswith('/images/generations'):
            path = path[:-len('/images/generations')]
        if path not in ('/api/v3', '/api/plan/v3'):
            raise ConfigurationError("生图服务地址须为/api/v3或/api/plan/v3")
        if not api_key or not re.fullmatch(r'[A-Za-z0-9._-]{1,150}', model or ''):
            raise ConfigurationError("请配置生图API密钥和正确的模型ID")
        if size not in ('1K', '1.5K', '2K', '4K') or not 10 <= timeout <= 300:
            raise ConfigurationError("生图尺寸或超时配置无效")
        if type(watermark) is not bool:
            raise ConfigurationError('IMAGE_WATERMARK须为true或false')
        self.endpoint = 'https://ark.cn-beijing.volces.com' + path + '/images/generations'
        self.api_key, self.model, self.size, self.timeout = api_key, model, size, timeout
        self.watermark = watermark

    @classmethod
    def from_settings(cls, values):
        if not values.get('IMAGE_API_KEY') or not values.get('IMAGE_MODEL') or not values.get('IMAGE_BASE_URL'):
            return None
        try:
            timeout = float(values.get('IMAGE_TIMEOUT_SECONDS') or '180')
        except ValueError:
            raise ConfigurationError("生图超时须为数字") from None
        watermark = str(values.get('IMAGE_WATERMARK') or 'false').lower()
        if watermark not in ('true', 'false'):
            raise ConfigurationError('IMAGE_WATERMARK须为true或false')
        return cls(base_url=values['IMAGE_BASE_URL'], api_key=values['IMAGE_API_KEY'], model=values['IMAGE_MODEL'], size=values.get('IMAGE_SIZE') or '2K', timeout=timeout, watermark=watermark == 'true')

    def generate(self, prompt, *, aspect_ratio=None):
        if aspect_ratio is not None and aspect_ratio not in RESOLUTIONS_2K:
            raise ConfigurationError('生图宽高比不受支持')
        size = RESOLUTIONS_2K[aspect_ratio] if aspect_ratio and self.size == '2K' else self.size
        payload = {"model": self.model, "prompt": prompt, "size": size, "response_format": "b64_json", "stream": False, "watermark": self.watermark}
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        call = request.Request(self.endpoint, data=body, headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"}, method='POST')
        try:
            with request.build_opener(NoModelRedirect()).open(call, timeout=self.timeout) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
                if len(raw) > 32 * 1024 * 1024:
                    raise ModelOutputError("生图响应超过大小限制")
                value = json.loads(raw)
        except error.HTTPError as exception:
            status = exception.code
            try:
                details = json.loads(exception.read(8192)).get('error', {})
                vendor_code = re.sub(r'[^A-Za-z0-9_.:-]', '', str(details.get('code', '')))[:100]
                vendor_message = str(details.get('message', '')).replace(self.api_key, '[REDACTED]')[:350]
            except (ValueError, TypeError, AttributeError):
                vendor_code, vendor_message = '', ''
            exception.close()
            detail = (' ['+vendor_code+']' if vendor_code else '') + (' '+vendor_message if vendor_message else '')
            if status in (401, 403):
                raise ModelAuthError("火山引擎拒绝鉴权或模型权限，请核对生图密钥、模型ID及套餐调用地址。"+detail) from None
            if status == 429:
                raise ModelUnavailableError("火山引擎返回HTTP 429；未自动重试。"+detail) from None
            raise ModelUnavailableError(f"火山引擎生图请求失败（HTTP {status}）；未自动重试。"+detail) from None
        except (TimeoutError, socket.timeout):
            raise ModelTimeoutError("生图请求超时，供应商可能仍在生成或计费；不会自动重试") from None
        except error.URLError:
            raise ModelUnavailableError("无法连接火山引擎生图服务；没有自动重试") from None
        except (ValueError, UnicodeDecodeError):
            raise ModelOutputError("火山引擎返回了无法解析的生图响应") from None
        try:
            images = value['data']
            if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict) or images[0].get('error'):
                raise ValueError()
            data = base64.b64decode(images[0]['b64_json'], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error):
            raise ModelOutputError("生图接口未返回单张Base64图片；不会转用其他接口或自动追加调用") from None
        return {"data": data, **image_info(data), "model": self.model, "usage": {"generated_images": 1}, "provider": "volcengine"}


def image_prompt(task, row, index, plan=None):
    return compile_image_prompt(task, row, index, poster_plan(task, row, index, plan)['plan'])


class CampaignImages:
    def __init__(self, campaigns, *, client=None, directory=None):
        self.campaigns, self.repository, self.client = campaigns, campaigns.repository, client
        self.directory = Path(directory or self.repository.path.parent / 'images')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='image')
        self.closed = False
        self.active = set()
        with self.repository.connection() as connection:
            tasks = [json.loads(row[0]) for row in connection.execute('SELECT body FROM campaigns')]
        for task in tasks:
            if any(job['status'] in ('pending', 'running') for job in task.get('image_jobs', [])):
                def interrupt(current):
                    for job in current.get('image_jobs', []):
                        if job['status'] in ('pending', 'running'):
                            job.update(status='interrupted', error='服务已重启，原请求可能已计费；请先确认供应商结果，再决定是否重新生成。', updated_at=now())
                self.repository.update(task['task_id'], interrupt)

    def create(self, task_id, owner, payload):
        if not isinstance(payload, dict) or not {'round_no', 'item_index', 'submission_key'} <= set(payload) or set(payload) - {'round_no', 'item_index', 'submission_key', 'poster_plan'}:
            raise ContractValidationError("生图需要版本、渠道及提交标识")
        round_no, index, key = payload['round_no'], payload['item_index'], payload['submission_key']
        if type(round_no) is not int or type(index) is not int or not isinstance(key, str) or not 8 <= len(key) <= 100:
            raise ContractValidationError("生图参数无效")
        with self.lock:
            task = self.repository.get(task_id, owner)
            row = next((row for row in task['rounds'] if row['round_no'] == round_no), None)
            if not row or not row.get('creative') or not 0 <= index < len(row['creative']['data']['items']):
                raise ContractValidationError("该版本或渠道没有可用创意")
            if self.client is None:
                raise ConfigurationError("火山引擎生图尚未配置完整，请设置本机.env.images中的调用地址、密钥及模型ID")
            plan = poster_plan(task, row, index, payload.get('poster_plan'))['plan']
            creative = deepcopy(row['creative'])
            creative['data']['items'][index]['visual_brief']['poster'] = plan
            risks = content_risks({'requirements': task['requirements'], 'strategy': row['strategy'], 'creative': creative})
            poster_path = f'creative.items[{index}].visual_brief.poster.'
            if any(risk['severity'] == 'high' and risk['target_path'].startswith(poster_path) for risk in risks):
                raise ContractValidationError('海报文案存在无依据承诺或违背用户明确约束的内容，请先修改；未调用生图模型')
            signature = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            digest = hashlib.sha256(key.encode()).hexdigest()
            for job in task.get('image_jobs', []):
                if job.get('_request_key') == digest:
                    if job['round_no'] != round_no or job['item_index'] != index:
                        raise ContractValidationError("同一生图提交标识不能用于不同版本或渠道")
                    if job.get('_plan_hash') and job['_plan_hash'] != signature:
                        raise ContractValidationError('同一提交标识不能修改海报方案；请先确认上一请求结果')
                    return self.campaigns.get(task_id, owner)
                if job['status'] in ('pending', 'running') and job['round_no'] == round_no and job['item_index'] == index:
                    return self.campaigns.get(task_id, owner)
            if self.closed or len(self.active) >= 4 or len(task.get('image_jobs', [])) >= 6:
                raise ModelUnavailableError("当前生图任务较多或已达到本任务6次生图上限")
            job_id = uuid4().hex
            job = {'image_id': job_id, 'round_no': round_no, 'item_index': index, 'creative_result_id': row['creative']['result_id'], 'status': 'pending', 'provider': 'volcengine', 'model': self.client.model, 'created_at': now(), 'updated_at': now(), 'review_status': 'pending_human', 'prompt': image_prompt(task, row, index, plan), '_request_key': digest, 'error': None}
            job.update(poster_plan=plan, prompt_version=POSTER_VERSION, aspect_ratio=row['creative']['data']['items'][index]['visual_brief']['aspect_ratio'], visible_watermark=getattr(self.client, 'watermark', False), _plan_hash=signature)
            self.repository.update(task_id, lambda current: current.setdefault('image_jobs', []).append(job))
            self.active.add(job_id)
            self.executor.submit(self._run, task_id, job)
            return self.campaigns.get(task_id, owner)

    def preview(self, task_id, owner, round_no, index):
        task = self.repository.get(task_id, owner)
        row = next((item for item in task['rounds'] if item['round_no'] == round_no), None)
        if not row or not row.get('creative') or not 0 <= index < len(row['creative']['data']['items']):
            raise ContractValidationError('该版本或渠道没有可用创意')
        result = poster_plan(task, row, index)
        return {**result, 'brand': task['requirements']['product_name'], 'visible_watermark': getattr(self.client, 'watermark', False), 'prompt': image_prompt(task, row, index, result['plan'])}

    def _run(self, task_id, job):
        def update(**values):
            def mutate(task):
                current = next(item for item in task['image_jobs'] if item['image_id'] == job['image_id'])
                current.update(**values, updated_at=now())
                task['updated_at'] = current['updated_at']
            self.repository.update(task_id, mutate)
        try:
            if self.closed:
                return
            update(status='running')
            result = self.client.generate(job['prompt'], aspect_ratio=job['aspect_ratio'])
            with self.lock:
                if self.closed:
                    update(status='interrupted', error='服务停止，未自动重新生成；请确认供应商计费与结果。')
                    return
                filename = job['image_id'] + '.' + result['extension']
                (self.directory / filename).write_bytes(result['data'])
                update(status='succeeded', mime_type=result['mime_type'], width=result['width'], height=result['height'], sha256=hashlib.sha256(result['data']).hexdigest(), uri=f'/api/campaigns/{task_id}/images/{job["image_id"]}', _filename=filename, usage=result['usage'])
        except Exception as exception:
            message = str(exception) if isinstance(exception, StrategyAgentError) else '图片生成或保存失败；未自动重试，请核对供应商结果后再操作。'
            update(status='failed', error=message[:500])
        finally:
            with self.lock:
                self.active.discard(job['image_id'])

    def read(self, task_id, owner, image_id):
        task = self.repository.get(task_id, owner)
        job = next((item for item in task.get('image_jobs', []) if item['image_id'] == image_id and item['status'] == 'succeeded'), None)
        if not job or not re.fullmatch(r'[a-f0-9]{32}\.(?:png|jpg)', job.get('_filename', '')):
            raise ContractValidationError("图片不存在或尚未生成成功")
        path = self.directory / job['_filename']
        if not path.is_file():
            raise ContractValidationError("图片文件缺失，请检查本地存储；不会自动重新生成")
        return path.read_bytes(), job

    def close(self):
        with self.lock:
            self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
