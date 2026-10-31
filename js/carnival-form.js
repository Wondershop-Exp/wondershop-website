// "Carnival Stalls & Mascots" section of the partner onboarding form
// (2026-10-12, per Shruti). Shown when that option is picked. Exposes
// window.WSCarnival:
//   toggle(on)      show / hide the section
//   validate()      -> {error, el} for the first problem, or {} when complete
//   appendTo(fd)    adds carnival_profile (JSON), the catalogue files and the
//                   stall photos
//   fill(profile)   pre-fills from an update link
// Zones come from js/volunteer-data.js (same 6 Mumbai zones everywhere).
//
// 2026-10-31, per Shruti: "apart from catalog upload, can you give an option
// where they can select the stall name or activity name, add pricing, details
// like - timings, takeaway, manpower included, photos upload of earlier work
// done. these can be any type of activities from art to food to live stations
// like printing". Each stall / activity is now its own card: picked from the
// list below (or typed in), with price + what the price is per, duration,
// takeaway for the kids, staff included, capacity, space & power, details and
// up to 5 photos of earlier work. Stall photos go up as "stall_photos" with the
// card number in the file name ("s3__name.jpg"), so the server can file each
// photo under its stall.
(function () {
  var host = document.getElementById('carnivalSection');
  if (!host) return;
  var ZONES = (window.WS_VOLUNTEER && window.WS_VOLUNTEER.zones) || [];
  var GROUPS = [
    ['Games', ['Carnival game stall', 'Hit the cans', 'Ring toss', 'Buzz wire', 'Catch the stick', 'Air hockey',
      'Reaction / street fight game', 'Snatch game', 'Basketball arcade', 'Dart game', 'Bowling', 'Giant board games']],
    ['Art & craft', ['Tattoo', 'Glitter tattoo', 'Face painting', 'Nail art', 'Mehendi', 'Slime making', 'Clay modelling',
      'Spin art', 'Sand art', 'Canvas painting', 'Bracelet / jewellery making', 'Pot / mirror painting', 'Soft toy making',
      'Balloon modelling', 'Origami']],
    ['Food & drinks', ['Cotton candy', 'Popcorn', 'Chocolate fondue', 'Slush / ice gola', 'Ice cream cart', 'Popsicle cart',
      'Mocktail bar', 'Chaat / pani puri counter', 'Live pizza / food counter', 'Candy / dessert bar']],
    ['Live stations', ['Live T-shirt printing', 'Tote bag printing', 'Mug printing', 'Cap printing', 'Photo booth / instant prints',
      'Live caricature', 'Name keychain / engraving', 'Calligraphy', 'Customised bookmarks']],
    ['Rides & play', ['Bouncy castle / inflatable', 'Trampoline', 'Toy train', 'Ball pool', 'Soft play area', 'Zorbing',
      'Merry-go-round', 'Bungee jumping']],
    ['Characters & shows', ['Mascots', 'Magic show', 'Puppet show', 'Bubble show', 'Science show', 'Juggler / stilt walker']]
  ];
  var CAT_OF = {};
  GROUPS.forEach(function (g) { g[1].forEach(function (n) { CAT_OF[n] = g[0]; }); });
  var UNITS = [['stall', 'per stall (flat)'], ['child', 'per child'], ['piece', 'per piece'], ['hour', 'per hour'], ['day', 'per day']];
  var DURATIONS = ['1 hour', '2 hours', '3 hours', '4 hours', 'Full event', 'Per piece (no time limit)'];
  var HEADSUP = ['24 hours', '2 days', '3 days', '1 week', '2 weeks or more'];
  var SETUP = ['Under 30 min', '30 – 60 min', '1 – 2 hours', 'More than 2 hours'];
  var MAX_FILES = 10, MAX_BYTES = 10 * 1024 * 1024, MAX_TOTAL = 50 * 1024 * 1024;
  var MAX_STALL_PHOTOS = 5;
  var OK_TYPES = /^(application\/pdf|image\/(jpeg|png|webp))$/;
  var files = [];          // catalogue File objects chosen so far
  var stalls = [];         // [{id, photos: [File], onFile: n}] — form values live in the DOM
  var nextId = 1;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function opts(list, ph) {
    return '<option value="">' + ph + '</option>' + list.map(function (v) { return '<option>' + esc(v) + '</option>'; }).join('');
  }
  function size(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; }
  function $(id) { return document.getElementById(id); }
  var nameOpts = '<option value="">Pick a stall / activity…</option>' +
    GROUPS.map(function (g) {
      return '<optgroup label="' + esc(g[0]) + '">' + g[1].map(function (n) { return '<option>' + esc(n) + '</option>'; }).join('') + '</optgroup>';
    }).join('') + '<option value="__other">Something else (type it)</option>';

  host.innerHTML =
    '<div class="sec-h">Your stalls &amp; activities</div>' +
    '<div class="sec-sub">Add each stall or activity you can bring — games, art, food, live printing, rides, shows. ' +
    'Give its price and what is included, and add a few photos of earlier events.</div>' +
    '<div id="cv_stalls"></div>' +
    '<button type="button" class="cv-add-stall" id="cv_add_stall">+ Add a stall / activity</button>' +
    '<div class="sec-h">Catalogues <span class="opt" style="font-family:var(--fb);font-weight:400;font-size:13px">(optional)</span></div>' +
    '<div class="sec-sub">Brochures or price lists, if you have them.</div>' +
    '<label class="upload-box" for="cv_files"><input type="file" id="cv_files" multiple accept="application/pdf,image/jpeg,image/png,image/webp">' +
      '<div class="ic">📚</div><div class="txt">Tap to upload catalogues</div></label>' +
    '<div class="upload-note">PDF, JPG or PNG · up to ' + MAX_FILES + ' files · 10 MB each</div>' +
    '<ul class="cv-files" id="cv_list"></ul>' +
    '<div class="sec-h">Booking terms</div>' +
    '<div class="row2">' +
      '<div class="fld"><label>Heads-up time needed *</label><select id="cv_headsup">' + opts(HEADSUP, 'Select...') + '</select></div>' +
      '<div class="fld"><label>Setup time at venue <span class="opt">(optional)</span></label><select id="cv_setup">' + opts(SETUP, 'Select...') + '</select></div>' +
    '</div>' +
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

  var stallsEl = $('cv_stalls');

  function stallHtml(s, n) {
    var p = 'cs' + s.id + '_';
    return '<div class="cv-stall" data-id="' + s.id + '">' +
      '<div class="cv-stall-hd"><b>Stall ' + n + '</b>' +
        (stalls.length > 1 ? '<button type="button" class="cv-rm" data-rm-stall="' + s.id + '">Remove</button>' : '') + '</div>' +
      '<div class="fld"><label>Stall / activity *</label><select id="' + p + 'pick">' + nameOpts + '</select></div>' +
      '<div class="fld" id="' + p + 'other_box" hidden><label>Name of the stall / activity *</label>' +
        '<input type="text" id="' + p + 'other" maxlength="60" placeholder="e.g. Sand art, Live candle making"></div>' +
      '<div class="row2">' +
        '<div class="fld"><label>Price (₹) *</label><input type="text" inputmode="numeric" maxlength="7" id="' + p + 'price" placeholder="e.g. 6500"></div>' +
        '<div class="fld"><label>Price is *</label><select id="' + p + 'unit">' +
          UNITS.map(function (u) { return '<option value="' + u[0] + '">' + esc(u[1]) + '</option>'; }).join('') + '</select></div>' +
      '</div>' +
      '<div class="row2">' +
        '<div class="fld"><label>Time included *</label><select id="' + p + 'dur">' + opts(DURATIONS, 'Select...') + '</select></div>' +
        '<div class="fld"><label>Extra hour charge <span class="opt">(optional)</span></label><input type="text" inputmode="numeric" maxlength="6" id="' + p + 'extra" placeholder="₹"></div>' +
      '</div>' +
      '<div class="row2">' +
        '<div class="fld"><label>Staff included *</label><input type="text" inputmode="numeric" maxlength="2" id="' + p + 'staff" placeholder="e.g. 1"></div>' +
        '<div class="fld"><label>Kids it can serve <span class="opt">(optional)</span></label><input type="text" maxlength="40" id="' + p + 'cap" placeholder="e.g. 40 kids an hour"></div>' +
      '</div>' +
      '<div class="fld"><label>Do kids take something home? *</label><div class="vl-radios">' +
        '<label class="vl-radio"><input type="radio" name="' + p + 'take" value="yes"><span>Yes</span></label>' +
        '<label class="vl-radio"><input type="radio" name="' + p + 'take" value="no"><span>No</span></label></div></div>' +
      '<div class="fld" id="' + p + 'takewhat_box" hidden><label>What do they take home? *</label>' +
        '<input type="text" id="' + p + 'takewhat" maxlength="150" placeholder="e.g. printed tee, slime jar, framed sand art"></div>' +
      '<div class="fld"><label>Space &amp; power needed <span class="opt">(optional)</span></label>' +
        '<input type="text" id="' + p + 'space" maxlength="200" placeholder="e.g. 6×6 ft, 1 table, 1 power point"></div>' +
      '<div class="fld"><label>Anything else about this stall <span class="opt">(optional)</span></label>' +
        '<textarea id="' + p + 'det" maxlength="1500" placeholder="Themes / designs available, materials used, extra add-ons and their price…"></textarea></div>' +
      '<div class="fld"><label>Photos of earlier events <span class="opt">(up to ' + MAX_STALL_PHOTOS + ')</span></label>' +
        '<label class="upload-box cv-ph-box" for="' + p + 'ph" style="margin-top:0"><input type="file" id="' + p + 'ph" multiple accept="image/jpeg,image/png,image/webp">' +
        '<div class="ic">📸</div><div class="txt" id="' + p + 'phtxt">Tap to add photos</div></label>' +
        '<ul class="cv-files" id="' + p + 'phlist"></ul></div>' +
    '</div>';
  }

  // Values typed so far, kept while cards are re-drawn (add / remove).
  function readStall(s) {
    var p = 'cs' + s.id + '_', g = function (k) { var el = $(p + k); return el ? el.value.trim() : ''; };
    var t = host.querySelector('input[name="' + p + 'take"]:checked');
    return { pick: g('pick'), other: g('other'), price: g('price'), unit: g('unit'), dur: g('dur'), extra: g('extra'),
      staff: g('staff'), cap: g('cap'), take: t ? t.value : '', takewhat: g('takewhat'), space: g('space'), det: g('det') };
  }
  function writeStall(s, v) {
    var p = 'cs' + s.id + '_';
    ['pick', 'other', 'price', 'unit', 'dur', 'extra', 'staff', 'cap', 'takewhat', 'space', 'det'].forEach(function (k) {
      if (v[k] != null && v[k] !== '' && $(p + k)) $(p + k).value = v[k];
    });
    if (v.take) { var r = host.querySelector('input[name="' + p + 'take"][value="' + v.take + '"]'); if (r) r.checked = true; }
    syncStall(s);
  }
  function syncStall(s) {
    var p = 'cs' + s.id + '_';
    $(p + 'other_box').hidden = $(p + 'pick').value !== '__other';
    var t = host.querySelector('input[name="' + p + 'take"]:checked');
    $(p + 'takewhat_box').hidden = !(t && t.value === 'yes');
    $(p + 'phlist').innerHTML = s.photos.map(function (f, i) {
      return '<li><span>' + esc(f.name) + '</span><span>' + size(f.size) + ' <button type="button" data-rm-ph="' + s.id + ':' + i + '" aria-label="Remove">✕</button></span></li>';
    }).join('');
    $(p + 'phtxt').textContent = s.onFile
      ? 'We already have ' + s.onFile + ' photo' + (s.onFile > 1 ? 's' : '') + ' of this stall. Tap to add more'
      : (s.photos.length ? 'Tap to add more photos' : 'Tap to add photos');
  }
  function draw() {
    var keep = stalls.map(readStallSafe);
    stallsEl.innerHTML = stalls.map(function (s, i) { return stallHtml(s, i + 1); }).join('');
    stalls.forEach(function (s, i) { writeStall(s, keep[i] || {}); });
  }
  function readStallSafe(s) { return $('cs' + s.id + '_pick') ? readStall(s) : (s.init || {}); }
  function addStall(init) { stalls.push({ id: nextId++, photos: [], onFile: 0, init: init || {} }); draw(); }
  function byId(id) { return stalls.filter(function (s) { return s.id === +id; })[0]; }

  $('cv_add_stall').addEventListener('click', function () {
    addStall();
    var last = stalls[stalls.length - 1];
    $('cs' + last.id + '_pick').focus();
  });
  stallsEl.addEventListener('change', function (e) {
    var card = e.target.closest('.cv-stall'); if (!card) return;
    var s = byId(card.getAttribute('data-id'));
    if (e.target.type === 'file') {
      var chosen = Array.prototype.slice.call(e.target.files).filter(function (f) { return /^image\/(jpeg|png|webp)$/.test(f.type); });
      e.target.value = '';
      var room = MAX_STALL_PHOTOS - s.photos.length;
      if (chosen.length > room && window.showErr) window.showErr('You can add up to ' + MAX_STALL_PHOTOS + ' photos for each stall.');
      Promise.all(chosen.slice(0, Math.max(0, room)).map(shrink)).then(function (small) {
        s.photos = s.photos.concat(small); syncStall(s);
      });
      return;
    }
    syncStall(s);
  });
  stallsEl.addEventListener('click', function (e) {
    var rm = e.target.closest('[data-rm-stall]');
    if (rm) {
      var keep = stalls.map(readStall);
      var idx = stalls.indexOf(byId(rm.getAttribute('data-rm-stall')));
      stalls.splice(idx, 1); keep.splice(idx, 1);
      stalls.forEach(function (s, i) { s.init = keep[i]; });
      stallsEl.innerHTML = ''; draw();
      return;
    }
    var ph = e.target.closest('[data-rm-ph]');
    if (ph) {
      var parts = ph.getAttribute('data-rm-ph').split(':'), s = byId(parts[0]);
      s.photos.splice(+parts[1], 1); syncStall(s);
    }
  });
  stallsEl.addEventListener('input', function (e) {
    if (/_(price|extra|staff)$/.test(e.target.id || '')) {
      var d = e.target.value.replace(/\D/g, '');
      if (d !== e.target.value) e.target.value = d;
    }
  });

  // Phone photos are often 3-8 MB; shrink to 1600px JPEG before upload.
  function shrink(file) {
    return new Promise(function (resolve) {
      if (!window.createImageBitmap || !document.createElement('canvas').toBlob) return resolve(file);
      createImageBitmap(file).then(function (bmp) {
        var k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
        var c = document.createElement('canvas');
        c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
        c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
        c.toBlob(function (blob) {
          if (!blob) return resolve(file);
          var name = (file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg';
          try { resolve(new File([blob], name, { type: 'image/jpeg' })); } catch (err) { resolve(file); }
        }, 'image/jpeg', 0.85);
      }).catch(function () { resolve(file); });
    });
  }

  var listEl = $('cv_list');
  function drawFiles() {
    listEl.innerHTML = files.map(function (f, i) {
      return '<li><span>' + esc(f.name) + '</span><span>' + size(f.size) + ' <button type="button" data-rm="' + i + '" aria-label="Remove">✕</button></span></li>';
    }).join('');
  }
  listEl.addEventListener('click', function (e) {
    var b = e.target.closest('[data-rm]'); if (!b) return;
    files.splice(+b.getAttribute('data-rm'), 1); drawFiles();
  });
  $('cv_files').addEventListener('change', function () {
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

  function stallName(v) { return v.pick === '__other' ? v.other.replace(/\s+/g, ' ').trim() : v.pick; }

  addStall();

  window.WSCarnival = {
    toggle: function (on) { host.hidden = !on; },
    validate: function () {
      if (!stalls.length) return { error: 'Please add at least one stall or activity.', el: $('cv_add_stall') };
      var seen = {};
      for (var i = 0; i < stalls.length; i++) {
        var s = stalls[i], v = readStall(s), p = 'cs' + s.id + '_', n = 'stall ' + (i + 1);
        var bad = function (msg, k) { return { error: msg, el: $(p + k) }; };
        if (!v.pick) return bad('Please pick the stall / activity for ' + n + '.', 'pick');
        if (v.pick === '__other' && !v.other) return bad('Please type the name of ' + n + '.', 'other');
        var nm = stallName(v).toLowerCase();
        if (seen[nm]) return bad('You have added ' + stallName(v) + ' twice — please remove one.', 'pick');
        seen[nm] = 1;
        if (!+v.price) return bad('Please give the price for ' + stallName(v) + '.', 'price');
        if (!v.dur) return bad('Please choose the time included for ' + stallName(v) + '.', 'dur');
        if (v.staff === '') return bad('Please say how many staff come with ' + stallName(v) + ' (0 if none).', 'staff');
        if (!v.take) return { error: 'Please say if kids take something home from ' + stallName(v) + '.', el: host.querySelector('input[name="' + p + 'take"]') };
        if (v.take === 'yes' && !v.takewhat) return bad('Please say what kids take home from ' + stallName(v) + '.', 'takewhat');
      }
      if (!$('cv_headsup').value) return { error: 'Please choose the heads-up time you need.', el: $('cv_headsup') };
      if (!document.querySelectorAll('#cv_zones input:checked').length) return { error: 'Please pick the areas of Mumbai you cover.', el: $('cv_zones') };
      var total = files.concat.apply(files, stalls.map(function (s) { return s.photos; })).reduce(function (t, f) { return t + f.size; }, 0);
      if (total > MAX_TOTAL) return { error: 'Your files add up to more than 50 MB — please remove a few.', el: listEl };
      return {};
    },
    appendTo: function (fd) {
      var services = stalls.map(function (s, i) {
        var v = readStall(s), name = stallName(v);
        return { name: name, category: CAT_OF[name] || 'Other', price: +v.price || null, price_unit: v.unit || 'stall',
          duration: v.dur, extra_hour: +v.extra || null, staff: v.staff === '' ? null : +v.staff, capacity: v.cap,
          takeaway: v.take, takeaway_what: v.take === 'yes' ? v.takewhat : '', space_power: v.space, details: v.det,
          photo_key: 's' + (i + 1) };
      });
      var profile = {
        services: services,
        headsup: $('cv_headsup').value,
        setup_time: $('cv_setup').value,
        min_order: $('cv_min').value.trim(),
        instagram: $('cv_ig').value.trim(),
        zones: Array.prototype.map.call(document.querySelectorAll('#cv_zones input:checked'), function (i) { return +i.value; }),
        travel_charge: $('cv_travel').value.trim()
      };
      fd.append('carnival_profile', JSON.stringify(profile));
      files.forEach(function (f) { fd.append('catalogues', f, f.name); });
      stalls.forEach(function (s, i) {
        s.photos.forEach(function (f) { fd.append('stall_photos', f, 's' + (i + 1) + '__' + f.name); });
      });
    },
    fill: function (p, photoCounts) {
      if (!p) return;
      var list = (p.services || []).filter(function (s) { return s && s.name; });
      if (list.length) {
        stalls = []; nextId = 1;
        list.forEach(function (s) {
          var known = !!CAT_OF[s.name];
          stalls.push({ id: nextId++, photos: [], onFile: (photoCounts || {})[s.name.toLowerCase()] || 0, init: {
            pick: known ? s.name : '__other', other: known ? '' : s.name, price: s.price || '', unit: s.price_unit || 'stall',
            dur: s.duration || '', extra: s.extra_hour || '', staff: s.staff == null ? '' : String(s.staff), cap: s.capacity || '',
            take: s.takeaway || '', takewhat: s.takeaway_what || '', space: s.space_power || '', det: s.details || '' } });
        });
        stallsEl.innerHTML = ''; draw();
      }
      var set = function (id, v) { var el = $(id); if (el && v) el.value = v; };
      set('cv_headsup', p.headsup); set('cv_setup', p.setup_time);
      set('cv_min', p.min_order); set('cv_ig', p.instagram); set('cv_travel', p.travel_charge);
      (p.zones || []).forEach(function (n) { var el = document.querySelector('#cv_zones input[value="' + n + '"]'); if (el) el.checked = true; });
    }
  };
})();
