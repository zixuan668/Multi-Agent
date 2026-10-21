export function setupNavigation({document,window,storage}) {
  const sidebar=document.getElementById('workspace-sidebar');
  const toggle=document.getElementById('sidebar-toggle');
  const close=document.getElementById('sidebar-close');
  const backdrop=document.getElementById('sidebar-backdrop');
  const mobile=window.matchMedia('(max-width:900px)');
  const shell=document.querySelector('.app-shell');
  const key='zhice.sidebar.open.v1';
  let open=false;
  try{open=!mobile.matches&&storage.getItem(key)==='true';}catch{}
  function render(){
    sidebar.hidden=!open;
    sidebar.inert=!open;
    document.body.classList.toggle('sidebar-open',open);
    toggle.setAttribute('aria-expanded',String(open));
    toggle.querySelector('span').textContent=open?'收起侧栏':'展开侧栏';
    backdrop.hidden=!(open&&mobile.matches);
    shell.inert=open&&mobile.matches;
  }
  function setOpen(value,{remember=true}={}){
    const wasOpen=open;
    open=value;
    render();
    if(remember&&!mobile.matches){try{storage.setItem(key,JSON.stringify(open));}catch{}}
    if(open&&mobile.matches)sidebar.querySelector('button').focus();
    if(wasOpen&&!open)toggle.focus();
  }
  toggle.addEventListener('click',()=>setOpen(!open));
  close.addEventListener('click',()=>setOpen(false));
  backdrop.addEventListener('click',()=>setOpen(false));
  document.addEventListener('keydown',event=>{
    if(document.querySelector('dialog[open]'))return;
    if(event.key==='Escape'&&open){event.preventDefault();setOpen(false);}
    if(event.key==='Tab'&&open&&mobile.matches){
      const focusable=[...sidebar.querySelectorAll('a[href],button,summary')].filter(item=>!item.disabled&&item.getClientRects().length);
      const first=focusable[0];
      const last=focusable.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
  });
  sidebar.addEventListener('click',event=>{
    if(mobile.matches&&event.target.closest('#new-task,[data-task],[data-evaluation-hub]'))setOpen(false,{remember:false});
  });
  mobile.addEventListener('change',()=>setOpen(false,{remember:false}));
  render();
  return {setOpen};
}
