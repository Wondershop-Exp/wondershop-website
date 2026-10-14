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
    'Treasure hunts', 'Science show', 'Science activities', 'Magic', 'Storytelling', 'Dance & music games',
    'Tambola / Housie', 'Team-building games'];
  var LANGS = ['English', 'Hindi', 'Marathi', 'Gujarati', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Bengali', 'Punjabi'];
  var EVENT_TYPES = ['Birthday parties', 'Weddings', 'Engagements', 'Baby showers', 'School events', 'Corporate events',
    'Society / community events', 'Stage shows', 'Festivals'];
  var AGES = ['Toddlers (2-4)', '5-8 years', '9-12 years', 'Teens (13+)', 'Adults'];
  var hasHeadshot = false;   // already on file (update link)
  var headshot = null;       // shrunk File
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

  function chipGroup(name, list) {
    return '<div class="vl-chips">' + list.map(function (s) {
      return '<label class="vl-chip"><input type="checkbox" name="' + name + '" value="' + esc(s) + '"><span><b>' + esc(s) + '</b></span></label>';
    }).join('') + '</div>';
  }

  host.innerHTML =
    '<div class="sec-h">About you as a host</div>' +
    '<div class="sec-sub">Help us match you to the right parties and events. We also use these answers to build your host page on our website.</div>' +
    fld('Your headshot *', '<label class="upload-box" for="h_headshot" id="h_headshot_box" style="margin-top:0"><input type="file" id="h_headshot" accept="image/jpeg,image/png,image/webp">' +
      '<div class="ic">🙂</div><div class="txt" id="h_headshot_txt">Tap to add a clear photo of your face</div></label>', 'h_headshot_fld',
      'A recent, well-lit photo of just you, smiling. This is the main photo on your host page.') +
    '<div class="row2">' +
      fld('Name to show on your page <span class="opt">(optional)</span>', '<input type="text" id="h_display" maxlength="60" placeholder="e.g. Sunny">') +
      fld('Home town <span class="opt">(optional)</span>', '<input type="text" id="h_hometown" maxlength="60" placeholder="e.g. Mumbai">') +
    '</div>' +
    fld('Languages you speak *', chipGroup('h_lang', LANGS) +
      '<input type="text" id="h_lang_other" class="vl-other" maxlength="100" placeholder="Others (type here)">', 'h_lang_fld', 'Pick all that apply.') +
    fld('About you (2-3 lines) *', '<textarea id="h_about" maxlength="600" placeholder="e.g. A high-energy host from Mumbai who has hosted 500+ kids\u2019 parties..."></textarea>') +
    fld('Your story <span class="opt">(optional)</span>', '<textarea id="h_story" maxlength="2000" placeholder="How you got into hosting, what you have learnt, what a party with you feels like..."></textarea>', '', 'A short paragraph in your own words.') +
    fld('What do you love most about hosting? <span class="opt">(optional)</span>', '<input type="text" id="h_love" maxlength="200" placeholder="e.g. Seeing the whole room laugh together">') +
    '<div class="row2">' +
      fld('Your signature move or game <span class="opt">(optional)</span>', '<input type="text" id="h_signature" maxlength="120" placeholder="e.g. Instant ice-breakers">') +
      fld('Your catchphrase or tagline <span class="opt">(optional)</span>', '<input type="text" id="h_catch" maxlength="100" placeholder="e.g. Energy on. Smiles guaranteed!">') +
    '</div>' +
    fld('Years of hosting experience *', '<input type="text" id="h_years" inputmode="numeric" maxlength="2" placeholder="e.g. 3">') +
    fld('Your strengths *', '<div class="vl-chips" id="h_strengths">' + STRENGTHS.map(function (s) {
      return '<label class="vl-chip"><input type="checkbox" name="h_strength" value="' + esc(s) + '"><span><b>' + esc(s) + '</b></span></label>';
    }).join('') + '</div><input type="text" id="h_strengths_other" class="vl-other" maxlength="200" placeholder="Others (type here)">',
      'h_strengths_fld', 'Pick all that apply.') +
    fld('Types of events you have hosted <span class="opt">(optional)</span>', chipGroup('h_evt', EVENT_TYPES) +
      '<input type="text" id="h_evt_other" class="vl-other" maxlength="200" placeholder="Others (type here)">') +
    fld('Age groups you are best with <span class="opt">(optional)</span>', chipGroup('h_age', AGES)) +
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

    fld('Reviews from clients <span class="opt">(optional)</span>', '<textarea id="h_reviews" maxlength="2000" placeholder="Paste a couple of messages or reviews from parents / clients, with their name"></textarea>') +
    fld('Link to your Google or other reviews <span class="opt">(optional)</span>', '<input type="text" id="h_review_link" maxlength="500" placeholder="https://...">') +

    '<div class="vl-sub">Growing with us</div>' +
    fld('How can Wondershop Experiences help you grow as a host? <span class="opt">(optional)</span>', '<textarea id="h_grow" maxlength="1500"></textarea>') +
    '<label class="vl-accept" id="h_consent_lbl"><input type="checkbox" id="h_consent"><span>I allow Wondershop Experiences to use my name, photos, videos and the details above on its website and social media, including a host page about me. *</span></label>';

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

  var hsBox = $('h_headshot_box'), hsTxt = $('h_headshot_txt');
  function drawHeadshot() {
    hsBox.style.borderColor = headshot ? 'var(--gr)' : '';
    hsTxt.textContent = headshot ? '\u2713 ' + headshot.name + ' (tap to change)'
      : (hasHeadshot ? 'We already have your headshot. Tap to replace it' : 'Tap to add a clear photo of your face');
  }
  $('h_headshot').addEventListener('change', function () {
    var f = this.files[0]; this.value = '';
    if (!f) return;
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) { if (window.showErr) window.showErr('Your headshot must be a JPG or PNG photo.'); return; }
    shrink(f).then(function (small) { headshot = small; drawHeadshot(); });
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
      grow: val('h_grow'),
      display_name: val('h_display'),
      home_town: val('h_hometown'),
      languages: picked('h_lang'),
      languages_other: val('h_lang_other'),
      about: val('h_about'),
      story: val('h_story'),
      love: val('h_love'),
      signature: val('h_signature'),
      catchphrase: val('h_catch'),
      event_types: picked('h_evt'),
      event_types_other: val('h_evt_other'),
      age_groups: picked('h_age'),
      reviews: val('h_reviews'),
      review_link: val('h_review_link'),
      consent: $('h_consent').checked
    };
  }

  window.WSHost = {
    toggle: function (on) { host.hidden = !on; },
    validate: function () {
      var p = collect();
      function bad(msg, el) { return { error: msg, el: el }; }
      if (!headshot && !hasHeadshot) return bad('Please add a clear photo of your face (headshot).', $('h_headshot_fld'));
      if (!p.languages.length && !p.languages_other) return bad('Please pick the languages you speak.', $('h_lang_fld'));
      if (p.about.length < 20) return bad('Please write 2-3 lines about yourself.', $('h_about'));
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
      if (p.review_link && !/^https?:\/\/[^\s.]+\.[^\s]+$/i.test(p.review_link)) return bad('Please check your reviews link \u2014 it should start with https://', $('h_review_link'));
      if (!p.consent) return bad('Please allow us to use your details on our website (tick the box at the end).', $('h_consent_lbl'));
      return {};
    },
    appendTo: function (fd) {
      fd.append('host_profile', JSON.stringify(collect()));
      if (headshot) fd.append('host_headshot', headshot, headshot.name);
      photos.forEach(function (f) { fd.append('host_photos', f, f.name); });
    },
    fill: function (p, photoCount) {
      onFile = photoCount || 0; drawPhotos();
      hasHeadshot = !!(p && p.has_headshot); drawHeadshot();
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
      setVal('h_display', p.display_name); setVal('h_hometown', p.home_town);
      check('h_lang', p.languages); setVal('h_lang_other', p.languages_other);
      setVal('h_about', p.about); setVal('h_story', p.story); setVal('h_love', p.love);
      setVal('h_signature', p.signature); setVal('h_catch', p.catchphrase);
      check('h_evt', p.event_types); setVal('h_evt_other', p.event_types_other);
      check('h_age', p.age_groups);
      setVal('h_reviews', p.reviews); setVal('h_review_link', p.review_link);
    }
  };
})();
