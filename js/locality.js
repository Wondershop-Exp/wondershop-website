// Locality from a free-text venue (2026-10-12, per Shruti): "hiranandani
// gardens Near galleria mall Next to Cult Fit Powai" -> "Powai". Looks for a
// known Mumbai locality anywhere in the text (the one mentioned last wins);
// otherwise falls back to the last comma-separated part. Used by the sales
// list (sales-leads.html) and the bookings list (admin.html).
(function(){
  var AREAS = ['Colaba','Fort','Churchgate','Marine Lines','Girgaon','Grant Road','Tardeo','Malabar Hill','Breach Candy','Peddar Road','Cuffe Parade','Nariman Point',
    'Mumbai Central','Byculla','Mazgaon','Parel','Lower Parel','Lalbaug','Worli','Prabhadevi','Dadar','Mahim','Matunga','Wadala','Sewri','Sion','Antop Hill',
    'Bandra','Khar','Santacruz','Juhu','Vile Parle','Ville Parle','Andheri','JVLR','Jogeshwari','Goregaon','Malad','Kandivali','Borivali','Dahisar','Mira Road','Bhayander',
    'Kurla','Chembur','Chemur','Ghatkopar','Vikhroli','Kanjurmarg','Bhandup','Mulund','Powai','Saki Naka','Marol','Chandivali','Govandi','Mankhurd','Deonar',
    'Thane','Kalwa','Airoli','Ghansoli','Vashi','Nerul','Belapur','Kharghar','Sanpada','Panvel','Seawoods','Navi Mumbai','Dombivli','Kalyan','Ulhasnagar','Ambernath',
    'Badlapur','Vasai','Nalasopara','Virar','Lokhandwala','Versova','Oshiwara','Pune'];
  var sorted = AREAS.slice().sort(function(a,b){ return b.length - a.length; });
  window.wsLocality = function(v){
    var t = String(v||'').trim(); if(!t) return '';
    var low = t.toLowerCase(), best = null, bestAt = -1, bestEnd = -1;
    sorted.forEach(function(a){
      var re = new RegExp('(^|[^a-z])' + a.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g,'\\$&') + '(?![a-z])', 'g'), m;
      while((m = re.exec(low))){ var at = m.index + m[1].length, end = at + a.length; if(end > bestEnd || (end === bestEnd && a.length > (best||'').length)){ bestEnd = end; bestAt = at; best = t.substr(at, a.length); } }
    });
    if(best){
      // keep a trailing (W)/(E)/West/East
      var rest = t.substr(bestAt + best.length).match(/^\s*(\((?:W|E)\)|West|East)/i);
      return best + (rest ? ' ' + rest[1].trim() : '');
    }
    var parts = t.split(',').map(function(x){ return x.trim(); }).filter(Boolean);
    return parts.length ? parts[parts.length-1] : '';
  };
})();
