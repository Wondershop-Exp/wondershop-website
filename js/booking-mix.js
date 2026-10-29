/* Booking mix on the Analytics dashboard (2026-10-29, per Shruti):
   bookings by child gender, by age, and by locality on a Mumbai / Pune map,
   filtered by booking month, lead month and sales lead.
   Data: GET /api/admin/dashboard/booking-mix (one row per non-cancelled booking).
   Locality comes from the venue text (known area names, a few landmarks),
   else the pincode; anything still unknown is listed under "Not on map". */
(function(){
  // [lat, lng, city]
  var C = {
    'Colaba':[18.9067,72.8147,'Mumbai'],'Fort':[18.9338,72.8355,'Mumbai'],'Churchgate':[18.9322,72.8264,'Mumbai'],'Nariman Point':[18.9256,72.8242,'Mumbai'],
    'Cuffe Parade':[18.9150,72.8200,'Mumbai'],'Marine Lines':[18.9440,72.8237,'Mumbai'],'Girgaon':[18.9550,72.8150,'Mumbai'],'Grant Road':[18.9633,72.8158,'Mumbai'],
    'Tardeo':[18.9700,72.8130,'Mumbai'],'Malabar Hill':[18.9548,72.7985,'Mumbai'],'Breach Candy':[18.9690,72.8050,'Mumbai'],'Peddar Road':[18.9720,72.8090,'Mumbai'],
    'Mumbai Central':[18.9690,72.8205,'Mumbai'],'Byculla':[18.9790,72.8330,'Mumbai'],'Mazgaon':[18.9650,72.8430,'Mumbai'],'Mahalaxmi':[18.9827,72.8240,'Mumbai'],
    'Parel':[19.0000,72.8410,'Mumbai'],'Lower Parel':[18.9960,72.8300,'Mumbai'],'Lalbaug':[18.9930,72.8380,'Mumbai'],'Worli':[19.0170,72.8170,'Mumbai'],
    'Prabhadevi':[19.0160,72.8290,'Mumbai'],'Dadar':[19.0190,72.8430,'Mumbai'],'Mahim':[19.0400,72.8400,'Mumbai'],'Matunga':[19.0270,72.8550,'Mumbai'],
    'Wadala':[19.0160,72.8650,'Mumbai'],'Sewri':[19.0000,72.8560,'Mumbai'],'Sion':[19.0440,72.8640,'Mumbai'],'Antop Hill':[19.0230,72.8650,'Mumbai'],
    'Bandra':[19.0596,72.8295,'Mumbai'],'Khar':[19.0710,72.8360,'Mumbai'],'Santacruz':[19.0810,72.8410,'Mumbai'],'Juhu':[19.1075,72.8263,'Mumbai'],
    'Vile Parle':[19.0990,72.8490,'Mumbai'],'Andheri':[19.1197,72.8468,'Mumbai'],'Lokhandwala':[19.1420,72.8250,'Mumbai'],'Versova':[19.1330,72.8150,'Mumbai'],
    'Oshiwara':[19.1490,72.8350,'Mumbai'],'JVLR':[19.1350,72.8700,'Mumbai'],'Jogeshwari':[19.1380,72.8490,'Mumbai'],'Goregaon':[19.1663,72.8526,'Mumbai'],
    'Malad':[19.1860,72.8480,'Mumbai'],'Kandivali':[19.2040,72.8520,'Mumbai'],'Borivali':[19.2307,72.8567,'Mumbai'],'Dahisar':[19.2500,72.8590,'Mumbai'],
    'Mira Road':[19.2810,72.8690,'Mumbai'],'Bhayander':[19.3010,72.8510,'Mumbai'],'Kurla':[19.0728,72.8826,'Mumbai'],'Chembur':[19.0522,72.9005,'Mumbai'],
    'Ghatkopar':[19.0860,72.9080,'Mumbai'],'Vikhroli':[19.1110,72.9280,'Mumbai'],'Kanjurmarg':[19.1290,72.9350,'Mumbai'],'Bhandup':[19.1440,72.9380,'Mumbai'],
    'Mulund':[19.1720,72.9560,'Mumbai'],'Powai':[19.1176,72.9060,'Mumbai'],'Saki Naka':[19.1030,72.8890,'Mumbai'],'Marol':[19.1100,72.8800,'Mumbai'],
    'Chandivali':[19.1150,72.8950,'Mumbai'],'Govandi':[19.0550,72.9150,'Mumbai'],'Mankhurd':[19.0480,72.9320,'Mumbai'],'Deonar':[19.0500,72.9100,'Mumbai'],
    'Thane':[19.2183,72.9781,'Mumbai'],'Kalwa':[19.2000,72.9970,'Mumbai'],'Airoli':[19.1570,72.9990,'Mumbai'],'Ghansoli':[19.1210,73.0050,'Mumbai'],
    'Vashi':[19.0771,72.9986,'Mumbai'],'Sanpada':[19.0640,73.0090,'Mumbai'],'Nerul':[19.0330,73.0180,'Mumbai'],'Seawoods':[19.0180,73.0170,'Mumbai'],
    'Belapur':[19.0230,73.0400,'Mumbai'],'Kharghar':[19.0470,73.0700,'Mumbai'],'Panvel':[18.9890,73.1100,'Mumbai'],'Navi Mumbai':[19.0330,73.0297,'Mumbai'],
    'Dombivli':[19.2180,73.0870,'Mumbai'],'Kalyan':[19.2400,73.1300,'Mumbai'],'Ulhasnagar':[19.2210,73.1640,'Mumbai'],'Ambernath':[19.2090,73.1860,'Mumbai'],
    'Badlapur':[19.1550,73.2650,'Mumbai'],'Vasai':[19.3910,72.8390,'Mumbai'],'Nalasopara':[19.4180,72.8190,'Mumbai'],'Virar':[19.4560,72.8110,'Mumbai'],
    'Kothrud':[18.5074,73.8077,'Pune'],'Baner':[18.5590,73.7868,'Pune'],'Aundh':[18.5580,73.8075,'Pune'],'Wakad':[18.5990,73.7620,'Pune'],
    'Hinjewadi':[18.5913,73.7389,'Pune'],'Balewadi':[18.5770,73.7790,'Pune'],'Pashan':[18.5380,73.7920,'Pune'],'Bavdhan':[18.5150,73.7820,'Pune'],
    'Viman Nagar':[18.5679,73.9143,'Pune'],'Kalyani Nagar':[18.5480,73.9020,'Pune'],'Koregaon Park':[18.5362,73.8940,'Pune'],'Yerawada':[18.5530,73.8770,'Pune'],
    'Kharadi':[18.5510,73.9410,'Pune'],'Wagholi':[18.5800,73.9850,'Pune'],'Hadapsar':[18.5089,73.9260,'Pune'],'Magarpatta':[18.5150,73.9290,'Pune'],
    'Wanowrie':[18.4900,73.9000,'Pune'],'Kondhwa':[18.4660,73.8890,'Pune'],'NIBM':[18.4720,73.8990,'Pune'],'Undri':[18.4540,73.9080,'Pune'],
    'Pune Camp':[18.5150,73.8780,'Pune'],'Shivaji Nagar':[18.5308,73.8475,'Pune'],'Deccan':[18.5170,73.8410,'Pune'],'Erandwane':[18.5080,73.8320,'Pune'],
    'Model Colony':[18.5310,73.8370,'Pune'],'Sadashiv Peth':[18.5100,73.8500,'Pune'],'Bibwewadi':[18.4730,73.8640,'Pune'],'Katraj':[18.4480,73.8580,'Pune'],
    'Sinhagad Road':[18.4800,73.8200,'Pune'],'Warje':[18.4820,73.7980,'Pune'],'Pimple Saudagar':[18.5980,73.7980,'Pune'],'Pimpri':[18.6270,73.8000,'Pune'],
    'Chinchwad':[18.6440,73.7920,'Pune']
  };
  // other spellings / landmarks -> area
  var ALIAS = {'ville parle':'Vile Parle','vileparle':'Vile Parle','chemur':'Chembur','santa cruz':'Santacruz','kandivli':'Kandivali','borivli':'Borivali',
    'bhayandar':'Bhayander','ghatkoper':'Ghatkopar','sakinaka':'Saki Naka','kanjur marg':'Kanjurmarg','bkc':'Bandra','bandra kurla':'Bandra',
    'hiranandani gardens':'Powai','oberoi exquisite':'Goregaon','oberoi mall':'Goregaon','godrej platinum':'Vikhroli',
    'phoenix palladium':'Lower Parel','high street phoenix':'Lower Parel','r city':'Ghatkopar','shivajinagar':'Shivaji Nagar',
    'koregaon':'Koregaon Park','vimannagar':'Viman Nagar','kalyaninagar':'Kalyani Nagar','pune camp':'Pune Camp'};
  var PIN = {'400005':'Colaba','400001':'Fort','400020':'Churchgate','400021':'Nariman Point','400006':'Malabar Hill','400026':'Breach Candy','400007':'Grant Road',
    '400008':'Mumbai Central','400011':'Mahalaxmi','400012':'Parel','400013':'Lower Parel','400018':'Worli','400025':'Prabhadevi','400028':'Dadar','400014':'Dadar',
    '400016':'Mahim','400019':'Matunga','400031':'Wadala','400037':'Antop Hill','400022':'Sion','400050':'Bandra','400051':'Bandra','400052':'Khar',
    '400054':'Santacruz','400055':'Santacruz','400049':'Juhu','400056':'Vile Parle','400057':'Vile Parle','400053':'Andheri','400058':'Andheri','400069':'Andheri',
    '400093':'Andheri','400099':'Andheri','400059':'Marol','400060':'Jogeshwari','400102':'Jogeshwari','400062':'Goregaon','400063':'Goregaon','400104':'Goregaon',
    '400064':'Malad','400095':'Malad','400097':'Malad','400067':'Kandivali','400101':'Kandivali','400091':'Borivali','400092':'Borivali','400066':'Borivali',
    '400068':'Dahisar','401107':'Mira Road','401101':'Bhayander','400070':'Kurla','400024':'Kurla','400071':'Chembur','400074':'Chembur','400089':'Chembur',
    '400075':'Ghatkopar','400077':'Ghatkopar','400084':'Ghatkopar','400086':'Ghatkopar','400079':'Vikhroli','400083':'Vikhroli','400042':'Kanjurmarg','400078':'Bhandup',
    '400080':'Mulund','400081':'Mulund','400082':'Mulund','400076':'Powai','400072':'Saki Naka','400087':'Powai','400043':'Govandi','400088':'Govandi',
    '400601':'Thane','400602':'Thane','400603':'Thane','400604':'Thane','400606':'Thane','400607':'Thane','400610':'Thane','400615':'Thane','400605':'Kalwa',
    '400708':'Airoli','400701':'Ghansoli','400703':'Vashi','400705':'Sanpada','400706':'Nerul','400614':'Belapur','410210':'Kharghar','410206':'Panvel',
    '421201':'Dombivli','421202':'Dombivli','421301':'Kalyan',
    '411038':'Kothrud','411045':'Baner','411007':'Aundh','411057':'Wakad','411027':'Pimple Saudagar','411033':'Chinchwad','411018':'Pimpri','411014':'Viman Nagar',
    '411006':'Kalyani Nagar','411001':'Pune Camp','411028':'Hadapsar','411048':'Kondhwa','411060':'NIBM','411021':'Bavdhan','411004':'Deccan','411016':'Model Colony',
    '411005':'Shivaji Nagar','411030':'Sadashiv Peth','411037':'Bibwewadi','411046':'Katraj','411041':'Sinhagad Road','411052':'Warje','411008':'Pashan','411040':'Wanowrie'};
  var KEYS = Object.keys(C).map(function(k){ return [k.toLowerCase(), k]; })
    .concat(Object.keys(ALIAS).map(function(k){ return [k, ALIAS[k]]; }))
    .sort(function(a,b){ return b[0].length - a[0].length; });
  function locate(r){
    var t = ' ' + String(r.venue||'').toLowerCase().replace(/[^a-z0-9]+/g,' ') + ' ', best = null, bestAt = -1;
    KEYS.forEach(function(k){ var at = t.lastIndexOf(' ' + k[0] + ' '); if(at > bestAt){ bestAt = at; best = k[1]; } });
    var pin = String(r.pincode||'').trim();
    if(!best && PIN[pin]) best = PIN[pin];
    if(!best) return null;
    return {name: best, lat: C[best][0], lng: C[best][1], city: C[best][2]};
  }

  var DATA = null, MAP = null, F = {bm:'', lm:'', sl:''}, VIEW = 'Mumbai';
  var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function ml(ym){ return ym ? MON[+ym.slice(5,7)-1]+' '+ym.slice(0,4) : ''; }
  function e(s){ return String(s==null?'':s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function opts(vals, cur, fmt){ return '<option value="">All</option>' + vals.map(function(v){ return '<option value="'+e(v)+'"'+(v===cur?' selected':'')+'>'+e(fmt?fmt(v):v)+'</option>'; }).join(''); }
  function uniq(a){ return Array.from(new Set(a.filter(Boolean))); }
  function bars(rows, color){
    var max = Math.max.apply(null, rows.map(function(r){ return r[1]; }).concat([1]));
    var tot = rows.reduce(function(t,r){ return t+r[1]; }, 0);
    if(!tot) return '<div class="empty">No bookings for these filters.</div>';
    return rows.map(function(r){
      return '<div class="bm-bar"><span class="bm-l">'+e(r[0])+'</span><span class="bm-t"><span style="width:'+(r[1]/max*100)+'%;background:'+color+'"></span></span>'
        + '<span class="bm-v">'+r[1]+' <small>'+Math.round(r[1]/tot*100)+'%</small></span></div>';
    }).join('');
  }
  function filtered(){
    return DATA.filter(function(r){ return (!F.bm || r.booking_month===F.bm) && (!F.lm || r.lead_month===F.lm) && (!F.sl || r.sales_lead===F.sl); });
  }
  function render(){
    var card = document.getElementById('bookingMixCard'); if(!card || !DATA) return;
    var R = filtered();
    var g = {}; R.forEach(function(r){ r.genders.forEach(function(x){ g[x]=(g[x]||0)+1; }); });
    var gRows = ['Girl','Boy','Not specified'].filter(function(k){ return g[k]; }).map(function(k){ return [k, g[k]]; });
    var a = {}, noAge = 0;
    R.forEach(function(r){ if(!r.ages.length) noAge++; r.ages.forEach(function(x){ var k = x>=13 ? '13+' : String(x); a[k]=(a[k]||0)+1; }); });
    var aRows = ['1','2','3','4','5','6','7','8','9','10','11','12','13+'].filter(function(k){ return a[k]; }).map(function(k){ return [k+(k==='1'?' yr':' yrs'), a[k]]; });
    var loc = {}, off = [];
    R.forEach(function(r){ var l = locate(r); if(l){ (loc[l.name] = loc[l.name] || {l:l, n:0, who:[]}).n++; loc[l.name].who.push(r); } else off.push(r); });
    var locRows = Object.keys(loc).map(function(k){ return loc[k]; }).sort(function(x,y){ return y.n-x.n; });
    var shown = locRows.filter(function(x){ return x.l.city===VIEW; });
    var bms = uniq(DATA.map(function(r){ return r.booking_month; })).sort().reverse();
    var lms = uniq(DATA.map(function(r){ return r.lead_month; })).sort().reverse();
    var sls = uniq(DATA.map(function(r){ return r.sales_lead; })).sort();
    card.innerHTML =
      '<div class="dash-card-title-row"><div class="dash-card-title" style="margin-bottom:0">Booking mix <span style="font-weight:400;color:var(--gy)">· '+R.length+' booking'+(R.length===1?'':'s')+', cancelled excluded</span></div>'
      + '<div class="bm-filters"><label>Booking month<select onchange="wsBM.set(\'bm\',this.value)">'+opts(bms, F.bm, ml)+'</select></label>'
      + '<label>Lead month<select onchange="wsBM.set(\'lm\',this.value)">'+opts(lms, F.lm, ml)+'</select></label>'
      + '<label>Sales lead<select onchange="wsBM.set(\'sl\',this.value)">'+opts(sls, F.sl)+'</select></label></div></div>'
      + '<div class="bm-grid"><div><div class="bm-h">By gender <small>each child counted</small></div>'+bars(gRows, '#D6457F')+'</div>'
      + '<div><div class="bm-h">By age <small>each child counted'+(noAge?' · '+noAge+' booking'+(noAge===1?'':'s')+' without an age':'')+'</small></div>'+bars(aRows, '#6C4AB6')+'</div></div>'
      + '<div class="bm-h bm-maphead">By locality'
      + '<span class="bm-view"><button class="'+(VIEW==='Mumbai'?'on':'')+'" onclick="wsBM.view(\'Mumbai\')">Mumbai</button><button class="'+(VIEW==='Pune'?'on':'')+'" onclick="wsBM.view(\'Pune\')">Pune</button></span></div>'
      + '<div class="bm-mapwrap"><div id="bmMap"></div><div class="bm-loclist">'
      + (shown.length ? shown.map(function(x){ return '<div class="bm-loc" onclick="wsBM.fly('+x.l.lat+','+x.l.lng+')"><span>'+e(x.l.name)+'</span><b>'+x.n+'</b></div>'; }).join('')
                      : '<div class="empty">No bookings mapped in '+VIEW+'.</div>')
      + (off.length ? '<div class="bm-off"><b>Not on map ('+off.length+')</b><small>No known area in the venue or pincode</small>'
          + off.map(function(r){ return '<div>#'+r.id+' '+e(r.name||'')+' · <span>'+e(r.venue||r.pincode||'no venue')+'</span></div>'; }).join('')+'</div>' : '')
      + '</div></div>';
    drawMap(shown);
  }
  function loadLeaflet(cb){
    if(window.L) return cb();
    var css = document.createElement('link'); css.rel='stylesheet'; css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'; document.head.appendChild(css);
    var s = document.createElement('script'); s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'; s.onload=cb; document.head.appendChild(s);
  }
  function drawMap(rows){
    loadLeaflet(function(){
      var el = document.getElementById('bmMap'); if(!el) return;
      if(MAP){ MAP.remove(); MAP = null; }
      MAP = L.map(el, {scrollWheelZoom:false});
      // OpenStreetMap's own free tiles (CARTO now asks for a key on live sites, 2026-10-29).
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'&copy; OpenStreetMap contributors'}).addTo(MAP);
      if(VIEW==='Pune') MAP.setView([18.5204,73.8567], 11); else MAP.setView([19.10,72.93], 10);
      var max = Math.max.apply(null, rows.map(function(x){ return x.n; }).concat([1]));
      rows.forEach(function(x){
        L.circleMarker([x.l.lat, x.l.lng], {radius: 7 + 16*Math.sqrt(x.n/max), color:'#B4236B', weight:1.5, fillColor:'#D6457F', fillOpacity:.55})
          .bindTooltip(e(x.l.name)+' · '+x.n, {permanent:true, direction:'right', offset:[8,0], className:'bm-tip'})   // always-visible labels (2026-10-29)
          .bindPopup('<b>'+e(x.l.name)+'</b> · '+x.n+'<br>'+x.who.map(function(r){ return '#'+r.id+' '+e(r.name||''); }).join('<br>'))
          .addTo(MAP);
      });
    });
  }
  window.wsBM = {
    load: async function(){
      var card = document.getElementById('bookingMixCard'); if(!card) return;
      try{ DATA = (await apiCall('/api/admin/dashboard/booking-mix')).rows || []; render(); }
      catch(err){ if(err.message!=='unauthorized') card.innerHTML = '<div class="dash-card-title">Booking mix</div><div class="empty">Couldn\'t load: '+e(err.message)+'</div>'; }
    },
    set: function(k, v){ F[k] = v; render(); },
    view: function(v){ VIEW = v; render(); },
    fly: function(lat, lng){ if(MAP) MAP.setView([lat, lng], 13); },
    locate: locate
  };
})();
