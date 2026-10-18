"""Structural and reference validation only. Advertising content assessment is delegated to C."""
import re
from copy import deepcopy
from .errors import CreativeError

FIELDS=("copy","slogan","poster_concept","video_script")
LIMITS={"copy":500,"slogan":30,"poster_concept":1000,"video_script":2000}
PATH=re.compile(r"items\[(\d+)\]\.(copy|slogan|poster_concept|video_script)")

def locate(data,path):
    m=PATH.fullmatch(path)
    if not m or int(m[1])>=len(data["items"]): raise CreativeError("反馈字段不存在，策略问题需返回 A", "FEEDBACK_INVALID")
    return int(m[1]),m[2]

def check_data(data,context):
    issues=[]
    def issue(field,message): issues.append({"field":field,"message":message})
    if not isinstance(data,dict) or set(data)!={"items"} or not isinstance(data["items"],list) or not 1<=len(data["items"])<=5:
        raise CreativeError("创意输出缺少 data.items", "OUTPUT_INVALID")
    names=[c["name"] for c in context["channels"]]
    seen=set()
    for i,item in enumerate(data["items"]):
        prefix=f"items[{i}]"
        if not isinstance(item,dict) or set(item)!={"channel",*FIELDS,"evidence","pending_confirmations"}:
            issue(prefix,"字段缺失或包含未声明字段"); continue
        if item["channel"] not in names or item["channel"] in seen: issue(prefix+".channel","渠道不属于锁定策略或重复")
        seen.add(item["channel"])
        for field in FIELDS:
            value=item[field]
            if not isinstance(value,str) or not value.strip() or len(value)>LIMITS[field]:
                issue(prefix+"."+field,f"必须为 1~{LIMITS[field]} 字文字");continue
        if isinstance(item.get("poster_concept"),str):
            title=re.search(r"【标题】([^\n]+)",item["poster_concept"])
            if not title or not 1<=len(title[1].strip())<=40: issue(prefix+".poster_concept","必须有【标题】，标题不超过40字")
        if isinstance(item.get("video_script"),str):
            ranges=re.findall(r"(\d+)\s*[–—~-]\s*(\d+)\s*(?:s|秒)",item["video_script"])
            cursor=0
            for start,end in ranges:
                if int(start)!=cursor or int(end)<=int(start): issue(prefix+".video_script","分镜时间必须连续且不重叠")
                cursor=int(end)
            if not ranges or not 15<=cursor<=60: issue(prefix+".video_script","视频总时长须为15~60秒，使用0–5s分镜格式")
        evidence=item["evidence"]
        if not isinstance(evidence,list) or not 1<=len(evidence)<=5: issue(prefix+".evidence","需要1~5条原文依据")
        else:
            for j,e in enumerate(evidence):
                if not isinstance(e,dict) or set(e)!={"claim","source_quote"} or not all(isinstance(v,str) and 0<len(v)<=1000 for v in e.values()):
                    issue(prefix+f".evidence[{j}]","依据结构不合法");continue
        pending=item["pending_confirmations"]
        if not isinstance(pending,list) or len(pending)>12 or any(not isinstance(p,str) or not 1<=len(p)<=300 for p in pending):
            issue(prefix+".pending_confirmations","待确认事项必须是最多12条非空文字")
    if issues: raise CreativeError("创意格式不完整，请调整后再继续", "OUTPUT_INVALID",issues)
    return deepcopy(data)

def feedback_check(feedback,result):
    if not isinstance(feedback,list) or not 1<=len(feedback)<=15: raise CreativeError("需要1~15条评估反馈", "FEEDBACK_INVALID")
    paths=set()
    for f in feedback:
        if not isinstance(f,dict) or not {"target_agent","target_path","issue","suggestion","priority"}<=set(f):
            raise CreativeError("反馈字段不完整", "FEEDBACK_INVALID")
        if f["target_agent"] not in ("creative","strategy") or f["priority"] not in ("low","medium","high") or any(not isinstance(f[k],str) or not 1<=len(f[k])<=1000 for k in ("target_path","issue","suggestion")):
            raise CreativeError("反馈类型、优先级或描述不合法", "FEEDBACK_INVALID")
        if f["target_agent"]=="strategy" or re.match(r"(?:strategy(?:\.|$)|target_audience|positioning|selling_points|budget|channels)",f["target_path"]):
            raise CreativeError("反馈涉及策略，需要返回 strategy agent", "STRATEGY_FEEDBACK")
        if not PATH.fullmatch(f["target_path"]):
            raise CreativeError("反馈 target_path 不是受支持的创意字段", "FEEDBACK_INVALID")
        locate(result["data"],f["target_path"])
        if f["target_path"] in paths: raise CreativeError("反馈字段重复", "FEEDBACK_INVALID")
        paths.add(f["target_path"])
        if f["priority"] not in ("low","medium","high") or any(not isinstance(f[k],str) or not 1<=len(f[k])<=1000 for k in ("issue","suggestion")):
            raise CreativeError("反馈优先级或问题描述不合法", "FEEDBACK_INVALID")
    return deepcopy(feedback)
