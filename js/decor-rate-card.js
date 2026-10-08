// Decorator rate card for vendor-onboarding.html (2026-10-08, per Shruti).
// When "What do you deal in?" is Decorator, this adds a Decor Rate Card
// section: rates for the 4 standard decors (with a gallery of every website
// design - same rate / other rate / can't do), transport per Mumbai zone,
// flex pickup, booking notice and photos of past work. English is always
// shown; the decorator can add a Hindi or Marathi line under each question.
// The answers go to the backend as one JSON field (decor_rate_card) plus the
// photos (work_photos) - see backend/routers/vendor_onboarding.py.
(function () {
  'use strict';
  var D = window.WS_DECOR_DATA;
  var G = window.WS_DECOR_DESIGNS || { designs: {}, reference: {} };
  if (!D) return;

  var MAX_PHOTOS = 5;
  var state = {
    lang: 'hi',
    about: { years: '', team: '', perday: '' },
    tiers: {},
    zones: {},
    flex: '',
    notice: '',
    photos: []
  };
  D.tiers.forEach(function (t) {
    state.tiers[t.key] = { does: true, rate: '', modes: {}, other: {} };
  });
  D.zones.forEach(function (z) { state.zones[z.n] = { serves: true, rate: '', open: false }; });

  // ── helpers ────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function tr(key) { return '<span class="dc-tr" data-k="' + key + '"></span>'; }
  function trText(hi, mr) {
    return '<span class="dc-tr" data-hi="' + esc(hi) + '" data-mr="' + esc(mr) + '"></span>';
  }
  function digits(v) { return String(v || '').replace(/\D/g, '').slice(0, 7); }
  function money(n) {
    var s = String(n || '');
    return s ? '₹' + Number(s).toLocaleString('en-IN') : '—';
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  var ICONS = {
    arch: '<path d="M6 34V20a14 14 0 0 1 28 0v14"/><circle cx="6" cy="22" r="3"/><circle cx="9" cy="12" r="3"/><circle cx="16" cy="7" r="3"/><circle cx="24" cy="7" r="3"/><circle cx="31" cy="12" r="3"/><circle cx="34" cy="22" r="3"/>',
    balloon: '<ellipse cx="20" cy="15" rx="9" ry="11"/><path d="M20 26l-2 3h4l-2-3M20 29c0 4-3 4-3 8"/>',
    bunting: '<path d="M4 10q16 8 32 0"/><path d="M8 12l3 9 4-7M17 14l3 9 3-9M25 14l4 8 2-9"/>',
    foil: '<rect x="9" y="4" width="22" height="32" rx="6"/><path d="M24 11h-7l-1 7c4-2 8 0 8 5s-5 7-9 4"/>',
    panel: '<rect x="6" y="5" width="28" height="22" rx="2"/><path d="M12 27l-3 9M28 27l3 9"/>',
    stand: '<path d="M8 6h24M20 6v24M12 36l8-6 8 6"/>',
    garland: '<path d="M4 30C10 14 30 14 36 30"/><circle cx="8" cy="22" r="3"/><circle cx="14" cy="16" r="3"/><circle cx="20" cy="14" r="3"/><circle cx="26" cy="16" r="3"/><circle cx="32" cy="22" r="3"/>',
    bunch: '<circle cx="14" cy="13" r="6"/><circle cx="26" cy="13" r="6"/><circle cx="20" cy="21" r="6"/><path d="M20 27v9M14 19l6 17M26 19l-6 17"/>'
  };
  function icon(name) {
    return '<svg width="34" height="34" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">' + ICONS[name] + '</svg>';
  }
  var CHECK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';
  var CROSS = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  function chips(name, options, extraClass) {
    return '<div class="dc-chips ' + (extraClass || '') + '" role="group" data-chips="' + name + '">' +
      options.map(function (o) {
        return '<button type="button" class="dc-chip" data-v="' + esc(o) + '" aria-pressed="false">' + esc(o) + '</button>';
      }).join('') + '</div>';
  }
  function moneyInput(id, label, prefix) {
    return '<div class="dc-money"><span>' + (prefix || '₹') + '</span><input type="text" inputmode="numeric" autocomplete="off" id="' + id + '" aria-label="' + esc(label) + '"></div>';
  }

  // ── rendering ──────────────────────────────────────────────────────────
  function renderCallout() {
    return '<div class="dc-callout">' +
      '<p><b>You picked Decorator.</b> We\'ve added a <b>Decor Rate Card</b> section below — about 10 more minutes.' + tr('callout') + '</p>' +
      '<div class="dc-langrow"><span>Also show the questions in</span>' +
      '<div class="dc-lang" role="group">' +
      '<button type="button" data-lang="hi" aria-pressed="true">हिंदी</button>' +
      '<button type="button" data-lang="mr" aria-pressed="false">मराठी</button>' +
      '<button type="button" data-lang="en" aria-pressed="false">English only</button>' +
      '</div></div></div>';
  }

  function renderTier(t, i) {
    var designs = (G.designs && G.designs[t.label]) || [];
    var ref = G.reference && G.reference[t.label];
    var html = '<div class="dc-tier" id="dc-tier-' + t.key + '" data-tier="' + t.key + '">' +
      '<span class="dc-badge">Decor ' + (i + 1) + ' of 4</span>' +
      '<h3 class="dc-h2">' + esc(t.title) + '</h3>' + trText(t.hi, t.mr) +
      '<div class="dc-q"><div><span class="dc-l">Do you do this decor?</span>' + tr('doyou') + '</div>' +
      '<div class="dc-chips dc-yesno" data-yesno="' + t.key + '">' +
      '<button type="button" class="dc-chip" data-v="yes" aria-pressed="true">Yes ' + '<span class="dc-tr dc-inline" data-k="yes"></span></button>' +
      '<button type="button" class="dc-chip" data-v="no" aria-pressed="false">No ' + '<span class="dc-tr dc-inline" data-k="no"></span></button>' +
      '</div></div>' +
      '<div class="dc-skip" hidden>OK — we won\'t send you orders for this decor. Go to the next one.' + tr('skip') + '</div>' +
      '<div class="dc-tier-body">';
    if (ref) html += '<div class="dc-ref dc-protect"><img src="' + esc(ref) + '" alt="' + esc(t.title) + ' reference decor" draggable="false" loading="lazy"></div>';
    html += '<div class="dc-q"><div><span class="dc-l">What\'s included</span>' + tr('included') + '</div><div class="dc-tiles">' +
      t.items.map(function (it) {
        return '<div class="dc-tile' + (it.ours ? ' dc-ours' : '') + '">' + icon(it.icon) +
          '<span class="dc-cnt">' + esc(it.count) + '</span><span class="dc-tl">' + esc(it.en) + '</span>' + trText(it.hi, it.mr) + '</div>';
      }).join('') + '</div></div>' +
      '<div class="dc-q"><label for="dc-rate-' + t.key + '"><span class="dc-l">Your rate (normal balloons) *</span>' + tr('rate') + '</label>' +
      moneyInput('dc-rate-' + t.key, t.label + ' rate') + '</div>';
    if (designs.length) {
      html += '<div class="dc-galbox">' +
        '<div><span class="dc-l">Is <span class="dc-ratetext">this rate</span> your rate for all these ' + esc(t.label) + ' decors?</span>' + tr('gal_q') + '</div>' +
        '<p class="dc-wait">Enter your rate above to see all the designs.' + tr('gal_wait') + '</p>' +
        '<div class="dc-galwrap" hidden>' +
        '<p class="dc-sub">Under each photo pick: <b>Same rate</b>, <b>Other rate</b>, or <b>Can\'t do</b>.' + tr('gal_p') + '</p>' +
        '<span class="dc-count"></span>' +
        '<p class="dc-sub dc-small">Photos are Wondershop property, for quoting only. Please don\'t share.' + tr('gal_note') + '</p>' +
        '<div class="dc-gal">' +
        designs.map(function (d) {
          return '<div class="dc-gi" data-design="' + esc(d.id) + '" data-mode="same">' +
            '<div class="dc-gb dc-protect"><img src="' + esc(d.img) + '" alt="" draggable="false" loading="lazy">' +
            '<span class="dc-ck">' + CHECK + '</span><span class="dc-gn">' + esc(d.name) + '</span></div>' +
            '<div class="dc-seg" role="group" aria-label="' + esc(d.name) + '">' +
            '<button type="button" data-mode="same" aria-pressed="true"><span>Same</span><span>rate</span></button>' +
            '<button type="button" data-mode="other" aria-pressed="false"><span>Other</span><span>rate</span></button>' +
            '<button type="button" data-mode="no" aria-pressed="false"><span>Can\'t</span><span>do</span></button></div>' +
            '<div class="dc-money dc-sm dc-otherrate" hidden><span>₹</span><input type="text" inputmode="numeric" placeholder="Its rate" aria-label="Rate for ' + esc(d.name) + '"></div>' +
            '</div>';
        }).join('') + '</div></div></div>';
    }
    html += '<div class="dc-q"><label for="dc-pastel-' + t.key + '"><span class="dc-l">Extra if pastel balloons</span>' + tr('pastel') + '</label>' + moneyInput('dc-pastel-' + t.key, t.label + ' pastel extra', '+ ₹') + '</div>' +
      '<div class="dc-q"><label for="dc-chrome-' + t.key + '"><span class="dc-l">Extra if chrome balloons</span>' + tr('chrome') + '</label>' + moneyInput('dc-chrome-' + t.key, t.label + ' chrome extra', '+ ₹') + '</div>' +
      '<div class="dc-q"><div><span class="dc-l">Time needed to set up</span>' + tr('setup') + '</div>' + chips('setup-' + t.key, ['1 hr', '2 hrs', '3+ hrs']) + '</div>' +
      '<div class="dc-q"><label for="dc-rem-' + t.key + '"><span class="dc-l">Remarks <span class="dc-opt">(optional)</span></span>' + tr('remarks') + '</label>' +
      '<textarea id="dc-rem-' + t.key + '" class="dc-rem" maxlength="1000"></textarea>' +
      (i === 0 ? '<span class="dc-mic"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>Tap the mic on your keyboard to speak instead of typing' + tr('mic') + '</span>' : '') +
      '</div></div></div>';
    return html;
  }

  function renderMap() {
    return '<div class="dc-mapbox"><div><span class="dc-l dc-h3">Where are the zones?</span>' + tr('map_h') + '</div>' +
      '<svg viewBox="0 0 340 440" width="100%" role="img" aria-label="Sketch map of Mumbai showing the 6 transport zones" class="dc-map">' +
      '<rect width="340" height="440" fill="#E4EEF1" rx="12"/>' +
      '<text x="30" y="330" transform="rotate(-90 30 330)" style="font:500 12px Hind,sans-serif;fill:#5E7C86;letter-spacing:2px">ARABIAN SEA</text>' +
      '<a href="#dc-zone-6"><polygon points="80,70 76,20 132,14 134,68" fill="#E5E0DA" stroke="#6B6158" stroke-width="1.5"/><polygon points="226,140 216,100 262,80 322,84 322,142 272,152" fill="#E5E0DA" stroke="#6B6158" stroke-width="1.5"/><polygon points="262,292 302,290 318,346 272,358 246,338" fill="#E5E0DA" stroke="#6B6158" stroke-width="1.5"/></a>' +
      '<a href="#dc-zone-5"><polygon points="92,176 88,140 84,106 80,70 134,68 142,106 150,150 136,176" fill="#F6E5B3" stroke="#A16207" stroke-width="1.5"/></a>' +
      '<a href="#dc-zone-4"><polygon points="190,140 150,150 142,106 178,96 216,100 226,140" fill="#D3E1FB" stroke="#2563EB" stroke-width="1.5"/><polygon points="218,188 246,182 256,232 262,292 242,332 222,322 224,262" fill="#D3E1FB" stroke="#2563EB" stroke-width="1.5"/></a>' +
      '<a href="#dc-zone-2"><polygon points="112,290 104,250 96,212 92,176 136,176 141,212 146,250 150,288" fill="#FBD6C2" stroke="#C2410C" stroke-width="1.5"/></a>' +
      '<a href="#dc-zone-1"><polygon points="150,288 146,250 141,212 136,176 150,150 190,140 206,176 202,216 192,262 176,302 152,322" fill="#CDEBE7" stroke="#0F766E" stroke-width="1.5"/></a>' +
      '<a href="#dc-zone-3"><polygon points="72,436 86,400 100,360 112,322 112,290 150,288 152,322 130,352 106,396 84,438" fill="#E3D7FB" stroke="#6D28D9" stroke-width="1.5"/></a>' +
      '<polyline points="80,428 100,372 118,300 112,250 104,200 98,150 92,100 100,40" fill="none" stroke="#1E1B2E" stroke-width="2" stroke-dasharray="6 4"/>' +
      '<polyline points="84,432 112,360 140,300 160,250 176,200 190,150 214,118 262,112" fill="none" stroke="#1E1B2E" stroke-width="2"/>' +
      '<g style="font:600 11px Hind,sans-serif;fill:#1E1B2E"><text x="86" y="420">Colaba</text><text x="122" y="314">Dadar</text><text x="66" y="276">Bandra</text><text x="54" y="210">Andheri</text><text x="156" y="272">Ghatkopar</text><text x="156" y="168">Mulund</text><text x="44" y="122">Borivali</text><text x="168" y="92">Thane</text><text x="226" y="210">Vashi</text><text x="88" y="32">Virar</text><text x="272" y="100">Kalyan</text><text x="268" y="312">Panvel</text></g>' +
      '<g style="font:700 14px \'Baloo 2\',sans-serif" text-anchor="middle">' +
      [[172, 232, 1, '#0F766E'], [120, 232, 2, '#C2410C'], [124, 352, 3, '#6D28D9'], [190, 120, 4, '#2563EB'], [240, 270, 4, '#2563EB'], [114, 138, 5, '#A16207'], [110, 52, 6, '#6B6158'], [296, 126, 6, '#6B6158'], [288, 334, 6, '#6B6158']].map(function (b) {
        return '<circle cx="' + b[0] + '" cy="' + b[1] + '" r="13" fill="' + b[3] + '"/><text x="' + b[0] + '" y="' + (b[1] + 5) + '" fill="#fff">' + b[2] + '</text>';
      }).join('') + '</g></svg>' +
      '<div class="dc-legend"><span><svg width="26" height="6" aria-hidden="true"><line x1="0" y1="3" x2="26" y2="3" stroke="#1E1B2E" stroke-width="2" stroke-dasharray="6 4"/></svg>Western line</span>' +
      '<span><svg width="26" height="6" aria-hidden="true"><line x1="0" y1="3" x2="26" y2="3" stroke="#1E1B2E" stroke-width="2"/></svg>Central line</span></div>' +
      '<p class="dc-sub dc-small">Sketch, not to scale. Tap a zone to jump to it.' + tr('map_note') + '</p></div>';
  }

  function renderZone(z) {
    var pins = (D.zonePins && D.zonePins[z.n]) || [];
    return '<div class="dc-zone" id="dc-zone-' + z.n + '" data-zone="' + z.n + '">' +
      '<div class="dc-zh"><span class="dc-zbadge" style="background:' + z.color + '">' + z.n + '</span><div><span class="dc-zn">' + esc(z.en) + '</span>' + trText(z.hi, z.mr) + '</div></div>' +
      '<p class="dc-areas">' + esc(z.areas) + '</p>' +
      moneyInput('dc-zone-rate-' + z.n, 'Zone ' + z.n + ' transport rate') +
      '<div class="dc-zrow"><button type="button" class="dc-no" aria-pressed="false"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/></svg>Don\'t go</button>' +
      '<button type="button" class="dc-more" aria-expanded="false">See pincodes (' + pins.length + ')</button></div>' +
      '<div class="dc-pins" hidden>' + pins.map(function (p) { return '<div class="dc-pin"><b>' + esc(p[0]) + '</b>' + esc(p[1]) + '</div>'; }).join('') + '</div>' +
      '</div>';
  }

  function renderSection() {
    var h = '<div class="dc-head"><div><div class="dc-h1">Decor Rate Card</div>' + tr('title') + '</div>' +
      '<div class="dc-lang dc-lang-sm" role="group"><button type="button" data-lang="hi" aria-pressed="true">हिंदी</button><button type="button" data-lang="mr" aria-pressed="false">मराठी</button><button type="button" data-lang="en" aria-pressed="false">EN</button></div></div>' +
      '<p class="dc-p">One number per question. Leave a box empty if it doesn\'t apply.' + tr('intro') + '</p>' +

      '<h3 class="dc-h3">About your decor business</h3>' + tr('about') +
      '<div class="dc-q"><div><span class="dc-l">Years in decoration *</span>' + tr('years') + '</div>' + chips('years', ['1–2', '3–5', '5–10', '10+']) + '</div>' +
      '<div class="dc-q"><div><span class="dc-l">People in your team</span>' + tr('team') + '</div>' + chips('team', ['1–2', '3–5', '6+']) + '</div>' +
      '<div class="dc-q"><div><span class="dc-l">Decors you can do in one day</span>' + tr('perday') + '</div>' + chips('perday', ['1', '2', '3+']) + '</div>' +
      '<div class="dc-q"><label for="dc-insta"><span class="dc-l">Instagram or Google page <span class="dc-opt">(optional)</span></span>' + tr('insta') + '</label><input type="url" id="dc-insta" class="dc-inp" placeholder="instagram.com/..." maxlength="300"></div>' +

      '<h3 class="dc-h3">How to give your rates</h3>' + tr('howto') +
      '<p class="dc-p">Quote every decor with <b class="dc-hl">normal balloons</b>. We ask the extra for pastel and chrome separately.' + tr('howto_p') + '</p>' +
      '<div class="dc-btypes"><div><b>Normal</b>' + tr('b_normal') + '<em class="dc-base">Base rate</em></div><div><b>Pastel</b>' + tr('b_pastel') + '<em>+ extra</em></div><div><b>Chrome</b>' + tr('b_chrome') + '<em>+ extra</em></div></div>' +
      '<div class="dc-incl"><b>Your rate includes</b>' + tr('incl') +
      '<div class="dc-rule"><span class="dc-dot">' + CHECK + '</span><div>Material, frame / stand, setup and dismantling' + tr('incl1') + '</div></div>' +
      '<div class="dc-rule"><span class="dc-dot">' + CHECK + '</span><div>We print the flex — you only mount it' + tr('incl2') + '</div></div>' +
      '<div class="dc-rule"><span class="dc-dot dc-dot-grey">' + CROSS + '</span><div>Transport is asked separately' + tr('incl3') + '</div></div></div>';

    h += D.tiers.map(renderTier).join('');

    h += '<div class="dc-block" id="dc-transport"><h3 class="dc-h2">Transport</h3>' + tr('transport') +
      '<p class="dc-p">One <b>fixed rate per area</b> for going and coming back — the same for every decor.' + tr('tr_p') + '</p>' +
      '<p class="dc-note">Includes picking up the flex from our office.' + tr('tr_flex') + '</p>' +
      renderMap() +
      '<p class="dc-sub">Tap “Don\'t go” for areas you don\'t serve.' + tr('dontgo_p') + '</p>' +
      D.zones.map(renderZone).join('') +
      '<div class="dc-q"><label for="dc-rem-transport"><span class="dc-l">Remarks <span class="dc-opt">(optional)</span></span>' + tr('remarks') + '</label><textarea id="dc-rem-transport" class="dc-rem" maxlength="1000"></textarea></div></div>';

    h += '<div class="dc-block"><h3 class="dc-h2">Flex &amp; booking</h3>' + tr('flex_h') +
      '<div class="dc-q"><div><span class="dc-l">Can you pick up the flex from our office?</span>' + tr('flex_q') + '</div>' + chips('flex', ['Yes', 'Sometimes', 'No']) + '</div>' +
      '<div class="dc-q"><div><span class="dc-l">Minimum notice for a booking</span>' + tr('notice_q') + '</div>' + chips('notice', ['1 day', '2 days', '3+ days']) + '</div>' +
      '<h3 class="dc-h3">Photos of your work</h3>' + tr('photos_h') +
      '<div class="dc-q"><div><span class="dc-l">Add 3–5 photos of past decors *</span>' + tr('photos_q') + '</div>' +
      '<div class="dc-photos"><label class="dc-addphoto" id="dc-addphoto"><input type="file" accept="image/jpeg,image/png,image/webp,image/*" multiple id="dc-photo-input"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg><span>Add photo</span></label></div>' +
      '<p class="dc-sub dc-small" id="dc-photo-msg"></p></div>' +
      '<div class="dc-q"><label for="dc-rem-general"><span class="dc-l">Anything else? <span class="dc-opt">(optional)</span></span>' + tr('remarks') + '</label><textarea id="dc-rem-general" class="dc-rem" maxlength="1000"></textarea></div></div>';

    h += '<div class="dc-summary"><div class="dc-h2">Your decor rate card</div>' + tr('summary_h') +
      '<div id="dc-summary-body"></div>' +
      '<p class="dc-fixed">These rates stay fixed for <b>6 months</b>.' + tr('fixed') + '</p>' +
      '<label class="dc-confirm"><input type="checkbox" id="dc-confirm"><span>I\'ve checked my rates — they are final *' + tr('confirm') + '</span></label></div>';
    return h;
  }

  // ── behaviour ──────────────────────────────────────────────────────────
  function applyLang() {
    var lang = state.lang;
    $all('.dc-tr').forEach(function (el) {
      var txt = '';
      if (lang !== 'en') {
        var k = el.getAttribute('data-k');
        txt = k ? ((D.t[k] || {})[lang] || '') : (el.getAttribute('data-' + lang) || '');
      }
      el.textContent = txt;
      el.hidden = !txt;
    });
    $all('[data-lang]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-lang') === lang)); });
  }

  function setPressed(group, value) {
    $all('button', group).forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === value)); });
  }

  function refreshTier(key) {
    var box = document.getElementById('dc-tier-' + key);
    var ts = state.tiers[key];
    $('.dc-skip', box).hidden = ts.does;
    $('.dc-tier-body', box).hidden = !ts.does;
    var gw = $('.dc-galwrap', box), wait = $('.dc-wait', box);
    if (gw) {
      gw.hidden = !ts.rate;
      wait.hidden = !!ts.rate;
      $('.dc-ratetext', box).textContent = ts.rate ? money(ts.rate) : 'this rate';
      var n = { same: 0, other: 0, no: 0 };
      $all('.dc-gi', box).forEach(function (gi) {
        var m = gi.getAttribute('data-mode');
        n[m]++;
        $all('.dc-seg button', gi).forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-mode') === m)); });
        $('.dc-ck', gi).innerHTML = m === 'same' ? CHECK : (m === 'no' ? CROSS : '₹');
        $('.dc-otherrate', gi).hidden = m !== 'other';
      });
      $('.dc-count', box).textContent = n.same + ' same · ' + n.other + ' other rate · ' + n.no + ' can\'t do';
    }
  }

  function renderSummary() {
    var body = document.getElementById('dc-summary-body');
    if (!body) return;
    var h = '<p class="dc-sh">Decor (normal balloons)</p>';
    D.tiers.forEach(function (t) {
      var ts = state.tiers[t.key];
      var extra = '';
      if (ts.does) {
        var other = 0, no = 0;
        Object.keys(ts.modes).forEach(function (id) { if (ts.modes[id] === 'other') other++; if (ts.modes[id] === 'no') no++; });
        if (other || no) extra = '<span class="dc-r-note">' + (other ? other + ' other rate' : '') + (other && no ? ' · ' : '') + (no ? no + ' can\'t do' : '') + '</span>';
      }
      h += '<div class="dc-r"><span>' + esc(t.label) + extra + '</span><span>' + (ts.does ? money(ts.rate) : 'Don\'t do') + '</span></div>';
    });
    h += '<p class="dc-sh">Transport</p>';
    D.zones.forEach(function (z) {
      var zs = state.zones[z.n];
      h += '<div class="dc-r"><span>' + z.n + ' · ' + esc(z.en) + '</span><span>' + (zs.serves ? money(zs.rate) : 'Don\'t go') + '</span></div>';
    });
    body.innerHTML = h;
  }

  function wire(root) {
    root.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b || !root.contains(b)) return;
      if (b.hasAttribute('data-lang')) {
        state.lang = b.getAttribute('data-lang');
        applyLang();
        return;
      }
      var yn = b.closest('[data-yesno]');
      if (yn) {
        var key = yn.getAttribute('data-yesno');
        state.tiers[key].does = b.getAttribute('data-v') === 'yes';
        setPressed(yn, b.getAttribute('data-v'));
        refreshTier(key); renderSummary();
        return;
      }
      var ch = b.closest('[data-chips]');
      if (ch) {
        setPressed(ch, b.getAttribute('data-v'));
        ch.setAttribute('data-value', b.getAttribute('data-v'));
        ch.classList.remove('dc-err');
        return;
      }
      var seg = b.closest('.dc-seg');
      if (seg) {
        var gi = b.closest('.dc-gi'), tier = b.closest('.dc-tier').getAttribute('data-tier');
        var mode = b.getAttribute('data-mode');
        gi.setAttribute('data-mode', mode);
        state.tiers[tier].modes[gi.getAttribute('data-design')] = mode;
        refreshTier(tier); renderSummary();
        if (mode === 'other') { var inp = $('.dc-otherrate input', gi); if (inp) inp.focus(); }
        return;
      }
      if (b.classList.contains('dc-no')) {
        var zbox = b.closest('.dc-zone'), zn = zbox.getAttribute('data-zone');
        var zs = state.zones[zn];
        zs.serves = !zs.serves;
        b.setAttribute('aria-pressed', String(!zs.serves));
        zbox.classList.toggle('dc-off', !zs.serves);
        $('.dc-money input', zbox).disabled = !zs.serves;
        renderSummary();
        return;
      }
      if (b.classList.contains('dc-more')) {
        var pins = b.closest('.dc-zone').querySelector('.dc-pins');
        pins.hidden = !pins.hidden;
        b.setAttribute('aria-expanded', String(!pins.hidden));
        b.textContent = (pins.hidden ? 'See' : 'Hide') + b.textContent.replace(/^(See|Hide)/, '');
        return;
      }
      if (b.classList.contains('dc-rmphoto')) {
        var idx = Number(b.getAttribute('data-i'));
        state.photos.splice(idx, 1);
        renderPhotos();
      }
    });

    root.addEventListener('input', function (e) {
      var el = e.target;
      if (el.closest('.dc-money')) {
        var d = digits(el.value);
        if (d !== el.value) el.value = d;
        el.closest('.dc-money').classList.remove('dc-err');
        var m;
        if ((m = /^dc-rate-(\w+)$/.exec(el.id))) { state.tiers[m[1]].rate = d; refreshTier(m[1]); }
        if ((m = /^dc-zone-rate-(\d)$/.exec(el.id))) { state.zones[m[1]].rate = d; }
        if (el.closest('.dc-otherrate')) {
          var gi = el.closest('.dc-gi'), tier = el.closest('.dc-tier').getAttribute('data-tier');
          state.tiers[tier].other[gi.getAttribute('data-design')] = d;
        }
        renderSummary();
      }
    });

    root.addEventListener('change', function (e) {
      if (e.target.id === 'dc-photo-input') {
        var files = Array.prototype.slice.call(e.target.files || []);
        var room = MAX_PHOTOS - state.photos.length;
        var msg = '';
        if (files.length > room) msg = 'You can add up to ' + MAX_PHOTOS + ' photos.';
        files.slice(0, Math.max(0, room)).forEach(function (f) {
          if (!/^image\//.test(f.type)) { msg = 'Please pick photos (JPG or PNG).'; return; }
          state.photos.push(f);
        });
        e.target.value = '';
        renderPhotos(msg);
      }
      if (e.target.id === 'dc-confirm') e.target.closest('.dc-confirm').classList.remove('dc-err');
    });

    // Gallery and reference photos: no long-press save / right-click / drag.
    root.addEventListener('contextmenu', function (e) { if (e.target.closest('.dc-protect')) e.preventDefault(); });
    root.addEventListener('dragstart', function (e) { if (e.target.closest('.dc-protect')) e.preventDefault(); });
  }

  function renderPhotos(msg) {
    var wrap = $('.dc-photos');
    $all('.dc-thumb', wrap).forEach(function (t) { var img = $('img', t); if (img) URL.revokeObjectURL(img.src); t.remove(); });
    var add = document.getElementById('dc-addphoto');
    state.photos.forEach(function (f, i) {
      var div = document.createElement('div');
      div.className = 'dc-thumb';
      div.innerHTML = '<img alt=""><button type="button" class="dc-rmphoto" data-i="' + i + '" aria-label="Remove photo">' + CROSS + '</button>';
      $('img', div).src = URL.createObjectURL(f);
      wrap.insertBefore(div, add);
    });
    add.hidden = state.photos.length >= MAX_PHOTOS;
    wrap.classList.remove('dc-err');
    document.getElementById('dc-photo-msg').textContent = msg || (state.photos.length ? state.photos.length + ' of ' + MAX_PHOTOS + ' added' : '');
  }

  // Phone photos are often 3-8 MB; shrink to 1600px JPEG before upload so the
  // whole form stays well under the server's size limit.
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
          try { resolve(new File([blob], name, { type: 'image/jpeg' })); } catch (err) { resolve(blob); }
        }, 'image/jpeg', 0.85);
      }).catch(function () { resolve(file); });
    });
  }

  function chipValue(name) {
    var g = document.querySelector('[data-chips="' + name + '"]');
    return g ? (g.getAttribute('data-value') || '') : '';
  }

  // ── public API used by vendor-onboarding.html ─────────────────────────
  var api = {
    active: false,
    toggle: function (on) {
      api.active = !!on;
      document.getElementById('decorCallout').hidden = !on;
      document.getElementById('decorSection').hidden = !on;
    },
    validate: function () {
      function fail(msg, el) {
        if (el) {
          (el.closest('.dc-money') || el.closest('[data-chips]') || el.closest('.dc-confirm') || el).classList.add('dc-err');
        }
        return { error: msg, el: el };
      }
      if (!chipValue('years')) return fail('Please tell us how many years you have been doing decoration.', document.querySelector('[data-chips="years"]'));
      var anyTier = false;
      for (var i = 0; i < D.tiers.length; i++) {
        var t = D.tiers[i], ts = state.tiers[t.key];
        if (!ts.does) continue;
        anyTier = true;
        if (!ts.rate) return fail('Please enter your rate for the ' + t.label + ' decor (or tap “No” if you don\'t do it).', document.getElementById('dc-rate-' + t.key));
        var box = document.getElementById('dc-tier-' + t.key);
        var gis = $all('.dc-gi[data-mode="other"]', box);
        for (var j = 0; j < gis.length; j++) {
          var id = gis[j].getAttribute('data-design');
          if (!ts.other[id]) return fail('Please enter the rate for “' + $('.dc-gn', gis[j]).textContent + '” in ' + t.label + ', or pick Same rate.', $('.dc-otherrate input', gis[j]));
        }
      }
      if (!anyTier) return fail('Please give a rate for at least one decor.', document.getElementById('dc-tier-classic'));
      var anyZone = false;
      for (var k = 0; k < D.zones.length; k++) {
        var z = D.zones[k], zs = state.zones[z.n];
        if (!zs.serves) continue;
        anyZone = true;
        if (!zs.rate) return fail('Please enter your transport rate for zone ' + z.n + ' (' + z.en + '), or tap “Don\'t go”.', document.getElementById('dc-zone-rate-' + z.n));
      }
      if (!anyZone) return fail('Please give a transport rate for at least one zone.', document.getElementById('dc-transport'));
      if (!state.photos.length) return fail('Please add at least one photo of your past decor work.', $('.dc-photos'));
      var c = document.getElementById('dc-confirm');
      if (!c.checked) return fail('Please tick “I\'ve checked my rates — they are final”.', c);
      return { error: null };
    },
    build: function () {
      var card = {
        version: 1,
        language: state.lang,
        about: {
          years: chipValue('years'), team: chipValue('team'), decors_per_day: chipValue('perday'),
          page_link: (document.getElementById('dc-insta').value || '').trim()
        },
        tiers: {},
        transport: { zones: [], remarks: (document.getElementById('dc-rem-transport').value || '').trim() },
        flex_pickup: chipValue('flex'),
        min_notice: chipValue('notice'),
        remarks: (document.getElementById('dc-rem-general').value || '').trim(),
        confirmed: !!document.getElementById('dc-confirm').checked
      };
      D.tiers.forEach(function (t) {
        var ts = state.tiers[t.key];
        if (!ts.does) { card.tiers[t.key] = { does: false }; return; }
        var designs = ((G.designs && G.designs[t.label]) || []).map(function (d) {
          var m = ts.modes[d.id] || 'same';
          var o = { id: d.id, name: d.name, mode: m };
          if (m === 'other') o.rate = Number(ts.other[d.id] || 0);
          return o;
        });
        card.tiers[t.key] = {
          does: true,
          rate: Number(ts.rate || 0),
          pastel_extra: Number(digits(document.getElementById('dc-pastel-' + t.key).value) || 0) || null,
          chrome_extra: Number(digits(document.getElementById('dc-chrome-' + t.key).value) || 0) || null,
          setup_time: chipValue('setup-' + t.key),
          remarks: (document.getElementById('dc-rem-' + t.key).value || '').trim(),
          designs: designs
        };
      });
      D.zones.forEach(function (z) {
        var zs = state.zones[z.n];
        card.transport.zones.push({ zone: z.n, name: z.en, serves: zs.serves, rate: zs.serves ? Number(zs.rate || 0) : null });
      });
      return card;
    },
    appendTo: function (fd) {
      fd.append('decor_rate_card', JSON.stringify(api.build()));
      return Promise.all(state.photos.map(shrink)).then(function (files) {
        files.forEach(function (f, i) { fd.append('work_photos', f, (f.name || ('work-photo-' + (i + 1) + '.jpg'))); });
      });
    }
  };
  window.WSDecor = api;

  function init() {
    var callout = document.getElementById('decorCallout');
    var section = document.getElementById('decorSection');
    if (!callout || !section) return;
    callout.innerHTML = renderCallout();
    section.innerHTML = renderSection();
    wire(callout); wire(section);
    D.tiers.forEach(function (t) { refreshTier(t.key); });
    renderSummary();
    applyLang();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
