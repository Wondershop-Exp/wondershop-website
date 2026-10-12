// "Carnival Stalls & Mascots" section of the partner onboarding form
// (2026-10-12, per Shruti). Shown when that option is picked. Exposes
// window.WSCarnival:
//   toggle(on)      show / hide the section
//   validate()      -> {error, el} for the first problem, or {} when complete
//   appendTo(fd)    adds carnival_profile (JSON) and the catalogue files
//   fill(profile)   pre-fills from an update link
// Zones come from js/volunteer-data.js (same 6 Mumbai zones everywhere).
(function () {
  var host = document.getElementById('carnivalSection');
  if (!host) return;
  var ZONES = (window.WS_VOLUNTEER && window.WS_VOLUNTEER.zones) || [];
  var SERVICES = ['Mascots', 'Carnival game stalls', 'Inflatables / bouncy castle', 'Cotton candy', 'Popcorn',
    'Chocolate fondue', 'Trampoline', 'Slush / ice gola', 'Tattoo / face painting'];
  var HINTS = {
    'Mascots': 'Characters available and price per appearance',
    'Carnival game stalls': 'Games available and price per stall',
    'Inflatables / bouncy castle': 'Sizes and price'
  };
  var HEADSUP = ['24 hours', '2 days', '3 days', '1 week', '2 weeks or more'];
  var SETUP = ['Under 30 min', '30 – 60 min', '1 – 2 hours', 'More than 2 hours'];
  var MAX_FILES = 10, MAX_BYTES = 10 * 1024 * 1024, MAX_TOTAL = 50 * 1024 * 1024;
  var OK_TYPES = /^(application\/pdf|image\/(jpeg|png|webp))$/;
  var files = [];          // File objects chosen so far
  var custom = [];         // services the partner typed in
  var details = {};        // service name -> details text (kept while toggling)

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function opts(list, ph) {
    return '<option value="">' + ph + '</option>' + list.map(function (v) { return '<option>' + esc(v) + '</option>'; }).join('');
  }
  function size(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; }

  host.innerHTML =
    '<div class="sec-h">What you offer</div>' +
    '<div class="sec-sub">Tick everything you can provide. A short line on each helps us quote correctly.</div>' +
    '<div class="vl-chips" id="cv_chips"></div>' +
    '<div class="fld"><label>Something else? Add it <span class="opt">(as many as you like)</span></label>' +
      '<div style="display:flex;gap:8px"><input type="text" id="cv_add" maxlength="60" placeholder="e.g. Popsicle cart, Nail art, Sand art">' +
      '<button type="button" class="cv-add-btn" id="cv_add_btn">Add</button></div></div>' +
    '<div id="cv_details"></div>' +
    '<div class="sec-h">Catalogues &amp; photos</div>' +
    '<div class="sec-sub">Upload your brochures, price lists and photos of past setups. You can add several files.</div>' +
    '<label class="upload-box" for="cv_files"><input type="file" id="cv_files" multiple accept="application/pdf,image/jpeg,image/png,image/webp">' +
      '<div class="ic">📚</div><div class="txt">Tap to upload catalogues or photos</div></label>' +
    '<div class="upload-note">PDF, JPG or PNG · up to ' + MAX_FILES + ' files · 10 MB each</div>' +
    '<ul class="cv-files" id="cv_list"></ul>' +
    '<div class="sec-h">Booking terms</div>' +
    '<div class="row2">' +
      '<div class="fld"><label>Heads-up time needed *</label><select id="cv_headsup">' + opts(HEADSUP, 'Select...') + '</select></div>' +
      '<div class="fld"><label>Setup time at venue <span class="opt">(optional)</span></label><select id="cv_setup">' + opts(SETUP, 'Select...') + '</select></div>' +
    '</div>' +
    '<div class="fld"><label>What you need from the venue <span class="opt">(optional)</span></label><input type="text" id="cv_needs" maxlength="300" placeholder="e.g. 1 power point (15 Amp), 15×15 ft open space"></div>' +
    '<div class="row2">' +
      '<div class="fld"><label>Minimum order / booking value <span class="opt">(optional)</span></label><input type="text" id="cv_min" maxlength="60" placeholder="e.g. ₹5,000"></div>' +
      '<div class="fld"><label>Instagram / website <span class="opt">(optional)</span></label><input type="text" id="cv_ig" maxlength="200" placeholder="e.g. @yourpage"></div>' +
    '</div>' +
    '<div class="sec-h">Service areas *</div>' +
    '<div class="sec-sub">Which parts of Mumbai do you cover? Pick all that apply.</div>' +
    '<div class="vl-zones" id="cv_zones">' + ZONES.map(function (z) {
      return '<label class="vl-zone"><input type="checkbox" name="cv_zone" value="' + z.n + '"><span><b>' + z.n + ' · ' + esc(z.en) + '</b><small>' + esc(z.areas) + '</small></span></label>';
    }).join('') + '</div>' +
    '<div class="fld"><label>Extra travel charge outside these areas <span class="opt">(optional)</span></label><input type="text" id="cv_travel" maxlength="200" placeholder="e.g. ₹1,500 for zones 5 and 6"></div>';

  var chipsEl = document.getElementById('cv_chips');
  var detailsEl = document.getElementById('cv_details');

  function checkedServices() {
    return Array.prototype.map.call(chipsEl.querySelectorAll('input:checked'), function (i) { return i.value; });
  }
  function saveDetails() {
    detailsEl.querySelectorAll('textarea[data-s]').forEach(function (t) { details[t.getAttribute('data-s')] = t.value; });
  }
  function drawChips(keep) {
    var on = keep || checkedServices();
    chipsEl.innerHTML = SERVICES.concat(custom).map(function (s) {
      return '<label class="vl-chip"><input type="checkbox" value="' + esc(s) + '"' + (on.indexOf(s) >= 0 ? ' checked' : '') + '><span><b>' + esc(s) + '</b></span></label>';
    }).join('');
  }
  function drawDetails() {
    saveDetails();
    detailsEl.innerHTML = checkedServices().map(function (s) {
      return '<div class="cv-svc"><div class="cv-svc-h">' + esc(s) + '</div>' +
        '<textarea data-s="' + esc(s) + '" maxlength="1500" placeholder="' + esc(HINTS[s] || 'Details and price') + '">' + esc(details[s] || '') + '</textarea></div>';
    }).join('');
  }
  chipsEl.addEventListener('change', drawDetails);
  function addCustom() {
    var inp = document.getElementById('cv_add');
    var v = inp.value.trim().replace(/\s+/g, ' ');
    if (!v) return;
    var all = SERVICES.concat(custom).map(function (x) { return x.toLowerCase(); });
    var on = checkedServices();
    if (all.indexOf(v.toLowerCase()) < 0) custom.push(v);
    else v = SERVICES.concat(custom)[all.indexOf(v.toLowerCase())];
    if (on.indexOf(v) < 0) on.push(v);
    saveDetails(); drawChips(on); drawDetails();
    inp.value = ''; inp.focus();
  }
  document.getElementById('cv_add_btn').addEventListener('click', addCustom);
  document.getElementById('cv_add').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addCustom(); } });

  var listEl = document.getElementById('cv_list');
  function drawFiles() {
    listEl.innerHTML = files.map(function (f, i) {
      return '<li><span>' + esc(f.name) + '</span><span>' + size(f.size) + ' <button type="button" data-rm="' + i + '" aria-label="Remove">✕</button></span></li>';
    }).join('');
  }
  listEl.addEventListener('click', function (e) {
    var b = e.target.closest('[data-rm]'); if (!b) return;
    files.splice(+b.getAttribute('data-rm'), 1); drawFiles();
  });
  document.getElementById('cv_files').addEventListener('change', function () {
    var bad = '';
    Array.prototype.forEach.call(this.files, function (f) {
      if (!OK_TYPES.test(f.type)) { bad = f.name + ' is not a PDF or photo.'; return; }
      if (f.size > MAX_BYTES) { bad = f.name + ' is larger than 10 MB.'; return; }
      if (files.length >= MAX_FILES) { bad = 'You can add up to ' + MAX_FILES + ' files.'; return; }
      files.push(f);
    });
    this.value = '';
    drawFiles();
    if (bad && window.showErr) window.showErr(bad);
  });

  drawChips([]);

  window.WSCarnival = {
    toggle: function (on) { host.hidden = !on; },
    validate: function () {
      var svc = checkedServices();
      if (!svc.length) return { error: 'Please tick at least one service you offer.', el: chipsEl };
      if (!document.getElementById('cv_headsup').value) return { error: 'Please choose the heads-up time you need.', el: document.getElementById('cv_headsup') };
      if (!document.querySelectorAll('#cv_zones input:checked').length) return { error: 'Please pick the areas of Mumbai you cover.', el: document.getElementById('cv_zones') };
      var total = files.reduce(function (t, f) { return t + f.size; }, 0);
      if (total > MAX_TOTAL) return { error: 'Your files add up to more than 50 MB — please remove a few.', el: listEl };
      return {};
    },
    appendTo: function (fd) {
      saveDetails();
      var profile = {
        services: checkedServices().map(function (s) { return { name: s, details: (details[s] || '').trim() }; }),
        headsup: document.getElementById('cv_headsup').value,
        setup_time: document.getElementById('cv_setup').value,
        venue_needs: document.getElementById('cv_needs').value.trim(),
        min_order: document.getElementById('cv_min').value.trim(),
        instagram: document.getElementById('cv_ig').value.trim(),
        zones: Array.prototype.map.call(document.querySelectorAll('#cv_zones input:checked'), function (i) { return +i.value; }),
        travel_charge: document.getElementById('cv_travel').value.trim()
      };
      fd.append('carnival_profile', JSON.stringify(profile));
      files.forEach(function (f) { fd.append('catalogues', f, f.name); });
    },
    fill: function (p) {
      if (!p) return;
      var names = (p.services || []).map(function (s) { return s.name; });
      (p.services || []).forEach(function (s) {
        details[s.name] = s.details || '';
        if (SERVICES.indexOf(s.name) < 0 && custom.indexOf(s.name) < 0) custom.push(s.name);
      });
      drawChips(names); drawDetails();
      var set = function (id, v) { var el = document.getElementById(id); if (el && v) el.value = v; };
      set('cv_headsup', p.headsup); set('cv_setup', p.setup_time); set('cv_needs', p.venue_needs);
      set('cv_min', p.min_order); set('cv_ig', p.instagram); set('cv_travel', p.travel_charge);
      (p.zones || []).forEach(function (n) { var el = document.querySelector('#cv_zones input[value="' + n + '"]'); if (el) el.checked = true; });
    }
  };
})();
