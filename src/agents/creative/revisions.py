from copy import deepcopy
import re


def preserve_revision_scope(data, request):
    previous = request.get("previous_result")
    feedback = request.get("feedback", [])
    if not previous or not any(item["feedback_id"].startswith("human-") for item in feedback):
        return data
    if previous["data"]["strategy_result_id"] != data.get("strategy_result_id"):
        return data
    paths = [item["target_path"] for item in feedback]
    if any(path == "creative.items" or path.startswith("creative.concept") for path in paths):
        return data
    result = deepcopy(previous["data"])
    for path in paths:
        match = re.fullmatch(r"creative\.items\[(\d+)\]\.(headline|body|call_to_action|visual_brief)", path)
        if match:
            index, field = int(match.group(1)), match.group(2)
            if index < len(result["items"]) and index < len(data.get("items", [])):
                result["items"][index][field] = deepcopy(data["items"][index][field])
                poster_field = {'headline': 'headline', 'call_to_action': 'action_text'}.get(field)
                old_poster = result['items'][index]['visual_brief'].get('poster')
                new_poster = data['items'][index].get('visual_brief', {}).get('poster')
                if poster_field and old_poster and new_poster:
                    old_poster[poster_field] = deepcopy(new_poster[poster_field])
    return result
