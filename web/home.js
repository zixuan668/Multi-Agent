const canvas = document.getElementById("networkCanvas");
const context = canvas.getContext("2d");
const pointerGlow = document.getElementById("pointerGlow");
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let particles = [];
let frameId;
let pointer = {x: window.innerWidth / 2, y: window.innerHeight / 2, active: false};

function resizeCanvas() {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.floor(window.innerWidth * ratio);
  canvas.height = Math.floor(window.innerHeight * ratio);
  canvas.style.width = `${window.innerWidth}px`;
  canvas.style.height = `${window.innerHeight}px`;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  const count = Math.max(24, Math.min(62, Math.floor(window.innerWidth / 24)));
  particles = Array.from({length: count}, () => ({
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    vx: (Math.random() - .5) * .24,
    vy: (Math.random() - .5) * .24,
    radius: Math.random() * 1.8 + .5,
    alpha: Math.random() * .45 + .12,
    hue: Math.random() > .72 ? "250, 106, 151" : "145, 134, 255"
  }));
}

function drawNetwork() {
  context.clearRect(0, 0, window.innerWidth, window.innerHeight);
  particles.forEach((particle, index) => {
    if (pointer.active) {
      const pointerDistance = Math.hypot(pointer.x - particle.x, pointer.y - particle.y);
      if (pointerDistance < 190 && pointerDistance > 0) {
        particle.x += (pointer.x - particle.x) / pointerDistance * .16;
        particle.y += (pointer.y - particle.y) / pointerDistance * .16;
      }
    }
    particle.x += particle.vx;
    particle.y += particle.vy;
    if (particle.x < -20) particle.x = window.innerWidth + 20;
    if (particle.x > window.innerWidth + 20) particle.x = -20;
    if (particle.y < -20) particle.y = window.innerHeight + 20;
    if (particle.y > window.innerHeight + 20) particle.y = -20;
    context.beginPath();
    context.fillStyle = `rgba(${particle.hue}, ${particle.alpha})`;
    context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
    context.fill();
    for (let next = index + 1; next < particles.length; next += 1) {
      const other = particles[next];
      const distance = Math.hypot(particle.x - other.x, particle.y - other.y);
      if (distance < 145) {
        context.beginPath();
        context.strokeStyle = `rgba(130, 119, 224, ${(1 - distance / 145) * .14})`;
        context.lineWidth = .6;
        context.moveTo(particle.x, particle.y);
        context.lineTo(other.x, other.y);
        context.stroke();
      }
    }
  });
  frameId = requestAnimationFrame(drawNetwork);
}

if (!prefersReducedMotion) {
  resizeCanvas();
  drawNetwork();
  window.addEventListener("resize", () => {
    cancelAnimationFrame(frameId);
    resizeCanvas();
    drawNetwork();
  });
  window.addEventListener("pointermove", event => {
    pointer = {x: event.clientX, y: event.clientY, active: true};
    pointerGlow.style.left = `${event.clientX}px`;
    pointerGlow.style.top = `${event.clientY}px`;
  });
  document.documentElement.addEventListener("mouseleave", () => { pointer.active = false; });
}

const header = document.querySelector(".site-header");
window.addEventListener("scroll", () => header.classList.toggle("scrolled", window.scrollY > 24), {passive: true});

const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add("visible");
      observer.unobserve(entry.target);
    }
  });
}, {threshold: .14});
document.querySelectorAll(".reveal-section").forEach(section => observer.observe(section));

const signalText = document.getElementById("strategySignal");
const signalMessages = ["正在识别关键卖点", "正在匹配目标受众", "正在分配渠道任务", "正在校验事实依据"];
let signalIndex = 0;
if (!prefersReducedMotion && signalText) {
  window.setInterval(() => {
    signalIndex = (signalIndex + 1) % signalMessages.length;
    signalText.animate([{opacity: 0, transform: "translateY(5px)"}, {opacity: 1, transform: "translateY(0)"}], {duration: 420, easing: "ease-out"});
    signalText.textContent = signalMessages[signalIndex];
  }, 2400);
}

document.querySelectorAll(".flow-card").forEach(card => {
  card.addEventListener("pointermove", event => {
    const bounds = card.getBoundingClientRect();
    const rotateX = ((event.clientY - bounds.top) / bounds.height - .5) * -5;
    const rotateY = ((event.clientX - bounds.left) / bounds.width - .5) * 5;
    card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-6px)`;
  });
  card.addEventListener("pointerleave", () => { card.style.transform = ""; });
});

fetch("/api/health", {cache: "no-store"})
  .then(response => response.json())
  .then(health => {
    document.getElementById("homeModelStatus").textContent = health.real_model_configured
      ? "策略智能体已配置 · 等待进入工作台"
      : "当前为离线演示模式";
  })
  .catch(() => { document.getElementById("homeModelStatus").textContent = "智能体状态暂不可用"; });
