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
  tncVersion: '2026-10-10-v2',
  tncIntro: 'Thank you for choosing to volunteer with Wondershop Experiences! These guidelines help us keep every event safe, happy and well run. Please read them carefully before you submit.',
  tnc: [
    { h: 'Punctuality and commitment', items: [
      'Please arrive at the reporting time shared with you. If you are running late or cannot make it, let the team know as early as possible.',
      'Once you confirm an event, the team counts on you. Arriving late, or not turning up after confirming, will lower your rating.'
    ] },
    { h: 'Dress and conduct', items: [
      'Please wear the dress code shared for the event, and come neat and well groomed.',
      'Speak to guests politely and confidently, and greet everyone with a smile.',
      'Stay calm and courteous throughout the event. Please never argue with the client, guests or children. If a situation becomes difficult, step away and call a senior team member.',
      'Please do not eat any food at the event unless the client offers it to you.'
    ] },
    { h: 'Children\'s safety', items: [
      'Please do not touch a child unless it is truly necessary, and always ask for permission before you do.',
      'Never leave children in your care unattended. Hand them over to a team member before you step away.',
      'Please do not take photos or videos of children on your personal phone, or post event photos on social media, without permission from the Wondershop Experiences team.',
      'If a child is hurt or unwell, or anything feels unsafe, tell a senior team member straight away.'
    ] },
    { h: 'During your duty', items: [
      'Please stay at your station and on your task until someone else has taken it over.',
      'Keep your phone away while on duty unless the event needs it, and always answer calls from the Wondershop Experiences team.',
      'If you are stuck or unsure about anything, please ask the senior team members present at the event for help.',
      'Take ownership of your role and be responsible for the guests, children and things in your care.'
    ] },
    { h: 'Training', items: [
      'During training, please ask questions about anything that is not clear. It is always better to ask than to guess.'
    ] },
    { h: 'Ratings, payment and policies', items: [
      'Every event is rated. Your ratings decide the future events you are offered and your pay.',
      'Payment is made within 7 working days of the event.',
      'If you are late, get into arguments, or do not follow company policies, Wondershop Experiences reserves the right to take action, including penalties, as it sees fit.'
    ] }
  ],
  tncOutro: 'Most of all, smile and enjoy the event. You are helping make a child\'s day special!',
  tncAccept: 'I have read and understood all the terms and conditions above, and I agree to follow them.'
};
