/* Wondershop training — shared voice + WhatsApp helpers (2026-11-12).
   Used by training.html and every training-*.html page.

   1. LISTEN  — reads text aloud with the phone/computer's built-in voice
                (prefers an Indian English voice). No internet service needed.
   2. RECORD  — you read the steps in your own voice; the page saves it as an
                audio file you can share straight to WhatsApp as a voice note.
   3. AUDIO   — if a ready audio file exists (data-audio="audio/xyz.m4a" on
                <body>), "Share voice note" sends that file instead.
   4. SHARE   — sends the written steps + page link on WhatsApp.
*/
(function(){
  const synth = window.speechSynthesis;
  let voice = null, rate = 1, queue = [], speaking = false, activeBtn = null;

  function pickVoice(){
    if(!synth) return;
    const v = synth.getVoices();
    voice = v.find(x=>/en[-_]IN/i.test(x.lang)) ||
            v.find(x=>/India/i.test(x.name)) ||
            v.find(x=>/^en/i.test(x.lang)) || v[0] || null;
  }
  if(synth){ pickVoice(); synth.onvoiceschanged = pickVoice; }

  function clean(t){ return (t||'').replace(/\s+/g,' ').trim(); }

  function stop(){
    queue = []; speaking = false;
    if(synth) synth.cancel();
    if(activeBtn){ activeBtn.classList.remove('on'); activeBtn.setAttribute('aria-pressed','false'); activeBtn = null; }
    document.querySelectorAll('.speaking').forEach(e=>e.classList.remove('speaking'));
  }

  function next(){
    if(!queue.length){ stop(); return; }
    const item = queue.shift();
    document.querySelectorAll('.speaking').forEach(e=>e.classList.remove('speaking'));
    if(item.el){ item.el.classList.add('speaking'); item.el.scrollIntoView({behavior:'smooth',block:'center'}); }
    const u = new SpeechSynthesisUtterance(item.text);
    if(voice) u.voice = voice;
    u.lang = voice ? voice.lang : 'en-IN';
    u.rate = rate;
    u.onend = next; u.onerror = next;
    synth.speak(u);
  }

  /* items: [{text, el}] */
  function play(items, btn){
    if(!synth){ alertBox('Your browser cannot read aloud. Try Chrome or Safari.'); return; }
    const same = activeBtn === btn && speaking;
    stop();
    if(same) return;                       // second tap = stop
    queue = items.filter(i=>clean(i.text)).map(i=>({text:clean(i.text), el:i.el}));
    speaking = true; activeBtn = btn;
    if(btn){ btn.classList.add('on'); btn.setAttribute('aria-pressed','true'); }
    next();
  }

  function alertBox(msg){
    let t = document.getElementById('tvToast');
    if(!t){ t = document.createElement('div'); t.id='tvToast'; t.className='tv-toast'; document.body.appendChild(t); }
    t.textContent = msg; t.classList.add('show');
    clearTimeout(t._h); t._h = setTimeout(()=>t.classList.remove('show'), 3500);
  }

  /* ---------- WhatsApp ---------- */
  function shareText(title, text){
    const url = location.href.split('#')[0];
    const msg = '*' + title + '*\n\n' + text + '\n\nFull guide: ' + url;
    window.open('https://wa.me/?text=' + encodeURIComponent(msg), '_blank');
  }

  async function shareFile(blob, name, title){
    const file = new File([blob], name, {type: blob.type || 'audio/mp4'});
    if(navigator.canShare && navigator.canShare({files:[file]})){
      try{ await navigator.share({files:[file], title:title}); return true; }
      catch(e){ if(e.name === 'AbortError') return true; }
    }
    // Desktop fallback: download it, then attach in WhatsApp Web.
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    alertBox('Audio saved. Attach it in WhatsApp to send as a voice note.');
    return false;
  }

  /* ---------- Recorder (your own voice) ---------- */
  let rec = null, chunks = [], lastBlob = null;
  async function toggleRecord(btn, onDone){
    if(rec && rec.state === 'recording'){ rec.stop(); return; }
    if(!navigator.mediaDevices || !window.MediaRecorder){ alertBox('Recording is not supported on this browser.'); return; }
    let stream;
    try{ stream = await navigator.mediaDevices.getUserMedia({audio:true}); }
    catch(e){ alertBox('Please allow microphone access to record.'); return; }
    const type = ['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg'].find(t=>MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
    rec = new MediaRecorder(stream, type ? {mimeType:type} : undefined);
    chunks = [];
    rec.ondataavailable = e => { if(e.data.size) chunks.push(e.data); };
    rec.onstop = () => {
      stream.getTracks().forEach(t=>t.stop());
      lastBlob = new Blob(chunks, {type: rec.mimeType || 'audio/mp4'});
      btn.classList.remove('rec'); btn.querySelector('span').textContent = 'Record again';
      onDone && onDone(lastBlob);
    };
    rec.start();
    btn.classList.add('rec'); btn.querySelector('span').textContent = 'Stop recording';
  }
  function ext(b){ return /webm/.test(b.type) ? 'webm' : /ogg/.test(b.type) ? 'ogg' : 'm4a'; }

  window.TrainingVoice = { play, stop, shareText, shareFile, toggleRecord, ext, toast: alertBox,
    setRate(r){ rate = r; }, supported: !!synth };
})();
