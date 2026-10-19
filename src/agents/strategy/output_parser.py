"""有界标点修复及已有文字的无损表示转换；所有结果仍完整校验。"""
from copy import deepcopy
import json

from .errors import ModelOutputError


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('重复JSON键')
        result[key]=value
    return result


def _open_containers(text):
    stack=[]
    quoted=escaped=False
    for char in text:
        if quoted:
            if escaped: escaped=False
            elif char=='\\': escaped=True
            elif char=='"': quoted=False
        elif char=='"': quoted=True
        elif char in '{[': stack.append(char)
        elif char in '}]':
            if not stack or stack[-1] != {'}':'{',']':'['}[char]:
                return None
            stack.pop()
    return None if quoted else stack


def parse_model_object(raw):
    text=raw.strip()
    repairs=[]
    for attempt in range(3):
        try:
            value=json.loads(text,object_pairs_hook=_unique_object)
            break
        except json.JSONDecodeError as exc:
            if attempt==2: raise ModelOutputError('模型JSON结构无法安全修复') from None
            stack=_open_containers(text)
            if exc.pos==len(text) and stack and len(stack)<=2:
                text+=''.join({'{':'}','[':']'}[item] for item in reversed(stack))
                repairs.append('补齐末尾闭合标点（不补字段或值）')
            elif exc.pos<len(text) and text[exc.pos]=='}' and exc.msg.startswith("Expecting ','"):
                prefix_stack=_open_containers(text[:exc.pos])
                if not prefix_stack or prefix_stack[-2:]!=['{','[']:
                    raise ModelOutputError('模型JSON结构无法安全修复') from None
                text=text[:exc.pos]+']'+text[exc.pos:]
                repairs.append('补齐对象结束前遗漏的数组闭合标点')
            else:
                raise ModelOutputError('模型必须只输出JSON对象，不接受说明文本、缺失值或代码围栏') from None
        except ValueError:
            raise ModelOutputError('模型JSON含重复键，不能确定有效值') from None
    if not isinstance(value,dict):
        raise ModelOutputError('模型输出顶层必须是JSON对象')
    value=deepcopy(value)
    data=value.get('data') if isinstance(value.get('data'),dict) else value
    fields=('assumptions','missing_information','constraint_conflicts')
    nested=data.get('marketing_strategy')
    # 仅修复三组完整根级列表都被放入marketing_strategy的已知结构错位。
    if isinstance(nested,dict) and all(key not in data and isinstance(nested.get(key),list) for key in fields):
        for key in fields: data[key]=nested.pop(key)
        repairs.append('将三组已有说明列表移回契约根级，保留原值')
    notes = data.get('assumptions')
    if isinstance(notes, list):
        for index, note in enumerate(notes):
            # 已知两段纯文本的表示错位；不丢弃额外字段、不补缺失值。
            if isinstance(note, dict) and set(note) == {'text'} and isinstance(note['text'], str) and note['text'].strip():
                notes[index] = note['text']
                repairs.append('展开已有假设文字包装（无新增内容）')
            elif isinstance(note, dict) and set(note) in ({'assumption', 'verification'}, {'assumption', 'validation'}) and all(isinstance(v, str) and v.strip() for v in note.values()):
                verification = note.get('verification', note.get('validation'))
                notes[index] = note['assumption'] + '；验证：' + verification
                repairs.append('将已有假设与验证文字合并为契约字符串（无新增内容）')
    return value,repairs
