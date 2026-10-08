const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
(async () => {
  const api = await import(pathToFileURL(path.resolve('web/evaluation/api.js')));
  assert.equal(api.escapeHtml('<script>"&\''), '&lt;script&gt;&quot;&amp;&#39;');
  const record = (id, score) => ({request:{task_id:'task-1',strategy:{result_id:'s-'+id,data:{positioning:'定位'}},creative:{result_id:'c-'+id,data:{strategy_result_id:'s-'+id,items:[{copy:'原文'}]}}},outcome:{evaluation:{result_id:id,data:{total_score:score}}}});
  const bundle = {records:[record('e1',90),record('e2',78),record('e3',76)],selected_index:1,mode:'offline',source:'fixture',config_snapshot:{pass_threshold:80},final:{task_status:'completed',assessment_status:'not_passed',termination_reason:'round_limit',selected_evaluation_id:'e2',remaining_issues:['继续优化']}};
  const exported = api.buildExport(bundle);
  assert.equal(exported.selected_results.evaluation.result_id,'e2');
  assert.equal(exported.selected_results.creative.data.strategy_result_id,exported.selected_results.strategy.result_id);
  assert.equal(exported.selected_results.evaluation.data.total_score,78);
  assert.equal(api.resolveContent(bundle.records[0].request,'creative.items[0].copy'),'原文');
  assert.equal(api.resolveContent(bundle.records[0].request,'creative.items[99].copy'),undefined);
  const unfinished={...bundle,selected_index:null,final:{...bundle.final,selected_evaluation_id:null,task_status:'optimizing'}};
  assert.equal(api.buildExport(unfinished).selected_results,null);
  console.log('Evaluation frontend: safe text, path resolution and final-version export checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
