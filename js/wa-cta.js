/* Wondershop WhatsApp CTA (2026-11-10)
   - Pre-fills a message naming the page on every wa.me link
   - Labelled WhatsApp pill on desktop; on mobile a sticky bar with "Book Online" (builder) + WhatsApp icon
   - Sends GA4 event "whatsapp_click" and Meta Pixel "Contact" on every WhatsApp click */
(function () {
  var NUM = '919742240477';
  var page = (document.title || '').split(/\s[|—–-]\s/)[0].replace('Wondershop Experiences', 'Home').trim() || 'Website';
  var msg = 'Hi Wondershop! I\'d like to plan a birthday party. (page: ' + page + ')';
  var href = 'https://wa.me/' + NUM + '?text=' + encodeURIComponent(msg);
  var noBar = /builder\.html/.test(location.pathname);

  // 1. Pre-fill any plain wa.me link
  document.querySelectorAll('a[href*="wa.me/' + NUM + '"]').forEach(function (a) {
    if (a.href.indexOf('text=') === -1) a.href = href;
  });

  // 2. Replace the icon-only button with a labelled pill + mobile bar
  var old = document.querySelector('.wa-fab'); if (old) old.remove();
  var css = document.createElement('style');
  css.textContent =
    '.ws-wa-pill{position:fixed;left:24px;bottom:24px;z-index:9999;display:flex;align-items:center;gap:8px;background:#25D366;color:#fff;font:700 15px/1 "DM Sans",sans-serif;padding:13px 20px 13px 16px;border-radius:50px;box-shadow:0 6px 20px rgba(37,211,102,.45);text-decoration:none;transition:transform .2s}' +
    '.ws-wa-pill:hover{transform:scale(1.04)}.ws-wa-pill svg{width:22px;height:22px;flex:none}' +
    '.ws-bar{display:none}' +
    '@media(max-width:700px){' + (noBar ? '.ws-wa-pill{bottom:16px;left:16px;padding:12px}.ws-wa-pill span{display:none}' :
      '.ws-wa-pill{display:none}.ws-bar{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:9999;gap:8px;padding:8px 10px calc(8px + env(safe-area-inset-bottom));background:#fff;box-shadow:0 -4px 16px rgba(0,0,0,.12)}' +
      '.ws-bar-book{flex:1;display:flex;align-items:center;justify-content:center;background:#8455DD;color:#fff;font:700 16px/1 "DM Sans",sans-serif;border-radius:50px;padding:15px 12px;text-decoration:none}' +
      '.ws-bar-wa{flex:none;width:52px;display:flex;align-items:center;justify-content:center;border:2px solid #191919;border-radius:50px;color:#25D366;text-decoration:none}.ws-bar-wa svg{width:24px;height:24px}' +
      'body{padding-bottom:72px}.cart-fab{bottom:84px!important}') + '}';
  document.head.appendChild(css);
  var ico = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17.47 14.38c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.16-.17.2-.35.22-.64.08-.3-.15-1.26-.47-2.39-1.48-.88-.79-1.48-1.76-1.65-2.06-.17-.3-.02-.46.13-.6.13-.14.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.03-.52-.07-.15-.67-1.61-.92-2.2-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.79.37-.27.3-1.04 1.02-1.04 2.48s1.07 2.88 1.21 3.07c.15.2 2.1 3.2 5.08 4.49.71.31 1.26.49 1.7.63.71.22 1.36.19 1.87.12.57-.09 1.76-.72 2.01-1.41.25-.7.25-1.29.17-1.41-.07-.13-.27-.2-.57-.35M12.05 21.79h-.01a9.87 9.87 0 0 1-5.03-1.38l-.36-.21-3.74.98 1-3.65-.24-.37a9.86 9.86 0 0 1-1.51-5.26c0-5.45 4.44-9.88 9.89-9.88a9.82 9.82 0 0 1 6.99 2.9 9.82 9.82 0 0 1 2.89 6.99c0 5.45-4.44 9.88-9.88 9.88m8.41-18.3A11.82 11.82 0 0 0 12.05 0C5.5 0 .16 5.34.16 11.89c0 2.1.55 4.14 1.59 5.95L.06 24l6.3-1.65a11.88 11.88 0 0 0 5.68 1.45h.01c6.55 0 11.89-5.34 11.89-11.89a11.82 11.82 0 0 0-3.48-8.41"/></svg>';
  function add(cls, inner, loc) {
    var a = document.createElement('a');
    a.className = cls; a.href = href; a.target = '_blank'; a.rel = 'noopener';
    a.setAttribute('aria-label', 'Chat with Wondershop on WhatsApp'); a.dataset.waLoc = loc; a.innerHTML = inner;
    document.body.appendChild(a);
  }
  add('ws-wa-pill', ico + '<span>Chat on WhatsApp</span>', 'floating');
  if (!noBar) {
    var bar = document.createElement('div'); bar.className = 'ws-bar';
    var root = /\/blogs\//.test(location.pathname) ? '../' : '';
    bar.innerHTML = '<a class="ws-bar-book" href="' + root + 'builder.html?start=1" data-book-loc="mobile_bar">Book Online ✦</a>' +
      '<a class="ws-bar-wa" href="' + href + '" target="_blank" rel="noopener" aria-label="Chat on WhatsApp" data-wa-loc="mobile_bar">' + ico + '</a>';
    document.body.appendChild(bar);
  }

  // 3. Track every WhatsApp click
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href*="wa.me"],a[href*="api.whatsapp.com"]');
    if (!a) return;
    var loc = a.dataset.waLoc || (a.closest('footer') ? 'footer' : a.closest('nav') ? 'nav' : 'in_page');
    try { if (window.gtag) gtag('event', 'whatsapp_click', { link_location: loc, page_title: page, page_path: location.pathname }); } catch (x) {}
    try { if (window.fbq) fbq('track', 'Contact', { content_name: page }); } catch (x) {}
  }, true);

  // 4. Track "Book Online" clicks from the mobile bar
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-book-loc]');
    if (!b) return;
    try { if (window.gtag) gtag('event', 'book_online_click', { link_location: b.dataset.bookLoc, page_title: page, page_path: location.pathname }); } catch (x) {}
  }, true);
})();
