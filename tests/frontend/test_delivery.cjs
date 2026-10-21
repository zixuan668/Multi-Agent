const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

(async()=>{
 const ui=await import(pathToFileURL(path.resolve('web/campaign/delivery.js')));
 assert.equal(ui.preferredPane({status:'running',rounds:[]}),'collaboration');
 assert.equal(ui.preferredPane({status:'awaiting_revision',rounds:[]}),'review');
 assert.equal(ui.preferredPane({status:'awaiting_confirmation',rounds:[{creative:{}}]}),'creative');
 assert.equal(ui.preferredPane({status:'awaiting_input',rounds:[]}),'collaboration');
 const row={round_no:1,creative:{result_id:'creative-1'}};
 const task={task_id:'safe',status:'awaiting_confirmation',requirements:{product_name:'<script>'},image_jobs:[]};
 const empty=ui.imageMarkup(task,row,0,true);
 assert.ok(empty.includes('制作宣传图'));
 assert.ok(!empty.includes('poster.svg'));
 assert.ok(!empty.includes('排版海报'));
 assert.ok(!empty.includes('<script>'));
 const completed={image_id:'asset',round_no:1,item_index:0,creative_result_id:'creative-1',status:'succeeded',uri:'/api/campaigns/safe/images/asset',width:2048,height:2560};
 const html=ui.imageMarkup({...task,image_jobs:[completed]},row,0,true);
 assert.ok(html.includes('&lt;script&gt;'));
 assert.ok(html.includes('下载原图'));
 assert.ok(html.includes('尚未通过图像审核'));
 assert.ok(!ui.imageMarkup({...task,image_jobs:[{...completed,status:'running'}]},row,0,true).includes('data-image-generate'));
 assert.ok(!ui.imageMarkup({...task,image_jobs:[{...completed,creative_result_id:'other'}]},row,0,true).includes('下载原图'));
 assert.ok(ui.imageErrorMessage('[SetLimitExceeded] private details').includes('用量上限'));
 assert.ok(!ui.imageErrorMessage('[SetLimitExceeded] private details').includes('private details'));
 console.log('Delivery: outcome-first navigation, real-image states, paid actions and no template fallback passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
