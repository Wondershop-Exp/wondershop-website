/* Decorator Job Card on the booking page — 2026-11-16, per Shruti.
 *
 * "help make a job card for decorators" — pre-filled from the booking, the
 * team fills in what's missing, then sends the decorator a WhatsApp image +
 * short text + a link (decor-job.html?t=…) where they see everything and
 * upload the completion photos. The decorator never sees the client's name
 * or phone; the child's name only when "decorator needs the child's name" is
 * ticked (name lights / letters). Backend: backend/routers/decor_jobs.py.
 * ADMIN ONLY (the amount is a payout): hidden for the sales login.
 *
 * Uses admin.html globals: API, apiCall, esc, getName, getPw, showToast,
 * ROLE, CURRENT_LEAD_ID, highlightWhoName, bookingCanShareFiles.
 */
(function(){
let DJ = null;          // last payload from the API
let DJ_DATA = null;     // the form's working copy of the card data
let DJ_LEAD = null;

const STANDS = ['Circle', 'Rectangle', 'Circle + Rectangle', 'Arch frame'];
const AGE_ITEMS = ['Foil balloon', 'Light', 'Not needed'];

window.renderDecorJob = async function(d){
  const sec = document.getElementById('djSection'), block = document.getElementById('djBlock');
  if(!sec || !block) return;
  sec.style.display = 'none'; block.innerHTML = '';
  if(!d || !d.is_booking || ROLE === 'sales') return;
  DJ_LEAD = d.lead_id;
  try{ DJ = await apiCall('/api/admin/decor-job/'+d.lead_id); }
  catch(e){ return; }   // sales login / older backend: no section
  if(String(CURRENT_LEAD_ID) !== String(DJ_LEAD)) return;
  DJ_DATA = JSON.parse(JSON.stringify(DJ.data || {}));
  sec.style.display = 'block';
  djDraw();
};

function v(x){ return esc(x == null ? '' : String(x)); }
function opts(list, cur){
  const all = Array.from(new Set(list.concat(cur && !list.includes(cur) ? [cur] : [])));
  return all.map(o=>'<option'+(o===cur?' selected':'')+'>'+esc(o)+'</option>').join('');
}
function row(label, html, hint){
  return '<label class="dj-f"><span>'+label+'</span>'+html+(hint?'<small>'+hint+'</small>':'')+'</label>';
}
function inp(id, val, ph, extra){ return '<input type="text" id="'+id+'" value="'+v(val)+'" placeholder="'+v(ph||'')+'" '+(extra||'')+'>'; }

function djDraw(){
  const block = document.getElementById('djBlock'); if(!block) return;
  const a = DJ.auto || {}, d = DJ_DATA, card = DJ.card;
  const photos = DJ.photos || [];
  const done = {}; photos.filter(p=>p.kind==='done').forEach(p=>done[p.slot]=p);
  const refs = {}; photos.filter(p=>p.kind==='ref').forEach(p=>refs[p.slot]=p);
  const nBoxes = (d.photos||[]).length, nDone = (d.photos||[]).filter(p=>done[p.slot]).length;

  let status;
  if(!card) status = '<span class="dj-chip">Not saved yet</span>';
  else if(card.approved_at) status = '<span class="dj-chip ok">✓ Decor approved'+(card.approved_by?' by '+esc(card.approved_by):'')+'</span>';
  else if(nDone) status = '<span class="dj-chip warn">'+nDone+' of '+nBoxes+' photos in</span>';
  else if(card.opened_at) status = '<span class="dj-chip">Link opened · waiting for photos</span>';
  else if(card.copied_at) status = '<span class="dj-chip">Message copied · link not opened yet</span>';
  else status = '<span class="dj-chip">Saved · not sent yet</span>';

  const pics = (a.pictures||[]).map(p=>'<a href="'+v(p.url)+'" target="_blank"><img src="'+v(p.url)+'" alt="'+v(p.label)+'"></a>').join('');
  const refBoxes = ['ref-1','ref-2','ref-3'].map(s=>refs[s]
    ? '<div class="dj-ref"><a href="'+v(refs[s].url)+'" target="_blank"><img src="'+v(refs[s].url)+'" alt="Extra reference"></a><button type="button" class="icon-btn" title="Remove" onclick="djRemovePhoto(\''+s+'\',\'ref\')">✕</button></div>'
    : '<label class="dj-ref add"'+(card?'':' title="Save the job card first"')+'>+ Add pic<input type="file" accept="image/*" hidden '+(card?'':'disabled')+' onchange="djUpload(\''+s+'\',\'ref\',this)"></label>').join('');

  const comps = (d.components||[]).map((c,i)=>'<tr data-i="'+i+'"'+(c.on?'':' class="off"')+'>'
    + '<td style="width:34px"><input type="checkbox" class="dj-c-on" '+(c.on?'checked':'')+' aria-label="Include '+v(c.label)+'" onchange="this.closest(\'tr\').classList.toggle(\'off\',!this.checked)"></td>'
    + '<td><input type="text" class="dj-c-label" value="'+v(c.label)+'" aria-label="Item"></td>'
    + '<td style="width:130px"><input type="text" class="dj-c-qty" value="'+v(c.qty)+'" placeholder="Qty / size" aria-label="Qty / size"></td>'
    + '<td><input type="text" class="dj-c-notes" value="'+v(c.notes)+'" placeholder="Notes" aria-label="Notes"></td>'
    + '<td style="width:30px"><button type="button" class="icon-btn" title="Remove" onclick="djRemoveRow(\'components\','+i+')">✕</button></td></tr>').join('');

  const rets = (d.returns||[]).map((r,i)=>'<tr data-i="'+i+'"><td><input type="text" class="dj-r-item" value="'+v(r.item)+'" placeholder="e.g. Fairy light string" aria-label="Item to return"></td>'
    + '<td style="width:90px"><input type="text" class="dj-r-qty" value="'+v(r.qty)+'" placeholder="Qty" aria-label="Qty"></td>'
    + '<td style="width:30px"><button type="button" class="icon-btn" title="Remove" onclick="djRemoveRow(\'returns\','+i+')">✕</button></td></tr>').join('');

  const boxes = (d.photos||[]).map((p,i)=>{
    const got = done[p.slot];
    return '<div class="dj-ph'+(got?' got':'')+'" data-i="'+i+'" data-slot="'+v(p.slot)+'">'
      + (got ? '<a href="'+v(got.url)+'" target="_blank" class="dj-ph-img"><img src="'+v(got.url)+'" alt="'+v(p.label)+'"></a>'
             : '<div class="dj-ph-img empty">Waiting</div>')
      + '<input type="text" class="dj-p-label" value="'+v(p.label)+'" placeholder="Photo name" aria-label="Photo name">'
      + '<input type="text" class="dj-p-hint" value="'+v(p.hint)+'" placeholder="Hint for the decorator" aria-label="Hint">'
      + '<div class="dj-ph-act">'
        + (got ? '<span class="ok">✓ '+(got.source==='team'?'added by team':'sent')+'</span><button type="button" class="mini-btn" onclick="djRemovePhoto(\''+v(p.slot)+'\',\'done\')" title="Empty this box so the decorator sends it again">Ask re-take</button>'
               : (card && p.slot ? '<label class="mini-btn" title="Got it on WhatsApp? Add it here">Upload<input type="file" accept="image/*" hidden onchange="djUpload(\''+v(p.slot)+'\',\'done\',this)"></label>' : '')
                 + '<button type="button" class="icon-btn" title="Remove this box" onclick="djRemoveRow(\'photos\','+i+')">✕</button>')
      + '</div></div>';
  }).join('');

  const share = (typeof bookingCanShareFiles==='function' && bookingCanShareFiles());
  block.innerHTML =
    '<div class="dj-top">'+status
      + (DJ.stale ? '<span class="dj-chip warn" title="Date, time, venue, age, theme or decor changed on the booking. Save here to update the decorator\'s link.">Booking changed — save to update the link</span>' : '')
      + '<div class="fb-btns">'
        + '<button class="fb-btn pk" onclick="djSave(this)">'+(card?'Save':'Create job card')+'</button>'
        + '<button class="fb-btn gh" onclick="djCopy(this)">📋 Copy WhatsApp message</button>'
        + '<button class="fb-btn gh" onclick="djImage(false,this)">🖼️ Download image</button>'
        + (share ? '<button class="fb-btn wa" onclick="djImage(true,this)">📤 Share image + message</button>' : '')
        + (card ? '<a class="fb-btn gh" href="'+v(card.link)+'" target="_blank">Open decorator link ↗</a>' : '')
      + '</div></div>'
    + '<div class="dj-title">Decorator sees: <b>'+esc(DJ.title||'')+'</b><small>No client name or phone. Coordinator only.</small></div>'

    + '<div class="dj-h">1. From the booking <small>change these on the booking above, then save here</small></div>'
    + '<div class="dj-auto">'
      + [['Date', a.event_date], ['Age', a.age], ['Theme', a.theme], ['Package', (a.package||'') + (a.decor_name && a.decor_name!==a.package ? ' ('+a.decor_name+')' : '')],
         ['Party starts', a.event_time], ['Venue handover', a.handover], ['Venue packup', a.packup],
         ['Venue', a.venue], ['Maps link', a.maps]]
        .map(([k,x])=>'<div><span>'+k+'</span><b>'+(!x ? '<em>missing</em>' : (k==='Maps link' ? '<a href="'+v(x)+'" target="_blank">open ↗</a>' : esc(x)))+'</b></div>').join('')
    + '</div>'

    + '<div class="dj-h">2. Decorator, times &amp; venue</div>'
    + '<div class="dj-grid">'
      + row('Decorator', inp('djDecorator', DJ.decorator, 'Partner name', 'list="vendorNamesList" autocomplete="off"'), DJ.partner_row && DJ.partner_row.partner ? 'From Partners &amp; Expenses: '+esc(DJ.partner_row.partner) : '')
      + row('Ready by', inp('djReady', d.ready_by, a.event_time ? 'Party start: '+a.event_time : 'e.g. 4:30 PM'), 'Shown in the title. Empty = party start time.')
      + row('Floor / hall', inp('djFloor', d.floor, 'e.g. 3rd floor, Party Hall'))
      + row('Colours', inp('djColours', d.colours, 'e.g. Pink, lilac, gold'))
    + '</div>'
    + row('Venue notes', '<textarea id="djVenueNotes" rows="2" placeholder="e.g. Use service lift. No tape on walls.">'+v(d.venue_notes)+'</textarea>')

    + '<div class="dj-h">3. Decor pictures</div>'
    + '<div class="dj-pics">'+(pics || '<span class="dj-muted">No decor picture on the booking yet (finalize the decor design or upload a reference).</span>')+refBoxes+'</div>'

    + '<div class="dj-h">4. Decor components <small>unticked rows are hidden from the decorator</small></div>'
    + '<div style="overflow-x:auto"><table class="team-tbl dj-tbl" id="djComps"><tbody>'+comps+'</tbody></table></div>'
    + '<div class="fb-btns" style="margin:6px 0 10px"><button class="fb-btn gh" onclick="djAddRow(\'components\')">+ Add item</button></div>'
    + row('Custom requests from the client', '<textarea id="djCustom" rows="2" placeholder="Anything special the decorator must make">'+v(d.custom_requests)+'</textarea>')
    + '<label class="dj-check"><input type="checkbox" id="djNameNeeded" '+(d.child_name_needed?'checked':'')+' onchange="document.getElementById(\'djNameWrap\').style.display=this.checked?\'\':\'none\'"> Decorator needs the child\'s name</label>'
    + '<div class="dj-muted" style="margin:-2px 0 6px 26px">Only when they make something with the name, e.g. name lights or letters. Leave off when the name is already on the flex.</div>'
    + '<div id="djNameWrap" style="margin-left:26px;max-width:320px;'+(d.child_name_needed?'':'display:none')+'">'+row('Name to show', inp('djChildName', d.child_name, a.child_name || 'Child\'s name'))+'</div>'

    + '<div class="dj-h">5. Materials</div>'
    + '<div class="dj-grid">'
      + row('From Wondershop (to pick up)', inp('djOurs', (d.ours||[]).join(', '), 'Flex, Cutouts, Welcome poster'), 'Separate with commas')
      + row('Pickup location', inp('djPickup', d.pickup_location, 'Wondershop office'))
      + row('Pick up before', inp('djPickupBy', d.pickup_by, 'e.g. Sun 22 Nov, 1 PM'))
    + '</div>'
    + '<div class="dj-grid">'
      + row('Stand (they bring)', '<input type="text" id="djStand" list="djStandList" value="'+v(d.stand)+'" placeholder="Circle / Rectangle"><datalist id="djStandList">'+STANDS.map(x=>'<option value="'+esc(x)+'">').join('')+'</datalist>')
      + row('Balloons (they bring)', inp('djBalloons', d.balloons, 'e.g. 80 balloons, pink / lilac / gold'))
      + row('Age '+(a.age?'"'+esc(a.age)+'" ':'')+'(they bring)', '<select id="djAgeItem">'+opts(AGE_ITEMS, d.age_item||'Foil balloon')+'</select>')
      + row('Cake table (they bring)', '<input type="text" id="djCake" list="djCakeList" value="'+v(d.cake_table||'No')+'"><datalist id="djCakeList"><option value="Yes"><option value="No"></datalist>', 'Yes / No, or details')
    + '</div>'
    + row('Anything else they bring', inp('djBringOther', d.bring_other, ''))

    + '<div class="dj-h">6. Amount &amp; coordinator</div>'
    + '<div class="dj-grid">'
      + row('Agreed amount (₹, shown to decorator)', '<input type="number" id="djAmount" min="0" step="1" value="'+(d.amount==null?'':v(d.amount))+'" placeholder="₹">', DJ.partner_row && DJ.partner_row.amount!=null ? 'Partners &amp; Expenses: ₹'+esc(DJ.partner_row.amount) : '')
      + row('Coordinator name', inp('djCoordName', d.coordinator_name || localStorage.getItem('ws_dj_coord_name') || '', 'Wondershop coordinator'))
      + row('Coordinator phone', inp('djCoordPhone', d.coordinator_phone || localStorage.getItem('ws_dj_coord_phone') || '', '98xxxxxxxx', 'inputmode="tel"'))
    + '</div>'

    + '<div class="dj-h">7. To return to Wondershop <small>optional — only shown when filled</small></div>'
    + '<table class="team-tbl dj-tbl" id="djReturns"><tbody>'+rets+'</tbody></table>'
    + '<div class="fb-btns" style="margin-top:6px"><button class="fb-btn gh" onclick="djAddRow(\'returns\')">+ Add item</button></div>'

    + '<div class="dj-h">8. Completion photos <small>'+(card ? nDone+' of '+nBoxes+' in' : 'each box is a photo the decorator sends')+'</small></div>'
    + '<div class="dj-phs" id="djPhotos">'+boxes+'</div>'
    + '<div class="fb-btns" style="margin-top:8px"><button class="fb-btn gh" onclick="djAddRow(\'photos\')">+ Add photo box</button>'
      + (card ? (card.approved_at
          ? '<button class="fb-btn gh" onclick="djApprove(false,this)">Undo approval</button>'
          : '<button class="fb-btn pk" '+(nDone?'':'disabled title="No photos yet"')+' onclick="djApprove(true,this)">✓ Approve decor</button>') : '')
    + '</div>'
    + (card ? '<div class="fb-meta">Saved '+esc(card.updated_at||'')+(card.updated_by?' by '+esc(card.updated_by):'')
        + (card.copied_at?' · message copied '+esc(card.copied_at):'')+(card.opened_at?' · decorator opened the link '+esc(card.opened_at):'')+'</div>' : '');
}

function readForm(){
  const g = id => (document.getElementById(id)||{}).value || '';
  const d = DJ_DATA;
  d.components = Array.from(document.querySelectorAll('#djComps tbody tr')).map(tr=>{
    const old = d.components[+tr.dataset.i] || {};
    return {key: old.key||'', label: tr.querySelector('.dj-c-label').value.trim(), on: tr.querySelector('.dj-c-on').checked,
            qty: tr.querySelector('.dj-c-qty').value.trim(), notes: tr.querySelector('.dj-c-notes').value.trim()};
  });
  d.returns = Array.from(document.querySelectorAll('#djReturns tbody tr')).map(tr=>({
    item: tr.querySelector('.dj-r-item').value.trim(), qty: tr.querySelector('.dj-r-qty').value.trim()}));
  d.photos = Array.from(document.querySelectorAll('#djPhotos .dj-ph')).map(el=>({
    slot: el.dataset.slot||'', label: el.querySelector('.dj-p-label').value.trim(), hint: el.querySelector('.dj-p-hint').value.trim()}));
  d.ready_by = g('djReady').trim(); d.floor = g('djFloor').trim(); d.colours = g('djColours').trim();
  d.venue_notes = g('djVenueNotes').trim(); d.custom_requests = g('djCustom').trim();
  d.child_name_needed = !!(document.getElementById('djNameNeeded')||{}).checked; d.child_name = g('djChildName').trim();
  d.ours = g('djOurs').split(',').map(x=>x.trim()).filter(Boolean);
  d.pickup_location = g('djPickup').trim(); d.pickup_by = g('djPickupBy').trim();
  d.stand = g('djStand').trim(); d.balloons = g('djBalloons').trim(); d.age_item = g('djAgeItem');
  d.cake_table = g('djCake').trim() || 'No'; d.bring_other = g('djBringOther').trim();
  d.amount = g('djAmount') === '' ? null : Number(g('djAmount'));
  d.coordinator_name = g('djCoordName').trim(); d.coordinator_phone = g('djCoordPhone').trim();
  DJ.decorator = g('djDecorator').trim();
  return d;
}

window.djAddRow = function(kind){
  readForm();
  if(kind==='components') DJ_DATA.components.push({key:'', label:'', on:true, qty:'', notes:''});
  if(kind==='returns') DJ_DATA.returns.push({item:'', qty:''});
  if(kind==='photos') DJ_DATA.photos.push({slot:'', label:'', hint:''});
  djDraw();
};
window.djRemoveRow = function(kind, i){ readForm(); DJ_DATA[kind].splice(i,1); djDraw(); };

async function save(quiet){
  const who = getName();
  if(!who){ showToast('⚠ Set "Editing as" name at the top first.'); if(typeof highlightWhoName==='function') highlightWhoName(); return false; }
  const data = readForm();
  if(data.coordinator_name) localStorage.setItem('ws_dj_coord_name', data.coordinator_name);
  if(data.coordinator_phone) localStorage.setItem('ws_dj_coord_phone', data.coordinator_phone);
  DJ = await apiCall('/api/admin/decor-job/'+DJ_LEAD, {method:'POST', body: JSON.stringify({decorator: DJ.decorator, data, changed_by: who})});
  DJ_DATA = JSON.parse(JSON.stringify(DJ.data||{}));
  djDraw();
  if(!quiet) showToast('✓ Job card saved');
  return true;
}
window.djSave = async function(btn){
  btn.disabled = true;
  try{ await save(false); }catch(e){ if(e.message!=='unauthorized') showToast('Could not save: '+e.message); }
  finally{ btn.disabled = false; }
};

function copyText(t){
  function fallback(){ const ta=document.createElement('textarea'); ta.value=t; ta.style.position='fixed'; ta.style.opacity='0';
    document.body.appendChild(ta); ta.select(); try{ document.execCommand('copy'); }catch(e){} ta.remove(); }
  if(navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t).catch(fallback);
  fallback(); return Promise.resolve();
}
function markCopied(){ apiCall('/api/admin/decor-job/'+DJ_LEAD+'/copied', {method:'POST', body:'{}'}).catch(()=>{}); }

window.djCopy = async function(btn){
  btn.disabled = true;
  try{
    if(!(await save(true))) return;
    await copyText(DJ.message||'');
    markCopied();
    showToast('✓ Saved and copied — paste it in WhatsApp with the image');
  }catch(e){ if(e.message!=='unauthorized') showToast('Could not copy: '+e.message); }
  finally{ btn.disabled = false; }
};

// ── WhatsApp image: decor picture + age badge + the title band ──────────
function loadImg(url){
  return new Promise((res, rej)=>{ const im = new Image(); im.crossOrigin = 'anonymous';
    im.onload = ()=>res(im); im.onerror = rej; im.src = url; });
}
function wrapLines(ctx, text, maxW){
  const words = String(text).split(' '); const lines = []; let cur = '';
  words.forEach(w=>{ const t = cur ? cur+' '+w : w; if(ctx.measureText(t).width > maxW && cur){ lines.push(cur); cur = w; } else cur = t; });
  if(cur) lines.push(cur); return lines;
}
async function buildImage(){
  const vw = DJ.view || {}; const W = 1080, H = 1350, BAND = 330, PH = H - BAND;
  try{ await Promise.all([document.fonts.load('700 64px Lora'), document.fonts.load('700 40px "DM Sans"')]); }catch(e){}
  const c = document.createElement('canvas'); c.width = W; c.height = H; const x = c.getContext('2d');
  x.fillStyle = '#EDE6FA'; x.fillRect(0, 0, W, PH);
  const pic = (vw.pictures||[])[0];
  let drew = false;
  if(pic){
    try{
      const im = await loadImg(pic.url);
      const s = Math.max(W / im.width, PH / im.height), w = im.width * s, h = im.height * s;
      x.save(); x.beginPath(); x.rect(0, 0, W, PH); x.clip();
      x.drawImage(im, (W - w) / 2, (PH - h) / 2, w, h); x.restore(); drew = true;
    }catch(e){ drew = false; }
  }
  if(!drew){ x.fillStyle = '#6B7280'; x.font = '600 40px "DM Sans", sans-serif'; x.textAlign = 'center';
    x.fillText('Decor picture: open the link', W / 2, PH / 2); x.textAlign = 'left'; }
  if(vw.age){
    const t = 'AGE ' + vw.age; x.font = '800 46px "DM Sans", sans-serif';
    const tw = x.measureText(t).width + 56;
    x.fillStyle = '#E65A96'; x.beginPath();
    if(x.roundRect) x.roundRect(36, 36, tw, 84, 42); else x.rect(36, 36, tw, 84);
    x.fill(); x.fillStyle = '#fff'; x.fillText(t, 64, 94);
  }
  x.fillStyle = '#2E2438'; x.fillRect(0, PH, W, BAND);
  x.fillStyle = '#fff'; x.font = '700 68px Lora, serif';
  let y = PH + 100;
  wrapLines(x, [vw.date, vw.area].filter(Boolean).join(' | ') || vw.title || '', W - 112).slice(0, 2).forEach(l=>{ x.fillText(l, 56, y); y += 78; });
  x.font = '700 46px "DM Sans", sans-serif'; x.fillStyle = '#F5C3D7';
  x.fillText([vw.package, vw.times && vw.times.ready ? 'Ready by ' + vw.times.ready : ''].filter(Boolean).join(' · '), 56, y + 4);
  x.font = '500 30px "DM Sans", sans-serif'; x.fillStyle = '#B59DDE';
  x.fillText('Wondershop Experiences', 56, H - 40);
  return await new Promise((res, rej)=>{ try{ c.toBlob(b=>b?res(b):rej(new Error('image')), 'image/jpeg', 0.9); }catch(e){ rej(e); } });
}
window.djImage = async function(share, btn){
  btn.disabled = true;
  try{
    if(!(await save(true))) return;
    let blob;
    try{ blob = await buildImage(); }
    catch(e){ showToast('Could not make the image (decor picture blocked). Send the decor picture instead.'); return; }
    const name = (DJ.title||'decor-job').replace(/[^\w]+/g,'-').replace(/^-|-$/g,'') + '.jpg';
    const file = new File([blob], name, {type:'image/jpeg'});
    if(share && navigator.canShare && navigator.canShare({files:[file]})){
      await copyText(DJ.message||'');
      try{ await navigator.share({files:[file], text: DJ.message||''}); markCopied(); }catch(e){ /* share sheet closed */ }
      return;
    }
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(a.href), 4000);
    showToast('✓ Image downloaded');
  }catch(e){ if(e.message!=='unauthorized') showToast('Could not make the image: '+e.message); }
  finally{ btn.disabled = false; }
};

// ── photos ──────────────────────────────────────────────────────────────
function keepForm(body){ readForm(); const keep = DJ_DATA; DJ = body; DJ_DATA = keep; djDraw(); }

window.djUpload = async function(slot, kind, input){
  const f = input.files && input.files[0]; if(!f) return;
  const fd = new FormData(); fd.append('image', f); fd.append('kind', kind); fd.append('uploaded_by', getName()||'');
  showToast('Uploading…');
  try{
    const res = await fetch(API+'/api/admin/decor-job/'+DJ_LEAD+'/photo/'+encodeURIComponent(slot), {method:'POST', headers:{'X-Admin-Password': getPw()}, body: fd});
    const body = await res.json().catch(()=>({}));
    if(!res.ok) throw new Error(body.detail || ('Upload failed ('+res.status+')'));
    keepForm(body);
    showToast('✓ Photo added');
  }catch(e){ showToast(e.message); }
};
window.djRemovePhoto = async function(slot, kind){
  if(kind==='done' && !confirm('Empty this photo box? The decorator will be asked to send it again on the link.')) return;
  try{
    keepForm(await apiCall('/api/admin/decor-job/'+DJ_LEAD+'/photo/'+encodeURIComponent(slot)+'/remove', {method:'POST', body: JSON.stringify({kind, by:getName()})}));
    showToast(kind==='done' ? 'Box emptied — ask the decorator to send it again' : 'Picture removed');
  }catch(e){ if(e.message!=='unauthorized') showToast(e.message); }
};
window.djApprove = async function(ok, btn){
  const who = getName();
  if(!who){ showToast('⚠ Set "Editing as" name at the top first.'); if(typeof highlightWhoName==='function') highlightWhoName(); return; }
  btn.disabled = true;
  try{
    keepForm(await apiCall('/api/admin/decor-job/'+DJ_LEAD+'/approve', {method:'POST', body: JSON.stringify({approved: ok, by: who})}));
    showToast(ok ? '✓ Decor approved' : 'Approval undone');
  }catch(e){ btn.disabled = false; if(e.message!=='unauthorized') showToast(e.message); }
};
})();
