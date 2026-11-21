/* Wondershop rough floor map (2026-11-12, per Shruti — "is it possible to
   build a floor map during the recce? like you give a rectangle, and the
   person marks these areas? a rough one will do to start with").

   2026-11-21, per Shruti: labels can be rotated to any angle and resized,
   text wraps / shrinks to fit, and lines can be drawn — partitions, doors,
   dotted lines and dotted zones.

   Stored as JSON in the venue form answer "floor_map":
     {"shape":"wide|square|long",
      "items":[{"k":"decor","l":"Decor","x":0.5,"y":0.1,"w":22,"h":8,"r":0}, ...],
      "lines":[{"t":"wall|door|dotted|zone","x1":.1,"y1":.2,"x2":.5,"y2":.2,"l":"Kids zone"}, ...]}
   x / y are 0–1 across the room; w / h are in map units (room is 100–160
   wide); r is degrees. Old maps without w / h / r still draw.

   FloorMap.editor(el, json, onChange)  — venue.html
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
  var LINES = [
    {t:'wall',   l:'Wall / partition', c:'#2D2140', dash:'',      w:1.3},
    {t:'door',   l:'Door',             c:'#C77C1A', dash:'2 1.4', w:1.4},
    {t:'dotted', l:'Dotted line',      c:'#6C4AB6', dash:'1 1.2', w:.9},
    {t:'zone',   l:'Zone (dotted box)',c:'#2F7D6D', dash:'1.6 1.2', w:.8, box:true}
  ];
  var BY = {}; ITEMS.forEach(function(i){ BY[i.k] = i; });
  var LBY = {}; LINES.forEach(function(i){ LBY[i.t] = i; });
  var SHAPES = {wide:[160,100], square:[110,110], long:[100,160]};

  function parse(v){
    try{
      var d = typeof v === 'string' ? JSON.parse(v) : v;
      if(d && (d.items || d.lines)) return {shape: SHAPES[d.shape] ? d.shape : 'wide', items: d.items || [], lines: d.lines || []};
    }catch(e){}
    return {shape:'wide', items:[], lines:[]};
  }
  function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function num(v, d){ v = Number(v); return isFinite(v) ? v : d; }

  // Default size: compact pill, wraps long names onto two lines.
  function size(it){
    var lab = it.l || (BY[it.k] || BY.other).l;
    var w = num(it.w, Math.min(30, Math.max(12, lab.length * 1.7 + 4)));
    var h = num(it.h, 7);
    return {w: w, h: h};
  }
  // Wrap the label into lines that fit the box, shrinking the font as needed.
  function fit(lab, w, h){
    var words = String(lab).split(/\s+/), fs = Math.min(3.6, h * 0.55), lines;
    for(var tries = 0; tries < 12; tries++){
      var maxCh = Math.max(3, Math.floor((w - 2) / (fs * 0.55)));
      lines = []; var cur = '';
      words.forEach(function(wd){
        var t = cur ? cur + ' ' + wd : wd;
        if(t.length <= maxCh || !cur){ cur = t; } else { lines.push(cur); cur = wd; }
      });
      if(cur) lines.push(cur);
      var tooWide = lines.some(function(l){ return l.length > maxCh; });
      if(lines.length * fs * 1.15 <= h - 1 && !tooWide) break;
      fs *= 0.88;
      if(fs < 1.6){ fs = 1.6; break; }
    }
    return {lines: lines, fs: fs};
  }

  function itemSvg(it, i, W, H, on){
    var m = BY[it.k] || BY.other, x = it.x * W, y = it.y * H, s = size(it), r = num(it.r, 0);
    var lab = it.l || m.l, f = fit(lab, s.w, s.h);
    var top = -(f.lines.length - 1) * f.fs * 1.15 / 2 + f.fs * 0.35;
    var t = '<text text-anchor="middle" font-size="' + f.fs.toFixed(2) + '" font-weight="700" fill="#fff" style="pointer-events:none">'
      + f.lines.map(function(l, j){ return '<tspan x="0" y="' + (top + j * f.fs * 1.15).toFixed(2) + '">' + esc(l) + '</tspan>'; }).join('') + '</text>';
    return '<g data-i="' + i + '" transform="translate(' + x.toFixed(2) + ' ' + y.toFixed(2) + ') rotate(' + r + ')" style="cursor:grab">'
      + '<rect x="' + (-s.w / 2) + '" y="' + (-s.h / 2) + '" width="' + s.w + '" height="' + s.h + '" rx="' + Math.min(s.h / 2, 3.5) + '" fill="' + m.c + '"'
      + (on ? ' stroke="#FFD34D" stroke-width="1.2"' : '') + '/>' + t + '</g>';
  }

  function lineSvg(ln, i, W, H, on){
    var m = LBY[ln.t] || LBY.dotted;
    var x1 = ln.x1 * W, y1 = ln.y1 * H, x2 = ln.x2 * W, y2 = ln.y2 * H;
    var st = ' stroke="' + (on ? '#FFB800' : m.c) + '" stroke-width="' + (on ? m.w + .6 : m.w) + '"' + (m.dash ? ' stroke-dasharray="' + m.dash + '"' : '') + ' fill="none" stroke-linecap="round"';
    var h = '<g data-l="' + i + '" style="cursor:pointer">';
    if(m.box){
      var rx = Math.min(x1, x2), ry = Math.min(y1, y2), rw = Math.abs(x2 - x1), rh = Math.abs(y2 - y1);
      h += '<rect x="' + rx + '" y="' + ry + '" width="' + rw + '" height="' + rh + '" rx="1.5"' + st + ' fill-opacity="0"/>'
        + '<rect x="' + rx + '" y="' + ry + '" width="' + rw + '" height="' + rh + '" fill="' + m.c + '" fill-opacity=".05" stroke="none"/>';
      if(ln.l) h += '<text x="' + (rx + 1.5) + '" y="' + (ry + 4) + '" font-size="3" font-weight="700" fill="' + m.c + '" style="pointer-events:none">' + esc(ln.l) + '</text>';
    }else{
      // wide invisible stroke so a thin line is easy to tap
      h += '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="transparent" stroke-width="5"/>'
        + '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '"' + st + '/>';
      if(ln.t === 'door') h += '<text x="' + ((x1 + x2) / 2) + '" y="' + ((y1 + y2) / 2 - 1.5) + '" text-anchor="middle" font-size="2.8" font-weight="700" fill="' + m.c + '" style="pointer-events:none">' + esc(ln.l || 'Door') + '</text>';
      else if(ln.l) h += '<text x="' + ((x1 + x2) / 2) + '" y="' + ((y1 + y2) / 2 - 1.5) + '" text-anchor="middle" font-size="2.8" font-weight="700" fill="' + m.c + '" style="pointer-events:none">' + esc(ln.l) + '</text>';
    }
    return h + '</g>';
  }

  function drawSvg(d, sel, selL, draft){
    var W = SHAPES[d.shape][0], H = SHAPES[d.shape][1];
    var h = '<svg viewBox="-4 -4 ' + (W + 8) + ' ' + (H + 8) + '" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;touch-action:none;font-family:DM Sans,Arial,sans-serif">'
      + '<rect x="0" y="0" width="' + W + '" height="' + H + '" rx="2" fill="#FFFDF8" stroke="#8A67BE" stroke-width="1.2"/>';
    for(var gx = 10; gx < W; gx += 10) h += '<line x1="' + gx + '" y1="0" x2="' + gx + '" y2="' + H + '" stroke="#F1ECF8" stroke-width=".4"/>';
    for(var gy = 10; gy < H; gy += 10) h += '<line x1="0" y1="' + gy + '" x2="' + W + '" y2="' + gy + '" stroke="#F1ECF8" stroke-width=".4"/>';
    (d.lines || []).forEach(function(ln, i){ h += lineSvg(ln, i, W, H, selL === i); });
    h += '<g class="fm-draft">' + (draft ? lineSvg(draft, -1, W, H, false) : '') + '</g>';
    d.items.forEach(function(it, i){ h += itemSvg(it, i, W, H, sel === i); });
    if(!d.items.length && !(d.lines || []).length && !draft)
      h += '<text x="' + W / 2 + '" y="' + H / 2 + '" text-anchor="middle" font-size="4.5" fill="#A99FBA">Tap a label below to add it, then drag it into place</text>';
    return h + '</svg>';
  }

  function svg(v){ var d = parse(v); return (d.items.length || d.lines.length) ? drawSvg(d, -1, -1) : ''; }

  // Download as a PNG (2026-11-21, per Shruti). Draws the SVG on a canvas.
  function download(v, name){
    var d = typeof v === 'object' && v && v.items ? v : parse(v);
    var W = SHAPES[d.shape][0] + 8, H = SHAPES[d.shape][1] + 8, scale = 12;
    var src = drawSvg(d, -1, -1).replace('<svg ', '<svg width="' + W * scale + '" height="' + H * scale + '" ');
    var img = new Image();
    img.onload = function(){
      var c = document.createElement('canvas'); c.width = W * scale; c.height = H * scale;
      var x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height); x.drawImage(img, 0, 0, c.width, c.height);
      c.toBlob(function(b){
        var a = document.createElement('a'); a.href = URL.createObjectURL(b);
        a.download = (String(name || 'floor-plan').replace(/[^\w\- ]+/g, '').trim() || 'floor-plan') + '.png';
        document.body.appendChild(a); a.click(); setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 1500);
      }, 'image/png');
    };
    img.onerror = function(){ alert('Could not make the image — please try again.'); };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(src);
  }
  // Read-only map with a Download button (booking page, sales lead).
  function view(v, name){
    var s = svg(v); if(!s) return '';
    var id = 'fmv' + Math.random().toString(36).slice(2, 8);
    VIEWS[id] = {v: v, name: name};
    return s + '<div style="padding:6px 8px;text-align:right;border-top:1px solid #EDE6FA;background:#fff"><button type="button" onclick="FloorMap._dl(\'' + id + '\')" style="border:none;background:#F3EDFD;color:#6C4AB6;border-radius:99px;padding:5px 11px;font:inherit;font-size:12px;font-weight:700;cursor:pointer">⬇ Download image</button></div>';
  }
  var VIEWS = {};

  var BTN = 'border:none;border-radius:99px;padding:6px 11px;font:inherit;font-size:12.5px;font-weight:700;cursor:pointer;';

  function editor(el, v, onChange, opts){
    opts = opts || {};
    var d = parse(v), sel = -1, selL = -1, tool = null;
    function save(){ onChange(JSON.stringify(d)); }
    function slider(name, label, min, max, step, val, unit){
      return '<label style="display:flex;align-items:center;gap:6px;font-size:12px;color:#6B6280;flex:1;min-width:150px">' + label
        + '<input type="range" data-sl="' + name + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + val + '" style="flex:1">'
        + '<span data-slv="' + name + '" style="min-width:34px;color:#2D2140;font-weight:700">' + Math.round(val) + (unit || '') + '</span></label>';
    }
    function controls(){
      if(sel >= 0){
        var it = d.items[sel], s = size(it);
        return '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12.5px;color:#6B6280"><b style="color:#2D2140">' + esc(it.l) + '</b> selected'
          + '<button type="button" class="fm-rot" data-d="-15" style="' + BTN + 'background:#F3EDFD;color:#6C4AB6">↺ 15°</button>'
          + '<button type="button" class="fm-rot" data-d="15" style="' + BTN + 'background:#F3EDFD;color:#6C4AB6">↻ 15°</button>'
          + '<button type="button" class="fm-rot" data-d="90" style="' + BTN + 'background:#F3EDFD;color:#6C4AB6">↻ 90°</button>'
          + '<button type="button" class="fm-ren" style="' + BTN + 'background:#F3EDFD;color:#6C4AB6">Rename</button>'
          + '<button type="button" class="fm-rm" style="' + BTN + 'background:#FDECEC;color:#B4232C">Remove</button></div>'
          + '<div style="display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:6px">'
          + slider('w', 'Width', 8, 80, 1, s.w) + slider('h', 'Height', 4, 50, 1, s.h) + slider('r', 'Angle', 0, 359, 1, (num(it.r, 0) % 360 + 360) % 360, '°') + '</div>';
      }
      if(selL >= 0){
        var ln = d.lines[selL], m = LBY[ln.t] || LBY.dotted;
        return '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12.5px;color:#6B6280"><b style="color:#2D2140">' + esc(ln.l || m.l) + '</b> selected'
          + '<button type="button" class="fm-lren" style="' + BTN + 'background:#F3EDFD;color:#6C4AB6">Label</button>'
          + '<button type="button" class="fm-lrm" style="' + BTN + 'background:#FDECEC;color:#B4232C">Remove</button></div>';
      }
      if(tool){
        var tm = LBY[tool];
        return '<div style="font-size:12.5px;color:#2D2140"><b>Drawing: ' + esc(tm.l) + '</b> — ' + (tm.box ? 'drag across the map to draw the zone.' : 'drag from one end to the other.')
          + ' <button type="button" class="fm-tool-off" style="' + BTN + 'background:#EDE6FA;color:#2D2140">Done</button></div>';
      }
      return '<span style="font-size:12.5px;color:#6B6280">Drag labels to move them. Tap one to rotate, resize, rename or remove it. The top of the box = the side you entered from, or the decor wall — just say which in the video.</span>';
    }
    function render(){
      var plans = opts.plans || [];
      var h = (plans.length ? '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px;font-size:12.5px;background:#F7F3FF;border-radius:10px;padding:8px 10px">'
          + '<span style="color:#6C4AB6;font-weight:700">Saved plans for ' + esc(opts.venueName || 'this venue') + ':</span>'
          + '<select class="fm-plan" style="font:inherit;font-size:12.5px;padding:5px 8px;border:1px solid #EDE6FA;border-radius:8px;max-width:220px">'
          + plans.map(function(p, i){ return '<option value="' + i + '">' + esc(p.name) + (p.saved_at ? ' · ' + esc(p.saved_at) : '') + '</option>'; }).join('') + '</select>'
          + '<button type="button" class="fm-use" style="' + BTN + 'background:#6C4AB6;color:#fff">Use this plan</button>'
          + '<span style="color:#6B6280">— copies it here so you can edit it for this party; the saved one stays as is.</span></div>' : '')
        + '<div class="fm-shapes" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;font-size:12.5px;align-items:center"><span style="color:#6B6280">Room shape:</span>'
        + [['wide','Wide ▭'],['square','Square ▢'],['long','Long ▯']].map(function(s){
            return '<button type="button" data-shape="' + s[0] + '" style="border:1.5px solid ' + (d.shape === s[0] ? '#E65A96;background:#E65A96;color:#fff' : '#EDE6FA;background:#fff;color:#2D2140') + ';border-radius:99px;padding:5px 11px;font:inherit;font-weight:700;cursor:pointer">' + s[1] + '</button>';
          }).join('') + '</div>'
        + '<div class="fm-board" style="border-radius:12px;overflow:hidden;border:1px solid #EDE6FA">' + drawSvg(d, sel, selL) + '</div>'
        + '<div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;margin-top:6px">'
        + '<button type="button" class="fm-dl" style="' + BTN + 'background:#F3EDFD;color:#6C4AB6">⬇ Download image</button>'
        + (opts.onSaveToVenue ? '<button type="button" class="fm-save-v" style="' + BTN + 'background:#2F7D6D;color:#fff">Save to venue for future parties</button>' : '')
        + '</div>'
        + '<div class="fm-ctl" style="margin:8px 0 10px;min-height:30px">' + controls() + '</div>'
        + '<div style="font-size:12px;color:#6B6280;margin-bottom:4px">Add an area</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:6px">' + ITEMS.map(function(m){
            return '<button type="button" data-add="' + m.k + '" style="' + BTN + 'background:' + m.c + ';color:#fff">＋ ' + esc(m.l) + (m.numbered ? 's' : '') + '</button>';
          }).join('') + '</div>'
        + '<div style="font-size:12px;color:#6B6280;margin:10px 0 4px">Draw lines &amp; zones</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:6px">' + LINES.map(function(m){
            var on = tool === m.t;
            return '<button type="button" data-tool="' + m.t + '" style="' + BTN + 'background:' + (on ? m.c : '#fff') + ';color:' + (on ? '#fff' : m.c) + ';border:1.5px ' + (m.dash ? 'dashed' : 'solid') + ' ' + m.c + '">' + esc(m.l) + '</button>';
          }).join('') + '</div>';
      el.innerHTML = h;
      wire();
    }
    function redrawBoard(){ el.querySelector('.fm-board').innerHTML = drawSvg(d, sel, selL); wireBoard(); }
    function wire(){
      el.querySelectorAll('[data-shape]').forEach(function(b){ b.onclick = function(){ d.shape = b.dataset.shape; render(); save(); }; });
      var dl = el.querySelector('.fm-dl'); if(dl) dl.onclick = function(){ download(d, opts.fileName || 'floor-plan'); };
      var sv = el.querySelector('.fm-save-v'); if(sv) sv.onclick = function(){
        if(!d.items.length && !d.lines.length){ alert('Draw the floor map first.'); return; }
        var n = window.prompt('Name this plan (e.g. "Birthday — hall, 40 kids")', opts.defaultPlanName || '');
        if(n === null) return;
        Promise.resolve(opts.onSaveToVenue(n.trim())).then(function(list){ if(list){ opts.plans = list; render(); } });
      };
      var use = el.querySelector('.fm-use'); if(use) use.onclick = function(){
        var p = (opts.plans || [])[+el.querySelector('.fm-plan').value]; if(!p) return;
        if((d.items.length || d.lines.length) && !window.confirm('Replace the current map with “' + p.name + '”?')) return;
        d = parse(p.map); sel = -1; selL = -1; tool = null; render(); save();
      };
      el.querySelectorAll('[data-add]').forEach(function(b){ b.onclick = function(){
        var m = BY[b.dataset.add], lab = m.l;
        if(m.numbered){ lab = m.l + ' ' + (d.items.filter(function(i){ return i.k === m.k; }).length + 1); }
        if(m.ask){ lab = (window.prompt('What is it? (e.g. Photo booth, Pinata)') || '').trim().slice(0, 40); if(!lab) return; }
        var n = d.items.length, a = n * 2.4, r = 0.08 + (n % 5) * 0.05;
        d.items.push({k: m.k, l: lab, x: Math.min(.92, Math.max(.08, .5 + Math.cos(a) * r)), y: Math.min(.9, Math.max(.1, .5 + Math.sin(a) * r)), r: 0});
        sel = d.items.length - 1; selL = -1; tool = null; render(); save();
      }; });
      el.querySelectorAll('[data-tool]').forEach(function(b){ b.onclick = function(){ tool = tool === b.dataset.tool ? null : b.dataset.tool; sel = -1; selL = -1; render(); }; });
      var off = el.querySelector('.fm-tool-off'); if(off) off.onclick = function(){ tool = null; render(); };
      var rm = el.querySelector('.fm-rm'); if(rm) rm.onclick = function(){ d.items.splice(sel, 1); sel = -1; render(); save(); };
      var rn = el.querySelector('.fm-ren'); if(rn) rn.onclick = function(){ var t = (window.prompt('New name', d.items[sel].l) || '').trim().slice(0, 40); if(t){ d.items[sel].l = t; render(); save(); } };
      el.querySelectorAll('.fm-rot').forEach(function(b){ b.onclick = function(){ var it = d.items[sel]; it.r = ((num(it.r, 0) + Number(b.dataset.d)) % 360 + 360) % 360; render(); save(); }; });
      el.querySelectorAll('[data-sl]').forEach(function(s){
        s.oninput = function(){
          var it = d.items[sel], cur = size(it); it.w = cur.w; it.h = cur.h;
          it[s.dataset.sl] = Number(s.value);
          var lab = el.querySelector('[data-slv="' + s.dataset.sl + '"]'); if(lab) lab.textContent = s.value + (s.dataset.sl === 'r' ? '°' : '');
          redrawBoard();
        };
        s.onchange = function(){ save(); };
      });
      var lrm = el.querySelector('.fm-lrm'); if(lrm) lrm.onclick = function(){ d.lines.splice(selL, 1); selL = -1; render(); save(); };
      var lrn = el.querySelector('.fm-lren'); if(lrn) lrn.onclick = function(){ var t = window.prompt('Label (e.g. Kids zone, Main door) — leave blank for none', d.lines[selL].l || ''); if(t !== null){ d.lines[selL].l = t.trim().slice(0, 40); render(); save(); } };
      wireBoard();
    }
    function wireBoard(){
      var svgEl = el.querySelector('svg'), drag = null, draw = null;
      var W = SHAPES[d.shape][0], H = SHAPES[d.shape][1];
      function pt(e){
        var r = svgEl.getBoundingClientRect(), vb = svgEl.viewBox.baseVal;
        var x = (e.clientX - r.left) / r.width * vb.width + vb.x, y = (e.clientY - r.top) / r.height * vb.height + vb.y;
        return {x: Math.max(0, Math.min(1, x / W)), y: Math.max(0, Math.min(1, y / H))};
      }
      svgEl.addEventListener('pointerdown', function(e){
        if(tool){
          var p = pt(e); draw = {t: tool, x1: p.x, y1: p.y, x2: p.x, y2: p.y};
          svgEl.setPointerCapture(e.pointerId); e.preventDefault(); return;
        }
        var g = e.target.closest('g[data-i]'), gl = e.target.closest('g[data-l]');
        if(g){
          drag = {i: +g.dataset.i, moved: false, sx: e.clientX, sy: e.clientY};
          svgEl.setPointerCapture(e.pointerId); e.preventDefault(); return;
        }
        if(gl){ selL = +gl.dataset.l; sel = -1; render(); return; }
        if(sel >= 0 || selL >= 0){ sel = -1; selL = -1; render(); }
      });
      svgEl.addEventListener('pointermove', function(e){
        if(draw){
          var p = pt(e);
          // straight lines snap to horizontal / vertical when close
          if(!LBY[draw.t].box){
            var dx = Math.abs(p.x - draw.x1) * W, dy = Math.abs(p.y - draw.y1) * H;
            if(dy < dx * 0.15) p.y = draw.y1; else if(dx < dy * 0.15) p.x = draw.x1;
          }
          draw.x2 = p.x; draw.y2 = p.y;
          svgEl.querySelector('.fm-draft').innerHTML = lineSvg(draw, -1, W, H, false);
          return;
        }
        if(!drag) return;
        if(Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 4) drag.moved = true;
        if(!drag.moved) return;
        var q = pt(e); d.items[drag.i].x = q.x; d.items[drag.i].y = q.y;
        var g = svgEl.querySelector('g[data-i="' + drag.i + '"]');
        g.setAttribute('transform', 'translate(' + (q.x * W).toFixed(2) + ' ' + (q.y * H).toFixed(2) + ') rotate(' + num(d.items[drag.i].r, 0) + ')');
      });
      function end(){
        if(draw){
          var dd = draw; draw = null;
          var len = Math.hypot((dd.x2 - dd.x1) * W, (dd.y2 - dd.y1) * H);
          if(len > 3){ d.lines.push(dd); selL = d.lines.length - 1; sel = -1; if(dd.t === 'zone'){ var t = window.prompt('Name this zone (optional, e.g. Kids zone)', ''); if(t) dd.l = t.trim().slice(0, 40); } save(); }
          render(); return;
        }
        if(!drag) return;
        var g = drag; drag = null;
        if(g.moved){ sel = g.i; selL = -1; render(); save(); }
        else { sel = sel === g.i ? -1 : g.i; selL = -1; render(); }
      }
      svgEl.addEventListener('pointerup', end); svgEl.addEventListener('pointercancel', end);
    }
    render();
  }

  window.FloorMap = {editor: editor, svg: svg, view: view, download: download, items: ITEMS,
    _dl: function(id){ var x = VIEWS[id]; if(x) download(x.v, x.name); }};
})();
