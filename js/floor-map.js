/* Wondershop rough floor map (2026-11-12, per Shruti — "is it possible to
   build a floor map during the recce? like you give a rectangle, and the
   person marks these areas? a rough one will do to start with").

   Stored as JSON in the venue form answer "floor_map":
     {"shape":"wide|square|long","items":[{"k":"decor","l":"Decor","x":0.5,"y":0.1}, ...]}
   x / y are 0–1 across the room, so the map scales to any screen.

   FloorMap.editor(el, json, onChange)  — venue.html (tap a label to add it, drag to move)
   FloorMap.svg(json)                   — read-only picture (admin booking page, sales lead)
*/
(function(){
  var ITEMS = [
    {k:'entrance', l:'Entrance',        c:'#2D2140'},
    {k:'decor',    l:'Decor',           c:'#E65A96'},
    {k:'wboard',   l:'Welcome board',   c:'#D9488A'},
    {k:'warch',    l:'Welcome arch',    c:'#B03A77'},
    {k:'music',    l:'Music / DJ',      c:'#6C4AB6'},
    {k:'buffet',   l:'Buffet',          c:'#C77C1A'},
    {k:'adult',    l:'Adult zone',      c:'#2F7D6D'},
    {k:'seating',  l:'Seating',         c:'#4E7BC4'},
    {k:'rgift',    l:'Return gifts',    c:'#8A67BE'},
    {k:'gifts',    l:'Gifts table',     c:'#A77BD6'},
    {k:'cake',     l:'Cake table',      c:'#E07A5F'},
    {k:'show',     l:'Show area',       c:'#3A9D5D'},
    {k:'spydesk',  l:'Spy desk',        c:'#333F4F', spy:true},
    {k:'station',  l:'Station',         c:'#556070', spy:true, numbered:true},
    {k:'plug',     l:'Plug',            c:'#E0A800'},
    {k:'plug16',   l:'16A plug',        c:'#B07F00'},
    {k:'other',    l:'Other',           c:'#6B6280', ask:true}
  ];
  var BY = {}; ITEMS.forEach(function(i){ BY[i.k] = i; });
  var SHAPES = {wide:[160,100], square:[110,110], long:[100,160]};

  function parse(v){
    try{ var d = typeof v === 'string' ? JSON.parse(v) : v; if(d && d.items) return {shape: SHAPES[d.shape] ? d.shape : 'wide', items: d.items}; }catch(e){}
    return {shape:'wide', items:[]};
  }
  function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  function drawSvg(d, sel){
    var W = SHAPES[d.shape][0], H = SHAPES[d.shape][1];
    var h = '<svg viewBox="-4 -4 ' + (W + 8) + ' ' + (H + 8) + '" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;touch-action:none;font-family:DM Sans,Arial,sans-serif">'
      + '<rect x="0" y="0" width="' + W + '" height="' + H + '" rx="2" fill="#FFFDF8" stroke="#8A67BE" stroke-width="1.2"/>';
    for(var gx = 10; gx < W; gx += 10) h += '<line x1="' + gx + '" y1="0" x2="' + gx + '" y2="' + H + '" stroke="#F1ECF8" stroke-width=".4"/>';
    for(var gy = 10; gy < H; gy += 10) h += '<line x1="0" y1="' + gy + '" x2="' + W + '" y2="' + gy + '" stroke="#F1ECF8" stroke-width=".4"/>';
    d.items.forEach(function(it, i){
      var m = BY[it.k] || BY.other, x = it.x * W, y = it.y * H;
      var lab = it.l || m.l, w = Math.max(14, lab.length * 2.35 + 5);
      var on = sel === i;
      h += '<g data-i="' + i + '" style="cursor:grab">'
        + '<rect x="' + (x - w / 2) + '" y="' + (y - 4.2) + '" width="' + w + '" height="8.4" rx="4.2" fill="' + m.c + '"' + (on ? ' stroke="#FFD34D" stroke-width="1.4"' : '') + '/>'
        + '<text x="' + x + '" y="' + (y + 1.5) + '" text-anchor="middle" font-size="4.1" font-weight="700" fill="#fff" style="pointer-events:none">' + esc(lab) + '</text></g>';
    });
    if(!d.items.length) h += '<text x="' + W / 2 + '" y="' + H / 2 + '" text-anchor="middle" font-size="4.5" fill="#A99FBA">Tap a label below to add it, then drag it into place</text>';
    return h + '</svg>';
  }

  function svg(v){ var d = parse(v); return d.items.length ? drawSvg(d, -1) : ''; }

  function editor(el, v, onChange){
    var d = parse(v), sel = -1;
    function save(){ onChange(JSON.stringify(d)); }
    function render(){
      var h = '<div class="fm-shapes" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;font-size:12.5px;align-items:center"><span style="color:#6B6280">Room shape:</span>'
        + [['wide','Wide ▭'],['square','Square ▢'],['long','Long ▯']].map(function(s){
            return '<button type="button" data-shape="' + s[0] + '" style="border:1.5px solid ' + (d.shape === s[0] ? '#E65A96;background:#E65A96;color:#fff' : '#EDE6FA;background:#fff;color:#2D2140') + ';border-radius:99px;padding:5px 11px;font:inherit;font-weight:700;cursor:pointer">' + s[1] + '</button>';
          }).join('') + '</div>'
        + '<div class="fm-board" style="border-radius:12px;overflow:hidden;border:1px solid #EDE6FA">' + drawSvg(d, sel) + '</div>'
        + '<div style="display:flex;gap:8px;align-items:center;margin:6px 0 10px;min-height:30px;font-size:12.5px;color:#6B6280">'
        + (sel >= 0 ? '<b style="color:#2D2140">' + esc(d.items[sel].l) + '</b> selected <button type="button" class="fm-rm" style="border:none;background:#FDECEC;color:#B4232C;border-radius:99px;padding:5px 11px;font:inherit;font-weight:700;cursor:pointer">Remove</button>'
                    + '<button type="button" class="fm-ren" style="border:none;background:#F3EDFD;color:#6C4AB6;border-radius:99px;padding:5px 11px;font:inherit;font-weight:700;cursor:pointer">Rename</button>'
                    : 'Drag labels to move them. Tap one to remove or rename it. The top of the box = the side you entered from, or the decor wall — just say which in the video.') + '</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:6px">' + ITEMS.map(function(m){
            return '<button type="button" data-add="' + m.k + '" style="border:none;background:' + m.c + ';color:#fff;border-radius:99px;padding:6px 11px;font:inherit;font-size:12.5px;font-weight:700;cursor:pointer">＋ ' + esc(m.l) + (m.numbered ? 's' : '') + '</button>';
          }).join('') + '</div>';
      el.innerHTML = h;
      wire();
    }
    function wire(){
      el.querySelectorAll('[data-shape]').forEach(function(b){ b.onclick = function(){ d.shape = b.dataset.shape; render(); save(); }; });
      el.querySelectorAll('[data-add]').forEach(function(b){ b.onclick = function(){
        var m = BY[b.dataset.add], lab = m.l;
        if(m.numbered){ lab = m.l + ' ' + (d.items.filter(function(i){ return i.k === m.k; }).length + 1); }
        if(m.ask){ lab = (window.prompt('What is it? (e.g. Photo booth, Pinata)') || '').trim().slice(0, 40); if(!lab) return; }
        // drop new labels in a loose spiral round the centre so they don't stack
        var n = d.items.length, a = n * 2.4, r = 0.08 + (n % 5) * 0.05;
        d.items.push({k: m.k, l: lab, x: Math.min(.92, Math.max(.08, .5 + Math.cos(a) * r)), y: Math.min(.9, Math.max(.1, .5 + Math.sin(a) * r))});
        sel = d.items.length - 1; render(); save();
      }; });
      var rm = el.querySelector('.fm-rm'); if(rm) rm.onclick = function(){ d.items.splice(sel, 1); sel = -1; render(); save(); };
      var rn = el.querySelector('.fm-ren'); if(rn) rn.onclick = function(){ var t = (window.prompt('New name', d.items[sel].l) || '').trim().slice(0, 40); if(t){ d.items[sel].l = t; render(); save(); } };
      var svgEl = el.querySelector('svg'), drag = null;
      function pt(e){
        var r = svgEl.getBoundingClientRect(), vb = svgEl.viewBox.baseVal;
        var W = SHAPES[d.shape][0], H = SHAPES[d.shape][1];
        var x = (e.clientX - r.left) / r.width * vb.width + vb.x, y = (e.clientY - r.top) / r.height * vb.height + vb.y;
        return {x: Math.max(0, Math.min(1, x / W)), y: Math.max(0, Math.min(1, y / H))};
      }
      svgEl.addEventListener('pointerdown', function(e){
        var g = e.target.closest('g[data-i]');
        if(!g){ if(sel >= 0){ sel = -1; render(); } return; }
        drag = {i: +g.dataset.i, moved: false, sx: e.clientX, sy: e.clientY};
        svgEl.setPointerCapture(e.pointerId); e.preventDefault();
      });
      svgEl.addEventListener('pointermove', function(e){
        if(!drag) return;
        if(Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 4) drag.moved = true;
        if(!drag.moved) return;
        var p = pt(e); d.items[drag.i].x = p.x; d.items[drag.i].y = p.y;
        var g = svgEl.querySelector('g[data-i="' + drag.i + '"]'), W = SHAPES[d.shape][0], H = SHAPES[d.shape][1];
        var rect = g.querySelector('rect'), txt = g.querySelector('text'), w = +rect.getAttribute('width');
        rect.setAttribute('x', p.x * W - w / 2); rect.setAttribute('y', p.y * H - 4.2);
        txt.setAttribute('x', p.x * W); txt.setAttribute('y', p.y * H + 1.5);
      });
      function end(){
        if(!drag) return;
        var dd = drag; drag = null;
        if(dd.moved){ sel = dd.i; render(); save(); }
        else { sel = sel === dd.i ? -1 : dd.i; render(); }
      }
      svgEl.addEventListener('pointerup', end); svgEl.addEventListener('pointercancel', end);
    }
    render();
  }

  window.FloorMap = {editor: editor, svg: svg, items: ITEMS};
})();
