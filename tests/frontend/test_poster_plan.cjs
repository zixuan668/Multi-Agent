const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

(async()=>{
 const {setupImageGeneration}=await import(pathToFileURL(path.resolve('web/campaign/delivery.js')));
 const plan={key_message:'单一诉求',headline:'短标题',supporting_text:null,action_text:null,layout:'top_hero_bottom',visual_mode:'editorial_scene',hero_description:'一个场景一个主体'};
 const fields=Object.fromEntries(Object.keys(plan).map(key=>[key,{value:''}]));
 const nodes=Object.fromEntries(['image-plan-dialog','image-plan-form','image-plan-generate','image-plan-close','image-plan-error','image-plan-meta','image-plan-warnings','image-plan-prompt'].map(id=>[id,{hidden:false,disabled:false,textContent:'',addEventListener(){}}]));
 nodes['image-plan-dialog'].showModal=function(){this.open=true;};
 nodes['image-plan-dialog'].close=function(){this.open=false;};
 nodes['image-plan-form'].elements={namedItem:key=>fields[key]};
 nodes['image-plan-form'].reportValidity=()=>true;
 let click,currentTask={task_id:'task-1',image_jobs:[]};
 const requests=[],posts=[],values=new Map();
 const document={getElementById:id=>nodes[id],addEventListener(name,handler){if(name==='click')click=handler;}};
 const oldFormData=globalThis.FormData,oldStorage=globalThis.localStorage;
 globalThis.FormData=class {constructor(){return new Map(Object.entries(fields).map(([key,node])=>[key,node.value]));}};
 globalThis.localStorage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
 let release;
 const post=async(path,payload)=>{posts.push({path,payload});if(posts.length===1)await new Promise((resolve,reject)=>{release=()=>reject(Error('network uncertain'));});return {...currentTask,image_jobs:[{status:'pending'}]};};
 setupImageGeneration({document,getTask:()=>currentTask,request:async path=>{requests.push(path);return path.includes('image-plan')?{plan,brand:'产品',aspect_ratio:'3:4',visible_watermark:false,warnings:[],prompt:'编译后的规则'}:currentTask;},post,onTask:task=>{currentTask=task;},onError:error=>{throw error;}});
 const button={disabled:false,dataset:{imageGenerate:'0',imageRound:'1'}};
 try{
  await click({target:{closest:()=>button}});
  assert.equal(posts.length,0);
  assert.equal(requests.length,2);
  assert.equal(nodes['image-plan-dialog'].open,true);
  assert.equal(fields.headline.value,'短标题');
  assert.ok(nodes['image-plan-meta'].textContent.includes('打开方案不计费'));
  const event={preventDefault(){}};
  const first=nodes['image-plan-form'].onsubmit(event);
  await nodes['image-plan-form'].onsubmit(event);
  assert.equal(posts.length,1);
  release();await first;
  assert.equal(nodes['image-plan-error'].hidden,false);
  await nodes['image-plan-form'].onsubmit(event);
  assert.equal(posts.length,2);
  assert.equal(posts[0].payload.submission_key,posts[1].payload.submission_key);
  assert.equal(posts[1].payload.poster_plan.supporting_text,null);
  assert.equal(posts[1].payload.poster_plan.headline,'短标题');
  assert.equal(nodes['image-plan-dialog'].open,false);
  assert.equal(values.size,0);
 }finally{globalThis.FormData=oldFormData;globalThis.localStorage=oldStorage;}
 console.log('Poster plan: free preview, editable copy, explicit paid confirmation, double-submit protection and uncertain-request idempotency passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
