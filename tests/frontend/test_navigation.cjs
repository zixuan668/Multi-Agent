const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

class Element {
 constructor(){this.hidden=false;this.inert=false;this.handlers={};this.attributes={};this.textContent='';this.disabled=false;}
 addEventListener(name,handler){this.handlers[name]=handler;}
 setAttribute(name,value){this.attributes[name]=value;}
 querySelector(){return this.child;}
 querySelectorAll(){return this.children||[];}
 getClientRects(){return [1];}
 focus(){this.document.activeElement=this;}
 click(target=this){this.handlers.click?.({target});}
}

(async()=>{
 const {setupNavigation}=await import(pathToFileURL(path.resolve('web/campaign/navigation.js')));
 function fixture({mobile=false,saved=null,blocked=false}={}){
  const nodes=Object.fromEntries(['workspace-sidebar','sidebar-toggle','sidebar-close','sidebar-backdrop','shell'].map(id=>[id,new Element()]));
  const document=new Element();
  const classes=new Set();
  document.body={classList:{toggle(name,value){if(value)classes.add(name);else classes.delete(name);}}};
  document.getElementById=id=>nodes[id];document.querySelector=selector=>selector==='dialog[open]'?document.modal:nodes.shell;
  for(const node of Object.values(nodes))node.document=document;
  nodes['sidebar-toggle'].child=new Element();
  nodes['workspace-sidebar'].child=nodes['sidebar-close'];
  nodes['workspace-sidebar'].children=[nodes['sidebar-close'],nodes['sidebar-toggle']];
  const media={matches:mobile,addEventListener(name,handler){this.change=handler;}};
  const values=new Map([['zhice.sidebar.open.v1',saved]]);
  const storage={getItem(key){if(blocked)throw Error('blocked');return values.get(key);},setItem(key,value){if(blocked)throw Error('blocked');values.set(key,value);}};
  const navigation=setupNavigation({document,window:{matchMedia:()=>media},storage});
  return {nodes,document,media,values,classes,navigation};
 }
 const desktop=fixture();
 assert.equal(desktop.nodes['workspace-sidebar'].hidden,true);
 assert.equal(desktop.nodes['workspace-sidebar'].inert,true);
 desktop.nodes['sidebar-toggle'].click();
 assert.equal(desktop.nodes['sidebar-toggle'].attributes['aria-expanded'],'true');
 assert.equal(desktop.nodes['workspace-sidebar'].hidden,false);
 assert.equal(desktop.nodes['sidebar-backdrop'].hidden,true);
 assert.ok(desktop.classes.has('sidebar-open'));
 assert.equal(desktop.values.get('zhice.sidebar.open.v1'),'true');
 assert.equal(fixture({saved:'true'}).nodes['workspace-sidebar'].hidden,false);
 desktop.nodes['sidebar-toggle'].click();
 assert.equal(desktop.nodes['workspace-sidebar'].hidden,true);
 assert.equal(desktop.values.get('zhice.sidebar.open.v1'),'false');
 assert.equal(desktop.document.activeElement,desktop.nodes['sidebar-toggle']);
 const phone=fixture({mobile:true,saved:'true'});
 assert.equal(phone.nodes['workspace-sidebar'].hidden,true);
 phone.nodes['sidebar-toggle'].click();
 assert.equal(phone.nodes['sidebar-backdrop'].hidden,false);
 assert.equal(phone.nodes.shell.inert,true);
 assert.equal(phone.document.activeElement,phone.nodes['sidebar-close']);
 let prevented=false;
 phone.document.handlers.keydown({key:'Tab',shiftKey:true,preventDefault(){prevented=true;}});
 assert.equal(prevented,true);
 assert.equal(phone.document.activeElement,phone.nodes['sidebar-toggle']);
 phone.document.handlers.keydown({key:'Escape',preventDefault(){}});
 assert.equal(phone.nodes['workspace-sidebar'].hidden,true);
 assert.equal(phone.nodes.shell.inert,false);
 phone.nodes['sidebar-toggle'].click();phone.nodes['sidebar-backdrop'].click();
 assert.equal(phone.nodes['workspace-sidebar'].hidden,true);
 phone.nodes['sidebar-toggle'].click();phone.nodes['sidebar-close'].click();
 assert.equal(phone.nodes['workspace-sidebar'].hidden,true);
 phone.nodes['sidebar-toggle'].click();
 phone.document.modal={};
 phone.document.handlers.keydown({key:'Escape',preventDefault(){throw Error('modal Escape must not be intercepted');}});
 assert.equal(phone.nodes['workspace-sidebar'].hidden,false);
 phone.document.modal=null;
 phone.nodes['workspace-sidebar'].click({closest:()=>true});
 assert.equal(phone.nodes['workspace-sidebar'].hidden,true);
 desktop.navigation.setOpen(true);
 desktop.media.matches=true;desktop.media.change();
 assert.equal(desktop.nodes['workspace-sidebar'].hidden,true);
 assert.equal(desktop.nodes.shell.inert,false);
 assert.doesNotThrow(()=>fixture({blocked:true}).nodes['sidebar-toggle'].click());
 console.log('Navigation: collapse, persistence, mobile backdrop, Escape, focus, resize and storage fallback passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
