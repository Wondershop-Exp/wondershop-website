/* Wondershop celebrations (2026-10-20, per Shruti — "add some animation to
   make it fun ... whenever the team converts a booking, add confetti
   animation with clapping or a boy doing cartwheel (use mascots from our
   brand book)"). No libraries: canvas confetti, CSS-animated brand mascots
   (img/brand-mascots/, from the Brand Book), falling ₹ notes and coins, a
   short synthesised clap. Respects "reduce motion".

   WSCelebrate.booking(title, sub)  confetti + cartwheel kid + dancing shapes + clapping
   WSCelebrate.money(el)            ₹ notes and coins rain over an element
   WSCelebrate.countUp(el)          numbers in el count up from 0 (data-count="1234" data-fmt="money|num|pct")
*/
(function(){
  const BASE = (document.currentScript && document.currentScript.src || '').replace(/js\/celebrate\.js.*$/, '');
  const IMG = n => BASE + 'img/brand-mascots/' + n + '.png';
  const REDUCED = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  const css = document.createElement('style');
  css.textContent = `
  .wsc-layer{position:fixed;inset:0;pointer-events:none;z-index:99999;overflow:hidden}
  .wsc-banner{position:fixed;left:50%;top:22%;transform:translate(-50%,-50%) scale(.6);opacity:0;z-index:100000;pointer-events:none;
    background:#fff;border-radius:22px;box-shadow:0 20px 60px rgba(46,36,56,.25);padding:22px 30px;text-align:center;font-family:'DM Sans',system-ui,sans-serif;
    animation:wscPop 3.6s cubic-bezier(.2,1.4,.4,1) forwards}
  .wsc-banner b{display:block;font-family:Lora,Georgia,serif;font-size:30px;color:#D6457F;line-height:1.15}
  .wsc-banner span{display:block;margin-top:6px;font-size:15px;color:#2E2438}
  @keyframes wscPop{0%{opacity:0;transform:translate(-50%,-50%) scale(.6)}12%{opacity:1;transform:translate(-50%,-50%) scale(1.04)}20%{transform:translate(-50%,-50%) scale(1)}85%{opacity:1}100%{opacity:0;transform:translate(-50%,-60%) scale(.96)}}
  .wsc-cartwheel{position:fixed;bottom:4vh;left:-200px;width:150px;z-index:100000;animation:wscRoll 3.4s cubic-bezier(.45,.05,.55,.95) forwards}
  @keyframes wscRoll{0%{left:-200px;transform:rotate(0deg) translateY(0)}25%{transform:rotate(360deg) translateY(-40px)}50%{transform:rotate(720deg) translateY(0)}75%{transform:rotate(1080deg) translateY(-40px)}100%{left:calc(100vw + 40px);transform:rotate(1440deg) translateY(0)}}
  .wsc-dancer{position:fixed;bottom:-180px;width:120px;z-index:99999;animation:wscRise 3.8s ease-in-out forwards}
  .wsc-dancer img{width:100%;display:block;animation:wscBounce .45s ease-in-out infinite alternate}
  @keyframes wscRise{0%{bottom:-180px}18%{bottom:12px}82%{bottom:12px}100%{bottom:-180px}}
  @keyframes wscBounce{from{transform:translateY(0) rotate(-8deg)}to{transform:translateY(-22px) rotate(8deg)}}
  .wsc-note{position:absolute;top:-60px;font-family:'DM Sans',system-ui,sans-serif;font-weight:700;pointer-events:none;will-change:transform}
  .wsc-note.bill{width:58px;height:30px;border-radius:5px;background:linear-gradient(135deg,#7BCB8F,#3E9B5C);color:#fff;font-size:15px;display:flex;align-items:center;justify-content:center;border:2px solid #2F7A47;box-shadow:0 3px 8px rgba(0,0,0,.15)}
  .wsc-note.coin{width:30px;height:30px;border-radius:50%;background:radial-gradient(circle at 35% 35%,#FFE38A,#F2B705 60%,#C98A00);color:#7A4E00;font-size:15px;display:flex;align-items:center;justify-content:center;border:2px solid #C98A00}
  @keyframes wscFall{0%{transform:translateY(0) rotate(0)}100%{transform:translateY(var(--fall)) rotate(var(--spin))}}
  .wsc-wiggle{animation:wscWiggle 1.6s ease-in-out infinite}
  @keyframes wscWiggle{0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg) translateY(-4px)}}
  `;
  document.head.appendChild(css);

  function layer(){ const l = document.createElement('div'); l.className = 'wsc-layer'; document.body.appendChild(l); return l; }

  // ── confetti (canvas) ─────────────────────────────────────────────────
  function confetti(ms){
    const c = document.createElement('canvas'); c.className = 'wsc-layer';
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = innerWidth * dpr; c.height = innerHeight * dpr; document.body.appendChild(c);
    const x = c.getContext('2d'); x.scale(dpr, dpr);
    const cols = ['#D6457F', '#6C4AB6', '#F2B705', '#45C46B', '#F57A1A', '#5B8EDD', '#F5C3D7'];
    const P = [];
    for(let i = 0; i < 220; i++){
      const fromLeft = i % 2 === 0;
      P.push({x: fromLeft ? -10 : innerWidth + 10, y: innerHeight * (0.55 + Math.random() * 0.3),
              vx: (fromLeft ? 1 : -1) * (6 + Math.random() * 9), vy: -(10 + Math.random() * 12),
              s: 6 + Math.random() * 7, r: Math.random() * 6, vr: (Math.random() - .5) * .4,
              c: cols[i % cols.length], shape: i % 3});
    }
    const t0 = performance.now();
    (function tick(t){
      const k = (t - t0) / ms;
      x.clearRect(0, 0, innerWidth, innerHeight);
      P.forEach(p => {
        p.vy += 0.35; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        x.save(); x.translate(p.x, p.y); x.rotate(p.r); x.globalAlpha = Math.max(0, 1 - Math.max(0, k - .7) / .3); x.fillStyle = p.c;
        if(p.shape === 0) x.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2);
        else if(p.shape === 1){ x.beginPath(); x.arc(0, 0, p.s / 2.6, 0, 7); x.fill(); }
        else { x.beginPath(); x.moveTo(0, -p.s / 2); x.lineTo(p.s / 2, p.s / 2); x.lineTo(-p.s / 2, p.s / 2); x.fill(); }
        x.restore();
      });
      if(k < 1) requestAnimationFrame(tick); else c.remove();
    })(t0);
  }

  // ── clapping (short noise bursts) ─────────────────────────────────────
  function clap(n){
    try{
      const AC = window.AudioContext || window.webkitAudioContext; if(!AC) return;
      const ac = new AC();
      for(let i = 0; i < n; i++){
        const at = ac.currentTime + i * (0.16 + Math.random() * 0.08);
        for(let j = 0; j < 3; j++){          // a few overlapping hands
          const len = 0.06, buf = ac.createBuffer(1, ac.sampleRate * len, ac.sampleRate), d = buf.getChannelData(0);
          for(let s = 0; s < d.length; s++) d[s] = (Math.random() * 2 - 1) * Math.pow(1 - s / d.length, 3);
          const src = ac.createBufferSource(); src.buffer = buf;
          const f = ac.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = 1100 + Math.random() * 900; f.Q.value = 0.9;
          const g = ac.createGain(); g.gain.value = 0.35;
          src.connect(f); f.connect(g); g.connect(ac.destination);
          src.start(at + j * 0.012);
        }
      }
      setTimeout(() => ac.close && ac.close(), (n * 0.3 + 1) * 1000);
    }catch(e){}
  }

  function booking(title, sub){
    if(REDUCED){ banner(title, sub); return; }
    confetti(3200);
    banner(title, sub);
    const cw = document.createElement('img'); cw.src = IMG('kid-cartwheel'); cw.alt = ''; cw.className = 'wsc-cartwheel';
    document.body.appendChild(cw); setTimeout(() => cw.remove(), 3600);
    const dancers = ['kid-jump-1', 'shape-5', 'kid-jump-3', 'shape-3', 'kid-jump-4', 'shape-1'];
    dancers.forEach((n, i) => {
      const d = document.createElement('div'); d.className = 'wsc-dancer';
      d.style.left = (4 + i * (88 / dancers.length)) + 'vw'; d.style.animationDelay = (i * 0.08) + 's';
      d.innerHTML = '<img alt="" src="' + IMG(n) + '" style="animation-delay:' + (i * 0.1) + 's">';
      document.body.appendChild(d); setTimeout(() => d.remove(), 4200);
    });
    clap(9);
  }
  function banner(title, sub){
    const b = document.createElement('div'); b.className = 'wsc-banner';
    b.innerHTML = '<b></b><span></span>'; b.querySelector('b').textContent = title || 'Booking converted!';
    b.querySelector('span').textContent = sub || 'Brilliant work, team!';
    document.body.appendChild(b); setTimeout(() => b.remove(), 3700);
  }

  // ── money rain over an element ────────────────────────────────────────
  function money(el, count){
    if(REDUCED || !el) return;
    const r = el.getBoundingClientRect(), l = layer();
    const n = count || 28;
    for(let i = 0; i < n; i++){
      const m = document.createElement('div');
      m.className = 'wsc-note ' + (i % 3 === 0 ? 'coin' : 'bill');
      m.textContent = '₹';
      m.style.left = (r.left + Math.random() * r.width) + 'px';
      m.style.setProperty('--fall', (r.bottom + 120) + 'px');
      m.style.setProperty('--spin', ((Math.random() - .5) * 720) + 'deg');
      m.style.animation = 'wscFall ' + (1.8 + Math.random() * 1.6) + 's cubic-bezier(.3,.1,.6,1) ' + (Math.random() * 1.2) + 's forwards';
      l.appendChild(m);
    }
    setTimeout(() => l.remove(), 4600);
  }

  // ── count-up numbers ──────────────────────────────────────────────────
  function countUp(root){
    (root || document).querySelectorAll('[data-count]').forEach(el => {
      const end = Number(el.dataset.count), fmt = el.dataset.fmt || 'num';
      if(!isFinite(end)) return;
      const show = v => fmt === 'money' ? '₹' + Math.round(v).toLocaleString('en-IN')
                      : fmt === 'pct' ? (Math.round(v * 10) / 10) + '%' : Math.round(v).toLocaleString('en-IN');
      if(REDUCED){ el.textContent = show(end); return; }
      const t0 = performance.now(), dur = 900;
      (function tick(t){ const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
        el.textContent = show(end * e); if(k < 1) requestAnimationFrame(tick); })(t0);
    });
  }

  window.WSCelebrate = {booking, money, countUp, confetti, clap};
})();
