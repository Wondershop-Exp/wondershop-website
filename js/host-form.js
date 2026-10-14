// "Host" section of the partner onboarding form (2026-10-14, per Shruti).
// Shown when "Host" is picked. Exposes window.WSHost:
//   toggle(on)      show / hide the section
//   validate()      -> {error, el} for the first problem, or {} when complete
//   appendTo(fd)    adds host_profile (JSON) and the photos
//   fill(p, n)      pre-fills from an update link (n = photos already on file)
// Address and pincode are mandatory for hosts (see vendor-onboarding.html).
// Zones come from js/volunteer-data.js (same 6 Mumbai zones everywhere).
(function () {
  var host = document.getElementById('hostSection');
  if (!host) return;
  var ZONES = (window.WS_VOLUNTEER && window.WS_VOLUNTEER.zones) || [];
  var STRENGTHS = ['Spy / mystery parties', 'Turf & sports games', 'Art & craft activities', 'Party games',
    'Treasure hunts', 'Science activities', 'Magic', 'Storytelling', 'Dance & music games',
    'Tambola / Housie', 'Team-building games'];
  var YES3 = [{ v: 'yes', l: 'Yes' }, { v: 'maybe', l: 'Maybe' }, { v: 'no', l: 'No' }];
  var MAX_PHOTOS = 6, MAX_VIDEOS = 5;
  var photos = [];         // shrunk File objects
  var onFile = 0;          // photos we already have (update link)

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function radios(name, list) {
    return '<div class="vl-radios">' + list.map(function (o) {
      return '<label class="vl-radio"><input type="radio" name="' + name + '" value="' + esc(o.v) + '"><span>' + esc(o.l) + '</span></label>';
    }).join('') + '</div>';
  }
  function scale(name) {
    return '<div class="vl-scale" id="' + name + '_box">' + [1, 2, 3, 4, 5].map(function (n) {
      return '<label><input type="radio" name="' + name + '" value="' + n + '"><span>' + n + '</span></label>';
    }).join('') + '</div><div class="vl-scale-ends"><span>1 = not comfortable</span><span>5 = very comfortable</span></div>';
  }
  function fld(label, inner, id, hint) {
    return '<div class="fld"' + (id ? ' id="' + id + '"' : '') + '><label>' + label + '</label>' + inner +
      (hint ? '<div class="f-hint">' + hint + '</div>' : '') + '</div>';
  }

  host.innerHTML =
    '<div class="sec-h">About you as a host</div>' +
    '<div class="sec-sub">Help us match you to the right parties and events.</div>' +
    fld('Years of hosting experience *', '<input type="text" id="h_years" inputmode="numeric" maxlength="2" placeholder="e.g. 3">') +
    fld('Your strengths *', '<div class="vl-chips" id="h_strengths">' + STRENGTHS.map(function (s) {
      return '<label class="vl-chip"><input type="checkbox" name="h_strength" value="' + esc(s) + '"><span><b>' + esc(s) + '</b></span></label>';
    }).join('') + '</div><input type="text" id="h_strengths_other" class="vl-other" maxlength="200" placeholder="Others (type here)">',
      'h_strengths_fld', 'Pick all that apply.') +
    fld('What makes you different from other hosts? *', '<textarea id="h_unique" maxlength="1500" placeholder="Your style, signature games, how you keep kids engaged..."></textarea>') +

    '<div class="vl-sub">Comfort level</div>' +
    fld('How comfortable are you with kids? *', scale('h_kids')) +
    fld('How comfortable are you hosting large kids’ events (50+ kids)? *', scale('h_large_kids')) +
    fld('Are you open to hosting adult events, like corporate events or functions? *', radios('h_adult', YES3)) +
    '<div id="h_corp_box" hidden>' + fld('How comfortable are you hosting large corporate events? *', scale('h_corp')) + '</div>' +

    '<div class="vl-sub">Training &amp; props</div>' +
    fld('Are you open to being trained on new themes and games? *', radios('h_training', YES3)) +
    fld('Do you have your own game props? *', radios('h_props', [{ v: 'yes', l: 'Yes' }, { v: 'no', l: 'No' }])) +
    '<div id="h_props_box" hidden>' + fld('Which props do you have? *', '<textarea id="h_props_list" maxlength="1000" placeholder="e.g. hoops, cones, parachute, music system, mic"></textarea>') + '</div>' +

    '<div class="vl-sub">Zones</div>' +
    fld('Which zones are you comfortable working in? *', '<div class="vl-zones" id="h_zones">' + ZONES.map(function (z) {
      return '<label class="vl-zone"><input type="checkbox" name="h_zone" value="' + z.n + '">' +
        '<span><b>Zone ' + z.n + ' · ' + esc(z.en) + '</b><small>' + esc(z.areas) + '</small></span></label>';
    }).join('') + '</div>', 'h_zones_fld', 'Pick all that apply.') +

    '<div class="vl-sub">Your work</div>' +
    fld('Instagram handle <span class="opt">(optional)</span>', '<input type="text" id="h_ig" maxlength="100" placeholder="e.g. @yourname">') +
    fld('Photos of your events <span class="opt">(up to ' + MAX_PHOTOS + ')</span>',
      '<label class="upload-box" for="h_photos" style="margin-top:0"><input type="file" id="h_photos" multiple accept="image/jpeg,image/png,image/webp">' +
      '<div class="ic">📸</div><div class="txt" id="h_photos_txt">Tap to add photos</div></label>' +
      '<ul class="cv-files" id="h_photo_list"></ul>') +
    fld('Links to your videos <span class="opt">(Instagram, YouTube or Google Drive, one per line)</span>',
      '<textarea id="h_videos" maxlength="2000" placeholder="https://www.instagram.com/reel/...\nhttps://drive.google.com/..."></textarea>', 'h_videos_fld',
      'Video files are too big to upload here, so please share links. For Google Drive, set the link to “anyone with the link can view”.') +

    '<div class="vl-sub">Growing with us</div>' +
    fld('How can Wondershop Experiences help you grow as a host? <span class="opt">(optional)</span>', '<textarea id="h_grow" maxlength="1500"></textarea>');

  function $(id) { return document.getElementById(id); }
  function radio(name) { var r = host.querySelector('input[name="' + name + '"]:checked'); return r ? r.value : ''; }
  function picked(name) {
    return Array.prototype.map.call(host.querySelectorAll('input[name="' + name + '"]:checked'), function (i) { return i.value; });
  }
  function val(id) { return ($(id).value || '').trim(); }
  function videoLinks() {
    return val('h_videos').split(/[\s,]+/).filter(Boolean);
  }

  host.addEventListener('change', function (e) {
    if (e.target.name === 'h_adult') $('h_corp_box').hidden = radio('h_adult') === 'no' || !radio('h_adult');
    if (e.target.name === 'h_props') $('h_props_box').hidden = radio('h_props') !== 'yes';
  });
  $('h_years').addEventListener('input', function () { var d = this.value.replace(/\D/g, '').slice(0, 2); if (d !== this.value) this.value = d; });

  // Phone photos are often 3-8 MB; shrink to 1600px JPEG before upload.
  function shrink(file) {
    return new Promise(function (resolve) {
      if (!window.createImageBitmap || !document.createElement('canvas').toBlob) return resolve(file);
      createImageBitmap(file).then(function (bmp) {
        var s = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
        var c = document.createElement('canvas');
        c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
        c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
        c.toBlob(function (blob) {
          if (!blob) return resolve(file);
          var name = (file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg';
          try { resolve(new File([blob], name, { type: 'image/jpeg' })); } catch (err) { resolve(file); }
        }, 'image/jpeg', 0.85);
      }).catch(function () { resolve(file); });
    });
  }
  var listEl = $('h_photo_list');
  function drawPhotos() {
    listEl.innerHTML = photos.map(function (f, i) {
      return '<li><span>' + esc(f.name) + '</span><span>' + Math.max(1, Math.round(f.size / 1024)) + ' KB <button type="button" data-rm="' + i + '" aria-label="Remove">✕</button></span></li>';
    }).join('');
    $('h_photos_txt').textContent = onFile
      ? 'We already have ' + onFile + ' photo' + (onFile > 1 ? 's' : '') + ' from you. Tap to add more'
      : (photos.length ? 'Tap to add more photos' : 'Tap to add photos');
  }
  listEl.addEventListener('click', function (e) {
    var b = e.target.closest('[data-rm]'); if (!b) return;
    photos.splice(+b.getAttribute('data-rm'), 1); drawPhotos();
  });
  $('h_photos').addEventListener('change', function () {
    var input = this, chosen = Array.prototype.slice.call(input.files), bad = '';
    input.value = '';
    chosen = chosen.filter(function (f) {
      if (!/^image\/(jpeg|png|webp)$/.test(f.type)) { bad = f.name + ' is not a JPG or PNG photo.'; return false; }
      return true;
    });
    var room = MAX_PHOTOS - photos.length;
    if (chosen.length > room) { bad = 'You can add up to ' + MAX_PHOTOS + ' photos.'; chosen = chosen.slice(0, Math.max(0, room)); }
    Promise.all(chosen.map(shrink)).then(function (small) {
      photos = photos.concat(small); drawPhotos();
      if (bad && window.showErr) window.showErr(bad);
    });
  });

  function collect() {
    var adult = radio('h_adult');
    return {
      years: val('h_years') === '' ? null : +val('h_years'),
      strengths: picked('h_strength'),
      strengths_other: val('h_strengths_other'),
      unique: val('h_unique'),
      comfort_kids: +radio('h_kids') || null,
      comfort_large_kids: +radio('h_large_kids') || null,
      adult_events: adult,
      comfort_corporate: adult && adult !== 'no' ? (+radio('h_corp') || null) : null,
      open_to_training: radio('h_training'),
      has_props: radio('h_props'),
      props: radio('h_props') === 'yes' ? val('h_props_list') : '',
      zones: picked('h_zone').map(Number),
      instagram: val('h_ig'),
      videos: videoLinks(),
      grow: val('h_grow')
    };
  }

  window.WSHost = {
    toggle: function (on) { host.hidden = !on; },
    validate: function () {
      var p = collect();
      function bad(msg, el) { return { error: msg, el: el }; }
      if (p.years === null || p.years > 50) return bad('Please enter your years of hosting experience.', $('h_years'));
      if (!p.strengths.length && !p.strengths_other) return bad('Please pick at least one of your strengths.', $('h_strengths_fld'));
      if (p.unique.length < 10) return bad('Please tell us what makes you different from other hosts.', $('h_unique'));
      if (!p.comfort_kids) return bad('Please rate how comfortable you are with kids (1 to 5).', $('h_kids_box'));
      if (!p.comfort_large_kids) return bad('Please rate how comfortable you are hosting large kids’ events (1 to 5).', $('h_large_kids_box'));
      if (!p.adult_events) return bad('Please tell us if you are open to hosting adult events.', host.querySelector('input[name="h_adult"]'));
      if (p.adult_events !== 'no' && !p.comfort_corporate) return bad('Please rate how comfortable you are hosting large corporate events (1 to 5).', $('h_corp_box'));
      if (!p.open_to_training) return bad('Please tell us if you are open to training on new themes and games.', host.querySelector('input[name="h_training"]'));
      if (!p.has_props) return bad('Please tell us if you have your own game props.', host.querySelector('input[name="h_props"]'));
      if (p.has_props === 'yes' && !p.props) return bad('Please list the props you have.', $('h_props_list'));
      if (!p.zones.length) return bad('Please pick at least one zone you are comfortable working in.', $('h_zones_fld'));
      if (p.videos.length > MAX_VIDEOS) return bad('Please share up to ' + MAX_VIDEOS + ' video links.', $('h_videos'));
      for (var i = 0; i < p.videos.length; i++) {
        if (!/^https?:\/\/[^\s.]+\.[^\s]+$/i.test(p.videos[i])) return bad('Please check your video links — each one should start with https://', $('h_videos'));
      }
      return {};
    },
    appendTo: function (fd) {
      fd.append('host_profile', JSON.stringify(collect()));
      photos.forEach(function (f) { fd.append('host_photos', f, f.name); });
    },
    fill: function (p, photoCount) {
      onFile = photoCount || 0; drawPhotos();
      if (!p) return;
      function setVal(id, v) { if (v != null && v !== '') $(id).value = v; }
      function check(name, values) {
        (values || []).forEach(function (v) {
          var el = host.querySelector('input[name="' + name + '"][value="' + String(v).replace(/"/g, '\\"') + '"]');
          if (el) el.checked = true;
        });
      }
      setVal('h_years', p.years);
      check('h_strength', p.strengths); setVal('h_strengths_other', p.strengths_other);
      setVal('h_unique', p.unique);
      check('h_kids', p.comfort_kids ? [p.comfort_kids] : []);
      check('h_large_kids', p.comfort_large_kids ? [p.comfort_large_kids] : []);
      check('h_adult', p.adult_events ? [p.adult_events] : []);
      $('h_corp_box').hidden = !p.adult_events || p.adult_events === 'no';
      check('h_corp', p.comfort_corporate ? [p.comfort_corporate] : []);
      check('h_training', p.open_to_training ? [p.open_to_training] : []);
      check('h_props', p.has_props ? [p.has_props] : []);
      $('h_props_box').hidden = p.has_props !== 'yes';
      setVal('h_props_list', p.props);
      check('h_zone', p.zones);
      setVal('h_ig', p.instagram);
      setVal('h_videos', (p.videos || []).join('\n'));
      setVal('h_grow', p.grow);
    }
  };
})();
