/* 只重排模型已有内容，不另生成结论；旧结果没有分段标签时保留全文。 */
const StrategyPresentation = (() => {
  const clean = value => String(value || "").replace(/^(?:待验证假设|待验证推断)[:：]\s*/, "");
  function sections(value, allowed) {
    const text = clean(value);
    const pattern = new RegExp("(?:^|[；;\\n])\\s*(" + allowed.join("|") + ")[:：]\\s*", "g");
    const matches = [...text.matchAll(pattern)];
    if (!matches.length || text.slice(0, matches[0].index).trim()) return [{label:"", text}];
    return matches.map((match,index) => ({
      label:match[1], text:text.slice(match.index + match[0].length, matches[index+1]?.index ?? text.length).trim(),
    })).filter(item => item.text);
  }
  function budget(channel, total, currency = "") {
    if (total === 0) return "零预算 · 仅用已有资源";
    if (channel.allocated_amount == null) return total == null ? "预算待确认" : "尚未估算 · 不代表预算已用完";
    return "建议上限 " + Number(channel.allocated_amount).toLocaleString("zh-CN") + " " + currency;
  }
  return {clean, sections, budget};
})();
if (typeof module !== "undefined" && module.exports) module.exports = StrategyPresentation;
