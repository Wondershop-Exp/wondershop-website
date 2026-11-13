/* Venues linked to a lead / booking (2026-11-13, per Shruti — venue master).
   Used on admin.html (booking page) and sales-leads.html (sales quote).
     LeadVenues.mount(el, leadId, apiCall)
   apiCall(path, opts) is the page's own admin API helper (adds the password).
   Backend: backend/routers/venues.py. Full venue page: venues.html#v=<id>. */
(function(){
  var ST = [['shortlisted','Shortlisted'],['final','Final'],['rejected','Not chosen']];
  function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function who(){ try{ return localStorage.getItem('ws_admin_name') || ''; }catch(e){ return ''; } }
  var CSS = '<style>.lv-row{display:flex;gap:8px;align-items:center;padding:8px 0;border-top:1px solid #F1ECF8;flex-wrap:wrap}'
    + '.lv-row:first-child{border-top:0}.lv-name{flex:1;min-width:180px;font-size:13.5px}.lv-name a{font-weight:700;color:#6C4AB6;text-decoration:none}'
    + '.lv-sub{font-size:12px;color:#6B6280}.lv-st{font:inherit;font-size:12.5px;padding:4px 6px;border-radius:8px;border:1px solid #EDE6FA}'
    + '.lv-st.final{background:#E7F8EE;color:#127A3D;border-color:#BFE8CF}.lv-st.rejected{color:#8B7FA0}'
    + '.lv-btn{font:inherit;font-size:12.5px;font-weight:700;border:0;border-radius:8px;padding:6px 10px;cursor:pointer;background:#F7F3FF;color:#6C4AB6;text-decoration:none;display:inline-block}'
    + '.lv-btn.pk{background:#E65A96;color:#fff}.lv-res{border:1px solid #EDE6FA;border-radius:10px;margin-top:6px;max-height:220px;overflow:auto;background:#fff}'
    + '.lv-res div{padding:7px 10px;cursor:pointer;font-size:13px;border-top:1px solid #F7F3FF}.lv-res div:hover{background:#F7F3FF}'
    + '.lv-search{font:inherit;font-size:13.5px;padding:7px 10px;border:1px solid #EDE6FA;border-radius:8px;width:100%;max-width:340px}</style>';

  function mount(el, leadId, apiCall){
    if(!el || !leadId) return;
    var rows = [];
    function load(){
      apiCall('/api/admin/lead-venues/' + leadId).then(function(d){ rows = d.venues || []; CACHE[leadId] = {rows: rows, at: Date.now()}; draw(); })
        .catch(function(e){ el.innerHTML = '<span style="color:#E65A96;font-size:13px">Could not load venues: ' + esc(e.message) + '</span>'; });
    }
    function draw(){
      var h = CSS + '<div style="font-size:12.5px;color:#6B6280;margin-bottom:6px">Venues the client is considering — mark the one they pick as <b>Final</b>. The Final venue shares its details (lift, rules, ceiling, plug points, photos) with this party’s venue form, and each new recce updates it for next time.</div>';
      h += rows.length ? rows.map(function(v){
        var facts = [v.venue_type, v.ceiling ? 'Ceiling ' + v.ceiling : null, v.plug16 ? '16A: ' + v.plug16 : null, v.media ? v.media + ' photos' : null, v.recce_at ? 'Recce ' + v.recce_at : null].filter(Boolean);
        return '<div class="lv-row"><div class="lv-name"><a href="venues.html#v=' + v.id + '" target="_blank" rel="noopener">' + esc(v.name) + ' ↗</a>'
          + '<div class="lv-sub">' + esc([v.address].concat(facts).filter(Boolean).join(' · ')) + '</div></div>'
          + '<select class="lv-st ' + v.status + '" data-st="' + v.id + '">' + ST.map(function(s){ return '<option value="' + s[0] + '"' + (s[0] === v.status ? ' selected' : '') + '>' + s[1] + '</option>'; }).join('') + '</select>'
          + '<button type="button" class="lv-btn" data-un="' + v.id + '" title="Unlink">✕</button></div>';
      }).join('') : '<div style="font-size:13px;color:#6B6280;padding:4px 0">No venue linked yet.</div>';
      h += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:flex-start">'
        + '<a class="lv-btn pk" href="venues.html?new=1&lead=' + leadId + '" target="_blank" rel="noopener">＋ New venue</a>'
        + '<div style="flex:1;min-width:220px"><input class="lv-search" placeholder="Link an existing venue — type its name…"><div class="lv-res" hidden></div></div></div>';
      el.innerHTML = h;
      el.querySelectorAll('[data-st]').forEach(function(s){ s.onchange = function(){ link(+s.dataset.st, s.value); }; });
      el.querySelectorAll('[data-un]').forEach(function(b){ b.onclick = function(){
        if(!confirm('Unlink this venue from the party? The venue stays in the venue list.')) return;
        apiCall('/api/admin/venues/' + b.dataset.un + '/link/' + leadId, {method:'DELETE'}).then(function(d){ rows = d.venues; draw(); }).catch(function(e){ alert(e.message); });
      }; });
      var inp = el.querySelector('.lv-search'), res = el.querySelector('.lv-res'), t = null;
      inp.oninput = function(){
        clearTimeout(t);
        var q = inp.value.trim();
        if(q.length < 2){ res.hidden = true; return; }
        t = setTimeout(function(){
          apiCall('/api/admin/venues?q=' + encodeURIComponent(q)).then(function(d){
            var have = rows.map(function(r){ return r.id; });
            var list = (d.venues || []).filter(function(v){ return have.indexOf(v.id) < 0; }).slice(0, 12);
            res.innerHTML = list.length ? list.map(function(v){ return '<div data-pick="' + v.id + '"><b>' + esc(v.name) + '</b>' + (v.address ? '<br><span class="lv-sub">' + esc(v.address) + '</span>' : '') + '</div>'; }).join('')
              : '<div style="cursor:default;color:#6B6280">No match — use “New venue”.</div>';
            res.hidden = false;
            res.querySelectorAll('[data-pick]').forEach(function(p){ p.onclick = function(){ link(+p.dataset.pick, 'shortlisted'); }; });
          }).catch(function(){});
        }, 300);
      };
    }
    function link(vid, status){
      apiCall('/api/admin/venues/' + vid + '/link', {method:'POST', body: JSON.stringify({lead_id: leadId, status: status, changed_by: who()})})
        .then(function(d){ rows = d.venues; draw(); }).catch(function(e){ alert(e.message); });
    }
    // Refresh when the user comes back from the venue page (e.g. after creating one).
    if(!el._lvFocus){ el._lvFocus = true; window.addEventListener('focus', function(){ if(document.body.contains(el)) load(); }); }
    // Pages that redraw often (sales lead) reuse the last list for 60 s.
    var c = CACHE[leadId];
    if(c && Date.now() - c.at < 60000){ rows = c.rows; draw(); return; }
    el.innerHTML = '<span style="font-size:12.5px;color:#6B6280">Loading venues…</span>';
    load();
  }
  var CACHE = {};
  window.LeadVenues = {mount: mount};
})();
