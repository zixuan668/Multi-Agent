/** Canvas particle stream. Pauses on hidden tabs and honors reduced motion. */
export class ParticleFlow {
  constructor(canvas) {
    this.canvas=canvas; this.ctx=canvas.getContext('2d'); this.enabled=!matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.time=0; this.running=false; this.frame=null; this.last=0;
    this.particles=Array.from({length:180},(_,i)=>({phase:i/180,depth:Math.random(),lane:Math.random(),radius:.6+Math.random()*1.1}));
    this.resizeObserver=new ResizeObserver(()=>this.resize()); this.resizeObserver.observe(canvas);
    this.visibility=()=>{this.last=0;this.schedule();}; document.addEventListener('visibilitychange',this.visibility);
    this.motionQuery=matchMedia('(prefers-reduced-motion: reduce)'); this.motionQuery.addEventListener('change',e=>{if(e.matches)this.setEnabled(false);});
    this.resize(); this.schedule();
  }
  resize(){const rect=this.canvas.getBoundingClientRect();this.w=rect.width;this.h=rect.height;const dpr=Math.min(devicePixelRatio||1,2);this.canvas.width=this.w*dpr;this.canvas.height=this.h*dpr;this.ctx.setTransform(dpr,0,0,dpr,0,0);this.draw();}
  setEnabled(enabled){this.enabled=enabled;this.last=0;if(!enabled&&this.frame){cancelAnimationFrame(this.frame);this.frame=null;}this.draw();this.schedule();}
  schedule(){if(this.frame||!this.enabled||document.hidden)return;this.frame=requestAnimationFrame(t=>{this.frame=null;if(this.last)this.time+=Math.min(t-this.last,40)/1000;this.last=t;this.draw();this.schedule();});}
  path(t,depth,lane){const x=(.12+.76*t)*this.w;const spread=Math.sin(Math.PI*t);const wave=Math.sin(t*Math.PI*3.3+depth*Math.PI*2+this.time*.24);const y=this.h*.43+wave*spread*this.h*(.10+lane*.20);return{x,y};}
  draw(){const ctx=this.ctx;if(!ctx||!this.w||!this.h)return;const w=this.w,h=this.h;ctx.clearRect(0,0,w,h);
    const glow=ctx.createRadialGradient(w*.5,h*.43,0,w*.5,h*.43,w*.45);glow.addColorStop(0,'rgba(67,159,152,.065)');glow.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=glow;ctx.fillRect(0,0,w,h);
    // Stream strands cross in depth, drawing a sculptural ribbon rather than a flat dotted background.
    for(let lane=0;lane<13;lane++){ctx.beginPath();for(let i=0;i<=110;i++){const p=this.path(i/110,lane/13,(lane%5)/5);i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y);}ctx.strokeStyle=`rgba(${lane%3===0?'163,192,145':'98,190,188'},${lane%4===0?.16:.07})`;ctx.lineWidth=lane%4===0?.9:.5;ctx.stroke();}
    for(const p of this.particles){const t=(p.phase+this.time*(this.running?.16:.06))%1;const pos=this.path(t,p.depth,p.lane);const alpha=Math.sin(Math.PI*t)*(.25+p.depth*.6);ctx.beginPath();ctx.arc(pos.x,pos.y,p.radius,0,Math.PI*2);ctx.fillStyle=`rgba(${p.depth>.65?'201,225,163':'126,221,214'},${alpha})`;ctx.shadowBlur=p.depth>.7?7:0;ctx.shadowColor='#9cdad0';ctx.fill();ctx.shadowBlur=0;}
    // The feedback orbit flows right-to-left below the primary path.
    ctx.beginPath();ctx.ellipse(w*.5,h*.46,w*.34,h*.22,0,.12,Math.PI-.12);ctx.strokeStyle='rgba(155,192,172,.13)';ctx.lineWidth=.7;ctx.setLineDash([3,5]);ctx.stroke();ctx.setLineDash([]);
    for(let i=0;i<14;i++){const t=((i/14+this.time*.06)%1)*Math.PI;ctx.beginPath();ctx.arc(w*.5+Math.cos(t)*w*.34,h*.46+Math.sin(t)*h*.22,1,0,Math.PI*2);ctx.fillStyle='rgba(201,225,177,.55)';ctx.fill();}
  }
}
