// Event Volunteer questions (2026-10-10, per Shruti). Shared by
// vendor-onboarding.html (the public partner form, when "Event Volunteer" is
// picked) and admin.html (Partners tab, volunteer profile). The 6 zones are
// the same Mumbai zones the decorator rate card uses (js/decor-rate-card-data.js).
window.WS_VOLUNTEER = {
  eventTypes: ['Tattoo', 'Art & craft', 'Kids parties / events', 'Music', 'Games', 'Dance',
    'Photography', 'Corporate events', 'Weddings', 'Exhibitions / fairs', 'Sports events'],
  skills: ['Tattoo', 'Hair grooming / braiding', 'Face painting', 'Art & craft', 'Slime making',
    'Nail art', 'Mehendi', 'Balloon modelling', 'Hosting / anchoring', 'Photography', 'Dance', 'Music'],
  responsibilities: [
    { v: 'Visitor Services', d: 'Registration desk, information booth, wayfinding' },
    { v: 'Child Management', d: '' },
    { v: 'Backstage', d: '' },
    { v: 'Technical Support', d: '' },
    { v: 'Photography / Social Media Support', d: '' },
    { v: 'Workshop / Activity Assistance', d: 'Helping the instructor set up activities, handling kids, etc.' },
    { v: 'Setup and Takedown Logistics', d: '' },
    { v: 'Crowd Management and Safety', d: '' },
    { v: 'Decor', d: '' },
    { v: 'Games', d: '' },
    { v: 'Hosting', d: '' }
  ],
  zones: [
    { n: 1, en: 'Central Suburbs', areas: 'Sion · Kurla · Chembur · Ghatkopar · Vikhroli · Bhandup · Mulund · Powai' },
    { n: 2, en: 'Western Suburbs', areas: 'Bandra · Khar · Santacruz · Juhu · Vile Parle · Andheri · Jogeshwari · Goregaon' },
    { n: 3, en: 'South & Central Mumbai', areas: 'Colaba · Fort · Byculla · Parel · Worli · Dadar · Matunga · Wadala' },
    { n: 4, en: 'Thane & Navi Mumbai', areas: 'Thane · Kalwa · Airoli · Ghansoli · Vashi · Nerul · Belapur · Kharghar' },
    { n: 5, en: 'Malad to Dahisar, Mira-Bhayander', areas: 'Malad · Kandivali · Borivali · Dahisar · Mira Road · Bhayander' },
    { n: 6, en: 'Far areas', areas: 'Dombivli · Kalyan · Ulhasnagar · Ambernath · Badlapur · Vasai · Nalasopara · Virar · Panvel' }
  ],
  collegeStatus: [
    { v: 'current', l: 'Currently studying' },
    { v: 'graduated', l: 'Graduated' },
    { v: 'na', l: 'Not in college' }
  ],
  training: [
    { v: 'yes', l: 'Yes' },
    { v: 'maybe', l: 'Maybe, I would like to know more' },
    { v: 'no', l: 'No' }
  ],
  // Bump the version whenever the wording below changes; the version a
  // volunteer accepted is saved with their profile.
  tncVersion: '2026-10-10',
  tnc: [
    'Report at the time given to you. Being late, or not turning up after confirming, lowers your rating.',
    'Wear the dress code shared for the event, and come neat and well groomed.',
    'Speak to guests politely and confidently.',
    'Do not use your phone during the event unless the event needs it. Always answer calls from Wondershop Experiences.',
    'Stay calm and polite through the event. Never argue with the client, guests or children.',
    'Every event is rated. Your rating decides the future events you are offered and your pay.',
    'Payment is made within 7 working days of the event.',
    'If you are late, argue with anyone, or do not follow company policies, Wondershop Experiences may apply a penalty as it sees fit.'
  ],
  tncAccept: 'I have read all the terms and conditions above and I agree to them.'
};
