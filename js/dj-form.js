// "DJ" section of the partner onboarding form (2026-10-21, per Shruti).
// Shown when "DJ" is picked. The DJ ticks the Mumbai zones they serve and,
// for each one, quotes two standard setups plus two add-ons. Exposes
// window.WSDJ:
//   toggle(on)      show / hide the section
//   validate()      -> {error, el} for the first problem, or {} when complete
//   appendTo(fd)    adds dj_profile (JSON)
//   fill(profile)   pre-fills from an update link
// Zones come from js/volunteer-data.js (same 6 Mumbai zones everywhere).
// The alternate mobile number is mandatory for DJs (vendor-onboarding.html).
(function () {
  var host = document.getElementById('djSection');
  if (!host) return;
  var ZONES = (window.WS_VOLUNTEER && window.WS_VOLUNTEER.zones) || [];
  // Keep in step with DJ_ITEMS in backend/routers/vendor_onboarding.py.
  var ITEMS = [
    { k: 'two_tops', l: 'Setup 1: 2 tops with stands + DJ with console + 2 mics', req: true },
    { k: 'one_top', l: 'Setup 2: 1 top with stand + DJ with console + 2 mics', req: true },
    { k: 'led4', l: 'Extra: 4 LED lights with stands', req: false },
    { k: 'smoke', l: 'Extra: Smoke machine', req: false }
  ];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function money(z, it) {
    return '<div class="dj-q"><label for="dj_' + z + '_' + it.k + '">' + esc(it.l) +
      (it.req ? ' *' : ' <span class="opt">(blank if you don’t provide it)</span>') + '</label>' +
      '<div class="dj-rs"><span>₹</span><input type="text" inputmode="numeric" maxlength="7" id="dj_' + z + '_' + it.k + '" data-z="' + z + '" data-k="' + it.k + '" placeholder="e.g. 8000"></div></div>';
  }

  host.innerHTML =
    '<div class="sec-h">Your DJ rates</div>' +
    '<div class="sec-sub">Tick each area of Mumbai you serve and give your price for each setup there, including transport. ' +
    'Leave an extra blank if you don’t provide it.</div>' +
    '<div id="dj_zones">' + ZONES.map(function (z) {
      return '<div class="dj-zone" id="dj_zone_' + z.n + '">' +
        '<label class="vl-zone dj-zone-h"><input type="checkbox" name="dj_zone" value="' + z.n + '">' +
          '<span><b>Zone ' + z.n + ' · ' + esc(z.en) + '</b><small>' + esc(z.areas) + '</small></span></label>' +
        '<div class="dj-prices" hidden>' + ITEMS.map(function (it) { return money(z.n, it); }).join('') + '</div>' +
      '</div>';
    }).join('') + '</div>' +
    '<div class="fld"><label>Anything else about your rates or setup? <span class="opt">(optional)</span></label>' +
      '<textarea id="dj_notes" maxlength="1000" placeholder="e.g. Extra hour ₹1,500; wireless mics; own generator"></textarea></div>';

  function $(id) { return document.getElementById(id); }
  function served() {
    return Array.prototype.map.call(host.querySelectorAll('input[name="dj_zone"]:checked'), function (i) { return +i.value; });
  }
  function sync() {
    ZONES.forEach(function (z) {
      var on = host.querySelector('input[name="dj_zone"][value="' + z.n + '"]').checked;
      $('dj_zone_' + z.n).querySelector('.dj-prices').hidden = !on;
      $('dj_zone_' + z.n).classList.toggle('on', on);
    });
  }
  host.addEventListener('change', function (e) { if (e.target.name === 'dj_zone') sync(); });
  host.addEventListener('input', function (e) {
    if (e.target.getAttribute('data-k')) {
      var d = e.target.value.replace(/\D/g, '').slice(0, 7);
      if (d !== e.target.value) e.target.value = d;
    }
  });

  function collect() {
    var rates = {};
    served().forEach(function (z) {
      var r = {};
      ITEMS.forEach(function (it) {
        var v = $('dj_' + z + '_' + it.k).value.trim();
        r[it.k] = v === '' ? null : +v;
      });
      rates[z] = r;
    });
    return { zones: served(), rates: rates, notes: $('dj_notes').value.trim() };
  }

  window.WSDJ = {
    toggle: function (on) { host.hidden = !on; },
    validate: function () {
      var p = collect();
      if (!p.zones.length) return { error: 'Please tick the areas of Mumbai you serve.', el: $('dj_zones') };
      for (var i = 0; i < p.zones.length; i++) {
        var z = p.zones[i];
        for (var j = 0; j < ITEMS.length; j++) {
          var it = ITEMS[j];
          if (it.req && !p.rates[z][it.k]) {
            var el = $('dj_' + z + '_' + it.k);
            return { error: 'Please give your price for ' + it.l.split(':')[0].toLowerCase() + ' in zone ' + z + '.', el: el };
          }
        }
      }
      return {};
    },
    appendTo: function (fd) { fd.append('dj_profile', JSON.stringify(collect())); },
    fill: function (p) {
      if (!p) return;
      (p.zones || []).forEach(function (z) {
        var cb = host.querySelector('input[name="dj_zone"][value="' + z + '"]');
        if (cb) cb.checked = true;
        var r = (p.rates || {})[z] || {};
        ITEMS.forEach(function (it) { if (r[it.k] != null) $('dj_' + z + '_' + it.k).value = r[it.k]; });
      });
      if (p.notes) $('dj_notes').value = p.notes;
      sync();
    }
  };
})();
