// Spy minimum bill by area (2026-10-14, per Shruti): ₹25,000 minimum on any
// Spy booking (package mission stations / Spy Treasure Hunt), irrespective
// of the number of kids — ₹30,000 for Bandra, Khar, South Bombay, Lower
// Parel, Parel, Prabhadevi, Mahim and Byculla. Area = the pincode the
// customer entered (homepage area picker -> localStorage 'ws_loc_v1', or
// Build-a-Birthday's own pincode fields). WEBSITE ONLY — the sales panel and
// the bookings page deliberately don't apply this.
(function(){
  var PREMIUM = [
    '400050','400051',                 // Bandra
    '400052',                          // Khar
    '400013',                          // Lower Parel
    '400012',                          // Parel
    '400025',                          // Prabhadevi
    '400016',                          // Mahim
    '400027',                          // Byculla
    // South Bombay: Fort, Kalbadevi, Masjid, Girgaon, Colaba/Cuffe Parade,
    // Malabar Hill, Grant Road, Mumbai Central, Mandvi, Mazgaon, Mahalaxmi,
    // Churchgate/Marine Lines, Nariman Point, Breach Candy/Peddar Road,
    // Tardeo, Walkeshwar
    '400001','400002','400003','400004','400005','400006','400007','400008','400009','400010','400011',
    '400020','400021','400026','400034','400035'
  ];
  window.WS_SPY_MIN_BILL = 25000;
  window.WS_SPY_MIN_BILL_PREMIUM = 30000;
  window.wsSpyIsPremiumPin = function(pin){ return PREMIUM.indexOf(String(pin||'').trim()) > -1; };
  // Pincode saved by the homepage's area picker ('' if none).
  window.wsSpySavedPin = function(){
    try{ var l = JSON.parse(localStorage.getItem('ws_loc_v1') || 'null'); return (l && l.pin) ? String(l.pin) : ''; }
    catch(e){ return ''; }
  };
  window.wsSpyMinBill = function(pin){
    if(pin === undefined || pin === null || pin === '') pin = window.wsSpySavedPin();
    return window.wsSpyIsPremiumPin(pin) ? window.WS_SPY_MIN_BILL_PREMIUM : window.WS_SPY_MIN_BILL;
  };
  window.WS_SPY_PRICE_NOTE = 'Starting from ₹25,000 · pricing will be confirmed once you enter the venue address';
})();
