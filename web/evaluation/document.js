/** Native Word document export. Runs locally without uploading task content. */
import {unpackText} from './api.js';

const riskNames={high:'严重',medium:'中等',low:'轻微'};
const dimensionNames={attraction:'吸引力',audience_fit:'用户匹配度',clarity:'信息传达',channel_fit:'渠道适配',call_to_action:'行动引导'};
const xml=value=>String(value??'').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/g,'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;');

export function strategyDocumentSections(payload){
  if(payload.delivery_type!=='strategy_feedback'||!payload.feedback?.length)throw new Error('没有可导出的策略修改事项。');
  const req=payload.requirements,s=payload.strategy.data,d=payload.evaluation.data;
  const sections=[],add=(text,style='Normal')=>sections.push({text:String(text??''),style});
  const clean=value=>unpackText(value||'').base;
  add(req.product_name+'策略修改单','Title');
  add('请营销策略负责人按以下事项调整策略，保留原始产品事实与限制。策略更新后，再生成相应广告创意并重新评估。');
  add(`本轮综合评分 ${d.total_score.toFixed(1)} 分，发现严重风险 ${d.risks.filter(r=>r.severity==='high').length} 项。当前结论为策略需要调整。`);
  add('需要调整的策略','Heading1');
  payload.feedback.forEach((f,i)=>{
    add(`修改事项 ${i+1} ${riskNames[f.priority]||'待处理'}`,'Heading2');
    add('问题：'+f.issue);add('修改建议：'+f.suggestion);
  });
  add('原始需求','Heading1');
  add('产品名称：'+req.product_name);add('产品介绍：'+clean(req.product_description));
  add('营销目标：'+clean(req.marketing_goal));add('目标受众：'+(req.target_audience||'未提供'));
  add('预算：'+(req.budget?`${req.budget.amount} ${req.budget.currency}`:'待确认'));
  const period=req.campaign_period;
  add('周期：'+(period?(period.duration_days?period.duration_days+' 天':`${period.start_date} 至 ${period.end_date}`):'待确认'));
  add('特殊限制：'+(clean(req.special_requirements)||'无额外限制'));
  add('当前营销策略','Heading1');add('目标人群：'+(s.target_audience?.segment||'待确认'));
  add('定位：'+s.positioning);
  for(const point of s.selling_points||[]){add('卖点：'+point.claim);add('原始依据：'+point.source_quote);}
  for(const channel of s.channels||[]){add('渠道 '+channel.name,'Heading2');add('选择理由：'+channel.reason);add('内容方向：'+channel.content_direction);add('预算分配：'+(channel.allocated_amount??'待确认'));}
  if(s.marketing_strategy){add('传播主题：'+s.marketing_strategy.theme);for(const x of s.marketing_strategy.content_directions||[])add('内容方向：'+x);for(const x of s.marketing_strategy.promotion_methods||[])add('推广方式：'+x);}
  add('当前假设：'+(s.assumptions?.join('；')||'无'));add('信息缺口：'+(s.missing_information?.join('；')||'无'));add('约束冲突：'+(s.constraint_conflicts?.join('；')||'无'));
  add('本轮评估依据','Heading1');
  for(const [key,name] of Object.entries(dimensionNames)){add(`${name} ${d.dimension_scores[key].score} 分`,'Heading2');add(d.dimension_scores[key].reason||'无补充说明');}
  add('风险检查','Heading2');
  for(const risk of d.risks){add(`${riskNames[risk.severity]}风险：${risk.description}`);add('依据：'+risk.evidence);}
  if(!d.risks.length)add('本轮未发现风险项。');
  add('后续创意修改事项','Heading1');
  add('以下事项由广告创意负责人在策略更新后处理，供策略负责人了解本轮问题。');
  for(const [i,f] of (payload.pending_creative_feedback||[]).entries()){add(`创意事项 ${i+1} ${riskNames[f.priority]||'待处理'}`,'Heading2');add('问题：'+f.issue);add('修改建议：'+f.suggestion);}
  if(!payload.pending_creative_feedback?.length)add('暂无单独的创意修改事项。');
  add('当前广告创意','Heading1');
  for(const item of payload.creative.data.items){
    add(item.channel,'Heading2');add('广告文案：\n'+item.copy);add('核心短句：'+item.slogan);
    const poster=typeof item.poster_concept==='string'?item.poster_concept:[item.poster_concept?.headline,item.poster_concept?.visual_description].filter(Boolean).join('\n');
    const video=typeof item.video_script==='string'?item.video_script:(item.video_script?.scenes||[]).map(s=>`${s.duration_seconds} 秒：${s.visual}\n旁白：${s.narration}`).join('\n');
    add('海报文字：\n'+poster);add('短视频脚本：\n'+video);add('待确认事项：'+(item.pending_confirmations?.join('；')||'无'));
  }
  add('交付记录','Heading1');add('本文件为待处理修改单。下载文档不表示策略负责人已接收或完成修改。');
  add('任务编号：'+payload.task_id);add('策略版本：'+payload.strategy.result_id);add('创意版本：'+payload.creative.result_id);add('评估版本：'+payload.evaluation.result_id);
  return sections;
}

function crc32(bytes){let crc=0xffffffff;for(const b of bytes){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
function zip(files){
  const encoder=new TextEncoder(),parts=[],directory=[];let offset=0;
  const header=size=>new Uint8Array(size),view=bytes=>new DataView(bytes.buffer);
  for(const [name,content] of Object.entries(files)){
    const n=encoder.encode(name),data=encoder.encode(content),crc=crc32(data),local=header(30),v=view(local);
    v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint16(12,33,true);v.setUint32(14,crc,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,n.length,true);
    const central=header(46),c=view(central);c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(8,0x800,true);c.setUint16(14,33,true);c.setUint32(16,crc,true);c.setUint32(20,data.length,true);c.setUint32(24,data.length,true);c.setUint16(28,n.length,true);c.setUint32(42,offset,true);
    parts.push(local,n,data);directory.push(central,n);offset+=local.length+n.length+data.length;
  }
  const size=directory.reduce((n,p)=>n+p.length,0),end=header(22),v=view(end),count=Object.keys(files).length;
  v.setUint32(0,0x06054b50,true);v.setUint16(8,count,true);v.setUint16(10,count,true);v.setUint32(12,size,true);v.setUint32(16,offset,true);
  const output=new Uint8Array(offset+size+22);let cursor=0;for(const part of [...parts,...directory,end]){output.set(part,cursor);cursor+=part.length;}return output;
}

export function buildStrategyDocument(payload){
  const paragraphs=strategyDocumentSections(payload).map(({text,style})=>`<w:p><w:pPr><w:pStyle w:val="${style}"/></w:pPr>${text.split(/\r\n|\r|\n/).map((line,i)=>`<w:r>${i?'<w:br/>':''}<w:t xml:space="preserve">${xml(line)}</w:t></w:r>`).join('')}</w:p>`).join('');
  const declaration='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
  return zip({
    '[Content_Types].xml':declaration+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>',
    '_rels/.rels':declaration+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
    'word/_rels/document.xml.rels':declaration+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
    'word/document.xml':declaration+`<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${paragraphs}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" w:header="360" w:footer="360"/></w:sectPr></w:body></w:document>`,
    'word/styles.xml':declaration+'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:color w:val="000000"/><w:lang w:val="zh-CN"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="336" w:lineRule="auto"/><w:widowControl/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="280" w:after="160"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="180" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style></w:styles>'
  });
}
