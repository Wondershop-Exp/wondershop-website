// Event Volunteer section of the partner onboarding form (2026-10-10, per
// Shruti). Shown when "Event Volunteer" is picked. Exposes window.WSVolunteer:
//   toggle(on)      show / hide the section
//   validate()      -> {error, el} for the first problem, or {} when complete
//   appendTo(fd)    adds volunteer_profile (JSON) and the resume to the FormData
// The question lists live in js/volunteer-data.js (also used by admin.html).
(function () {
  var D = window.WS_VOLUNTEER;
  var host = document.getElementById('volunteerSection');
  if (!D || !host) return;
  var MAX_RESUME = 5 * 1024 * 1024;
  var thisYear = new Date().getFullYear();

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function chips(name, list) {
    return '<div class="vl-chips" data-group="' + name + '">' + list.map(function (o) {
      var v = typeof o === 'string' ? o : o.v, d = typeof o === 'string' ? '' : o.d;
      return '<label class="vl-chip"><input type="checkbox" name="' + name + '" value="' + esc(v) + '">' +
        '<span><b>' + esc(v) + '</b>' + (d ? '<small>' + esc(d) + '</small>' : '') + '</span></label>';
    }).join('') + '</div>';
  }
  function radios(name, list) {
    return '<div class="vl-radios">' + list.map(function (o) {
      return '<label class="vl-radio"><input type="radio" name="' + name + '" value="' + esc(o.v) + '"><span>' + esc(o.l) + '</span></label>';
    }).join('') + '</div>';
  }
  function fld(label, inner, id, hint) {
    return '<div class="fld"' + (id ? ' id="' + id + '"' : '') + '><label>' + label + '</label>' + inner +
      (hint ? '<div class="f-hint">' + hint + '</div>' : '') + '</div>';
  }
  var yearAttrs = ' type="text" inputmode="numeric" maxlength="4" placeholder="e.g. ' + (thisYear - 2) + '"';

  host.innerHTML =
    '<div class="sec-h">Volunteer Details</div>' +
    '<div class="sec-sub">A few questions so we can match you to the right events and roles.</div>' +
    fld('Date of Birth *', '<input type="date" id="v_dob" max="' + (thisYear - 14) + '-12-31">') +

    '<div class="vl-sub">School</div>' +
    fld('School Name *', '<input type="text" id="v_school_name" maxlength="150">') +
    '<div class="row2">' +
      fld('Marks (10th / 12th) *', '<input type="text" id="v_school_marks" maxlength="30" placeholder="e.g. 85% or A grade">') +
      fld('Year of Passing *', '<input' + yearAttrs + ' id="v_school_year">') +
    '</div>' +

    '<div class="vl-sub">College</div>' +
    fld('College status *', radios('v_college_status', D.collegeStatus)) +
    '<div id="v_college_box" hidden>' +
      fld('College Name *', '<input type="text" id="v_college_name" maxlength="150">') +
      fld('Course / Degree *', '<input type="text" id="v_college_course" maxlength="100" placeholder="e.g. B.Com, BMS, BFA">') +
      '<div class="row2">' +
        fld('Marks / CGPA <span class="opt" id="v_college_marks_opt">(so far, optional)</span>', '<input type="text" id="v_college_marks" maxlength="30" placeholder="e.g. 78% or 8.2 CGPA">') +
        fld('<span id="v_college_year_lbl">Year of Passing</span> *', '<input' + yearAttrs.replace(thisYear - 2, thisYear + 1) + ' id="v_college_year">') +
      '</div>' +
    '</div>' +

    '<div class="vl-sub">Experience</div>' +
    fld('Do you have past volunteering experience? *', radios('v_exp', [{ v: 'yes', l: 'Yes' }, { v: 'no', l: 'No' }])) +
    '<div id="v_exp_box" hidden>' +
      fld('What kind of events have you done? *', chips('v_event_types', D.eventTypes) +
        '<input type="text" id="v_event_types_other" class="vl-other" maxlength="200" placeholder="Others (type here)">') +
      fld('Briefly describe your most relevant experience (2-3 sentences) *', '<textarea id="v_exp_desc" maxlength="1200"></textarea>') +
    '</div>' +
    fld('Your skills *', chips('v_skills', D.skills) +
      '<input type="text" id="v_skills_other" class="vl-other" maxlength="200" placeholder="Others (type here)">', 'v_skills_fld',
      'Pick all that apply.') +

    '<div class="vl-sub">Roles</div>' +
    fld('Which responsibilities are you interested in? *', chips('v_resp', D.responsibilities), 'v_resp_fld', 'Pick all that apply.') +
    fld('On a scale of 1 to 5, how comfortable are you interacting with the public and answering general queries? *',
      '<div class="vl-scale">' + [1, 2, 3, 4, 5].map(function (n) {
        return '<label><input type="radio" name="v_comfort" value="' + n + '"><span>' + n + '</span></label>';
      }).join('') + '</div><div class="vl-scale-ends"><span>1 = not comfortable</span><span>5 = very comfortable</span></div>') +
    fld('Why do you want to volunteer for Wonderfest NGMA? *', '<textarea id="v_why" maxlength="1200"></textarea>') +
    fld('Would you be open to training and grooming for senior volunteering positions? *', radios('v_training', D.training)) +

    '<div class="vl-sub">Zones</div>' +
    fld('Which zones are you open to work in? *', '<div class="vl-zones">' + D.zones.map(function (z) {
      return '<label class="vl-zone"><input type="checkbox" name="v_zones" value="' + z.n + '">' +
        '<span><b>Zone ' + z.n + ' · ' + esc(z.en) + '</b><small>' + esc(z.areas) + '</small></span></label>';
    }).join('') + '</div>', 'v_zones_fld', 'Pick all that apply.') +

    '<div class="vl-sub">Resume</div>' +
    '<label class="upload-box" id="v_resume_box" for="v_resume">' +
      '<input type="file" id="v_resume" accept=".pdf,.doc,.docx,image/jpeg,image/png,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document">' +
      '<div class="ic">📎</div><div class="txt" id="v_resume_txt">Tap to upload your resume <span class="opt">(optional)</span></div>' +
    '</label>' +
    '<div class="upload-note">PDF, Word or a photo (JPG / PNG), up to 5MB.</div>' +

    '<div class="sec-h">Terms &amp; Conditions</div>' +
    '<ol class="vl-tnc">' + D.tnc.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ol>' +
    '<label class="vl-accept" id="v_tnc_lbl"><input type="checkbox" id="v_tnc"><span>' + esc(D.tncAccept) + ' *</span></label>';

  function $(id) { return document.getElementById(id); }
  function picked(name) {
    return Array.prototype.slice.call(host.querySelectorAll('input[name="' + name + '"]:checked')).map(function (i) { return i.value; });
  }
  function radio(name) { var r = host.querySelector('input[name="' + name + '"]:checked'); return r ? r.value : ''; }
  function val(id) { return ($(id).value || '').trim(); }

  function syncCollege() {
    var s = radio('v_college_status');
    $('v_college_box').hidden = !s || s === 'na';
    $('v_college_year_lbl').textContent = s === 'current' ? 'Expected Year of Passing' : 'Year of Passing';
    $('v_college_marks_opt').textContent = s === 'current' ? '(so far, optional)' : '';
    $('v_college_marks').closest('.fld').querySelector('label').lastChild.textContent = s === 'graduated' ? ' *' : '';
  }
  // The label for college marks ends with a text node we flip between '' and ' *'.
  $('v_college_marks').closest('.fld').querySelector('label').appendChild(document.createTextNode(''));
  host.addEventListener('change', function (e) {
    if (e.target.name === 'v_college_status') syncCollege();
    if (e.target.name === 'v_exp') $('v_exp_box').hidden = radio('v_exp') !== 'yes';
  });
  ['v_school_year', 'v_college_year'].forEach(function (id) {
    $(id).addEventListener('input', function () { var d = this.value.replace(/\D/g, '').slice(0, 4); if (d !== this.value) this.value = d; });
  });

  var resume = $('v_resume'), resumeTxt = $('v_resume_txt'), resumeBox = $('v_resume_box');
  resume.addEventListener('change', function () {
    var f = resume.files[0];
    resumeBox.style.borderColor = '';
    if (!f) { resumeTxt.innerHTML = 'Tap to upload your resume <span class="opt">(optional)</span>'; resumeTxt.className = 'txt'; return; }
    if (f.size > MAX_RESUME) {
      resumeTxt.textContent = 'That file is too large — please pick one under 5MB.';
      resumeBox.style.borderColor = 'var(--rd)'; resume.value = ''; return;
    }
    if (!/\.(pdf|docx?|jpe?g|png)$/i.test(f.name)) {
      resumeTxt.textContent = 'Please upload a PDF, Word file or a JPG / PNG photo.';
      resumeBox.style.borderColor = 'var(--rd)'; resume.value = ''; return;
    }
    resumeBox.style.borderColor = 'var(--gr)';
    resumeTxt.textContent = '✓ ' + f.name; resumeTxt.className = 'fname';
  });

  function yearOk(y, lo, hi) { return /^\d{4}$/.test(y) && +y >= lo && +y <= hi; }

  function collect() {
    var cs = radio('v_college_status'), exp = radio('v_exp');
    return {
      dob: val('v_dob'),
      school: { name: val('v_school_name'), marks: val('v_school_marks'), year: val('v_school_year') },
      college: cs && cs !== 'na'
        ? { status: cs, name: val('v_college_name'), course: val('v_college_course'), marks: val('v_college_marks'), year: val('v_college_year') }
        : { status: cs },
      has_experience: exp,
      event_types: exp === 'yes' ? picked('v_event_types') : [],
      event_types_other: exp === 'yes' ? val('v_event_types_other') : '',
      experience_desc: exp === 'yes' ? val('v_exp_desc') : '',
      skills: picked('v_skills'),
      skills_other: val('v_skills_other'),
      responsibilities: picked('v_resp'),
      public_comfort: +radio('v_comfort') || null,
      why_wonderfest: val('v_why'),
      open_to_training: radio('v_training'),
      zones: picked('v_zones').map(Number),
      tnc_version: D.tncVersion
    };
  }

  window.WSVolunteer = {
    toggle: function (on) { host.hidden = !on; },
    validate: function () {
      var p = collect();
      function bad(msg, el) { return { error: msg, el: el }; }
      if (!p.dob) return bad('Please enter your date of birth.', $('v_dob'));
      var age = (Date.now() - new Date(p.dob + 'T00:00:00')) / (365.25 * 864e5);
      if (!(age >= 14 && age <= 80)) return bad('Please check your date of birth.', $('v_dob'));
      if (!p.school.name) return bad('Please enter your school name.', $('v_school_name'));
      if (!p.school.marks) return bad('Please enter your school marks.', $('v_school_marks'));
      if (!yearOk(p.school.year, 1950, thisYear)) return bad('Please enter your school year of passing (e.g. ' + (thisYear - 2) + ').', $('v_school_year'));
      if (!p.college.status) return bad('Please tell us your college status.', host.querySelector('input[name="v_college_status"]'));
      if (p.college.status !== 'na') {
        if (!p.college.name) return bad('Please enter your college name.', $('v_college_name'));
        if (!p.college.course) return bad('Please enter your course or degree.', $('v_college_course'));
        if (p.college.status === 'graduated' && !p.college.marks) return bad('Please enter your college marks or CGPA.', $('v_college_marks'));
        var hi = p.college.status === 'current' ? thisYear + 6 : thisYear;
        if (!yearOk(p.college.year, 1950, hi)) return bad('Please enter your college ' + (p.college.status === 'current' ? 'expected ' : '') + 'year of passing.', $('v_college_year'));
      }
      if (!p.has_experience) return bad('Please tell us if you have past volunteering experience.', host.querySelector('input[name="v_exp"]'));
      if (p.has_experience === 'yes') {
        if (!p.event_types.length && !p.event_types_other) return bad('Please pick the kinds of events you have done.', $('v_exp_box'));
        if (p.experience_desc.length < 20) return bad('Please describe your most relevant experience in 2-3 sentences.', $('v_exp_desc'));
      }
      if (!p.skills.length && !p.skills_other) return bad('Please pick at least one skill.', $('v_skills_fld'));
      if (!p.responsibilities.length) return bad('Please pick at least one responsibility you are interested in.', $('v_resp_fld'));
      if (!p.public_comfort) return bad('Please rate how comfortable you are with the public (1 to 5).', host.querySelector('input[name="v_comfort"]'));
      if (p.why_wonderfest.length < 10) return bad('Please tell us why you want to volunteer for Wonderfest NGMA.', $('v_why'));
      if (!p.open_to_training) return bad('Please tell us if you are open to training for senior positions.', host.querySelector('input[name="v_training"]'));
      if (!p.zones.length) return bad('Please pick at least one zone you can work in.', $('v_zones_fld'));
      if (!$('v_tnc').checked) return bad('Please read and accept the terms and conditions.', $('v_tnc_lbl'));
      return {};
    },
    appendTo: function (fd) {
      fd.append('volunteer_profile', JSON.stringify(collect()));
      fd.append('volunteer_tnc_accepted', $('v_tnc').checked ? 'yes' : '');
      if (resume.files[0]) fd.append('resume', resume.files[0]);
    }
  };
})();
