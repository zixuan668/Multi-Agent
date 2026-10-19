"""B generation only: scoped patches and bounded format repair. Content assessment belongs to C."""
from copy import deepcopy
from .schema import ROOT
from .validation import check_data,locate,FIELDS
from .errors import CreativeError

class CreativeAgent:
    def __init__(self,provider):
        self.provider=provider
        self.system=(ROOT/"prompts/creative/v6.txt").read_text(encoding="utf-8")

    def run(self,handoff,context,previous,action,channel,instruction,paths,feedback,on_stage):
        data=deepcopy(previous["data"]) if previous else {"items":[]}
        params={"action":action,"requirements":handoff["requirements"],"strategy":handoff["strategy"],
                "task_id":handoff["task_id"],"config_version":handoff["config_version"],
                "context":context,"channel":channel,"creative_instruction":instruction,
                "previous":previous,"allowed_paths":paths,"feedback":feedback}
        for attempt in (1,2):
            try:
                on_stage("generating",attempt)
                obj=self.provider.call(self.system,params)
                on_stage("parsing",attempt)
                candidate=deepcopy(data)
                if action=="generate":
                    if set(obj)!={"item"} or not isinstance(obj["item"],dict) or obj["item"].get("channel")!=channel:
                        raise CreativeError("模型没有返回当前渠道 item", "OUTPUT_INVALID")
                    idx=next((i for i,x in enumerate(candidate["items"]) if x["channel"]==channel),None)
                    if idx is None: candidate["items"].append(obj["item"])
                    else: candidate["items"][idx]=obj["item"]
                else:
                    if set(obj)!={"changes"} or not isinstance(obj["changes"],dict) or set(obj["changes"])!=set(paths):
                        raise CreativeError("模型修改范围与指定字段不一致", "OUTPUT_INVALID")
                    for path,value in obj["changes"].items():
                        idx,field=locate(candidate,path);candidate["items"][idx][field]=value
                on_stage("validating",attempt)
                check_data(candidate,context)
                return candidate,attempt
            except CreativeError as e:
                # A retry repairs output only; network/auth/timeout never automatically resubmit.
                if e.code!="OUTPUT_INVALID" or attempt==2: raise
                params["repair_issues"]=e.issues or [{"message":str(e)}]

