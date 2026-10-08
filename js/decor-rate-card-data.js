// Decorator rate card - fixed content (2026-10-08, per Shruti).
// The 4 standard decors with what's included, the Mumbai transport zones with
// their pincodes, and the Hindi / Marathi lines shown under each English
// question. The website designs shown in each decor's gallery come from
// js/decor-rate-card-designs.js (generated - see that file).
window.WS_DECOR_DATA = {
  tiers: [
    { key: 'classic', label: 'Classic', title: 'Classic — Balloon Arch', hi: 'क्लासिक — बलून आर्च', mr: 'क्लासिक — फुग्यांची कमान',
      items: [
        { icon: 'arch', count: '× 1', en: 'Balloon arch, ~8 ft', hi: 'बलून आर्च', mr: 'फुग्यांची कमान' },
        { icon: 'balloon', count: '~120', en: '10" balloons, 3 colours', hi: 'बलून, 3 रंग', mr: 'फुगे, 3 रंग' },
        { icon: 'bunting', count: '× 1', en: 'Happy Birthday bunting', hi: 'हैप्पी बर्थडे बंटिंग', mr: 'हॅपी बर्थडे बंटिंग' },
        { icon: 'foil', count: '1 set', en: 'Age foil numbers, 32"', hi: 'उम्र के फ़ॉयल नंबर', mr: 'वयाचे फॉइल नंबर' }
      ] },
    { key: 'premium', label: 'Premium', title: 'Premium — 1 Panel', hi: 'प्रीमियम — 1 पैनल', mr: 'प्रीमियम — 1 पॅनल',
      items: [
        { icon: 'panel', count: '× 1', en: '5×7 ft flex — we give', hi: 'फ्लेक्स — हम देंगे', mr: 'फ्लेक्स — आम्ही देऊ', ours: true },
        { icon: 'stand', count: '× 1', en: 'Frame / stand — yours', hi: 'फ्रेम / स्टैंड — आपका', mr: 'फ्रेम / स्टँड — तुमचा' },
        { icon: 'garland', count: '~100', en: 'Balloon garland on panel', hi: 'पैनल पर बलून गारलैंड', mr: 'पॅनलवर फुग्यांची माळ' },
        { icon: 'foil', count: '1 set', en: 'Age foil numbers, 32"', hi: 'उम्र के फ़ॉयल नंबर', mr: 'वयाचे फॉइल नंबर' },
        { icon: 'bunch', count: '× 2', en: 'Floor balloon bunches', hi: 'फ़र्श पर बलून गुच्छे', mr: 'जमिनीवर फुग्यांचे गुच्छ' }
      ] },
    { key: 'luxury', label: 'Luxury', title: 'Luxury — 2 Panels', hi: 'लग्ज़री — 2 पैनल', mr: 'लक्झरी — 2 पॅनल',
      items: [
        { icon: 'panel', count: '× 2', en: 'Flex panels — we give', hi: 'फ्लेक्स — हम देंगे', mr: 'फ्लेक्स — आम्ही देऊ', ours: true },
        { icon: 'stand', count: '× 2', en: 'Frames / stands — yours', hi: 'फ्रेम / स्टैंड — आपका', mr: 'फ्रेम / स्टँड — तुमचा' },
        { icon: 'garland', count: '~180', en: 'Balloon garland on panels', hi: 'पैनल पर बलून गारलैंड', mr: 'पॅनलवर फुग्यांची माळ' },
        { icon: 'foil', count: '1 set', en: 'Age foil numbers, 32"', hi: 'उम्र के फ़ॉयल नंबर', mr: 'वयाचे फॉइल नंबर' },
        { icon: 'bunch', count: '× 4', en: 'Floor balloon bunches', hi: 'फ़र्श पर बलून गुच्छे', mr: 'जमिनीवर फुग्यांचे गुच्छ' }
      ] },
    { key: 'signature', label: 'Signature', title: 'Signature — 3 Panels', hi: 'सिग्नेचर — 3 पैनल', mr: 'सिग्नेचर — 3 पॅनल',
      items: [
        { icon: 'panel', count: '× 3', en: 'Flex panels — we give', hi: 'फ्लेक्स — हम देंगे', mr: 'फ्लेक्स — आम्ही देऊ', ours: true },
        { icon: 'stand', count: '× 3', en: 'Frames / stands — yours', hi: 'फ्रेम / स्टैंड — आपका', mr: 'फ्रेम / स्टँड — तुमचा' },
        { icon: 'garland', count: '~250', en: 'Balloon garland on panels', hi: 'पैनल पर बलून गारलैंड', mr: 'पॅनलवर फुग्यांची माळ' },
        { icon: 'foil', count: '1 set', en: 'Age foil numbers, 32"', hi: 'उम्र के फ़ॉयल नंबर', mr: 'वयाचे फॉइल नंबर' },
        { icon: 'bunch', count: '× 6', en: 'Floor balloon bunches', hi: 'फ़र्श पर बलून गुच्छे', mr: 'जमिनीवर फुग्यांचे गुच्छ' }
      ] }
  ],
  zones: [
    { n: 1, color: '#0F766E', en: 'Central Suburbs', hi: 'सेंट्रल सबर्ब्स', mr: 'मध्य उपनगरे',
      areas: 'Sion · Kurla · Chembur · Ghatkopar · Vikhroli · Bhandup · Mulund · Powai' },
    { n: 2, color: '#C2410C', en: 'Western Suburbs', hi: 'वेस्टर्न सबर्ब्स', mr: 'पश्चिम उपनगरे',
      areas: 'Bandra · Khar · Santacruz · Juhu · Vile Parle · Andheri · Jogeshwari · Goregaon' },
    { n: 3, color: '#6D28D9', en: 'South & Central Mumbai', hi: 'साउथ और सेंट्रल मुंबई', mr: 'दक्षिण व मध्य मुंबई',
      areas: 'Colaba · Fort · Byculla · Parel · Worli · Dadar · Matunga · Wadala' },
    { n: 4, color: '#2563EB', en: 'Thane & Navi Mumbai', hi: 'ठाणे और नवी मुंबई', mr: 'ठाणे व नवी मुंबई',
      areas: 'Thane · Kalwa · Airoli · Ghansoli · Vashi · Nerul · Belapur · Kharghar' },
    { n: 5, color: '#A16207', en: 'Malad to Dahisar, Mira-Bhayander', hi: 'मलाड से दहिसर, मीरा-भायंदर', mr: 'मालाड ते दहिसर, मीरा-भाईंदर',
      areas: 'Malad · Kandivali · Borivali · Dahisar · Mira Road · Bhayander' },
    { n: 6, color: '#6B6158', en: 'Far areas', hi: 'दूर के एरिया', mr: 'लांबचे भाग',
      areas: 'Dombivli · Kalyan · Ulhasnagar · Ambernath · Badlapur · Vasai · Nalasopara · Virar · Panvel' }
  ],
  // pincode -> area name, per zone (draft map of 2026-10-07; zone choices for
  // border pincodes and serviceability still to be confirmed by Shruti)
  zonePins: {"3": [["400001", "Fort / CST / Ballard Estate"], ["400002", "Kalbadevi"], ["400003", "Mandvi / Masjid Bunder"], ["400004", "Girgaon / Charni Road"], ["400005", "Colaba"], ["400006", "Malabar Hill"], ["400007", "Grant Road / Tardeo"], ["400008", "Mumbai Central / Nagpada"], ["400009", "Dongri / Chinchbunder"], ["400010", "Mazgaon"], ["400011", "Jacob Circle / Chinchpokli"], ["400012", "Parel / Lalbaug"], ["400013", "Lower Parel (Delisle Road)"], ["400014", "Dadar East / Naigaon"], ["400015", "Sewri"], ["400016", "Mahim"], ["400017", "Dharavi"], ["400018", "Worli"], ["400019", "Matunga"], ["400020", "Churchgate / Marine Lines"], ["400021", "Nariman Point"], ["400025", "Prabhadevi"], ["400026", "Peddar Road / Gowalia Tank"], ["400027", "Byculla East (Rani Baug)"], ["400028", "Dadar West / Shivaji Park"], ["400030", "Worli Sea Face"], ["400031", "Wadala"], ["400032", "Mantralaya"], ["400033", "Cotton Green / Kalachowki"], ["400034", "Haji Ali / Tulsiwadi"], ["400035", "Raj Bhavan, Malabar Hill"], ["400037", "Antop Hill / Wadala Truck Terminal"]], "1": [["400022", "Sion / Chunabhatti"], ["400024", "Nehru Nagar, Kurla East"], ["400042", "Bhandup East"], ["400043", "Shivaji Nagar, Govandi"], ["400070", "Kurla West"], ["400071", "Chembur"], ["400072", "Sakinaka / Chandivali"], ["400074", "Chembur East / Mahul"], ["400075", "Pant Nagar, Ghatkopar East"], ["400076", "Powai"], ["400077", "Rajawadi, Ghatkopar East"], ["400078", "Bhandup West"], ["400079", "Vikhroli"], ["400080", "Mulund West"], ["400081", "Mulund East"], ["400082", "Mulund Colony / Bhandup Complex"], ["400083", "Vikhroli East – Kannamwar / Tagore Nagar"], ["400084", "Barve Nagar, Ghatkopar West"], ["400085", "BARC, Trombay"], ["400086", "Ghatkopar West"], ["400087", "NITIE / Vihar Lake, Powai"], ["400088", "Govandi / Mankhurd / Trombay"], ["400089", "Tilak Nagar, Chembur"], ["400094", "Anushakti Nagar"]], "2": [["400029", "Kalina – Air India Colony, Santacruz East"], ["400049", "Juhu"], ["400050", "Bandra West"], ["400051", "Bandra East / Kherwadi"], ["400052", "Khar"], ["400053", "Andheri West (Azad Nagar)"], ["400054", "Santacruz West"], ["400055", "Santacruz East / Vakola"], ["400056", "Vile Parle West"], ["400057", "Vile Parle East"], ["400058", "Andheri West (Station)"], ["400059", "Marol / J.B. Nagar, Andheri East"], ["400060", "Jogeshwari East"], ["400061", "Versova / Madh"], ["400063", "Goregaon East"], ["400065", "Aarey Colony"], ["400069", "Andheri East"], ["400093", "Chakala / MIDC, Andheri East"], ["400096", "SEEPZ, Andheri East"], ["400098", "Vidyanagari / Kalina"], ["400099", "Airport / Sahar"], ["400102", "Jogeshwari West / Oshiwara"], ["400104", "Goregaon West"]], "5": [["400064", "Malad West"], ["400066", "Borivali East"], ["400067", "Kandivali West / Charkop"], ["400068", "Dahisar"], ["400091", "Borivali"], ["400092", "Borivali West"], ["400095", "Kharodi / INS Hamla, Malad West"], ["400097", "Malad East"], ["400101", "Kandivali East"], ["400103", "Mandapeshwar, Borivali West"], ["401101", "Bhayander West"], ["401105", "Bhayander East"], ["401107", "Mira Road"]], "4": [["400601", "Thane West (Station area)"], ["400602", "Naupada, Thane West"], ["400603", "Thane East / Kopri"], ["400604", "Wagle Estate, Thane"], ["400605", "Kalwa"], ["400606", "Jekegram / Pokhran, Thane"], ["400607", "Manpada, Ghodbunder Road"], ["400608", "Balkum, Thane"], ["400610", "Thane West (Apna Bazar PO)"], ["400614", "CBD Belapur"], ["400615", "Kasarvadavali, Ghodbunder Road"], ["400701", "Ghansoli"], ["400703", "Vashi / Turbhe"], ["400705", "Sanpada"], ["400706", "Nerul"], ["400708", "Airoli"], ["400709", "Kopar Khairane"], ["400710", "Mahape (Millennium Business Park)"], ["410210", "Kharghar"]], "6": [["400612", "Mumbra / Diva"], ["401201", "Vasai West"], ["401202", "Vasai Road East"], ["401203", "Nalasopara (Sopara)"], ["401207", "Naigaon"], ["401208", "Vasai East (industrial)"], ["401209", "Nalasopara East"], ["401303", "Virar West"], ["401305", "Virar East"], ["410206", "Panvel / New Panvel / Kamothe"], ["410208", "Taloja"], ["410216", "Jagdish Nagar PO (Panvel area)"], ["410218", "Kalamboli"], ["421001", "Ulhasnagar 1"], ["421002", "Ulhasnagar 2–3"], ["421004", "Ulhasnagar 4"], ["421005", "Ulhasnagar 5"], ["421201", "Dombivli East (Ramnagar / Thakurli)"], ["421202", "Dombivli West (Vishnunagar)"], ["421203", "Dombivli MIDC"], ["421204", "Manpada / Nilje, Dombivli East"], ["421301", "Kalyan West"], ["421305", "Vidyashram (Kalyan–Bhiwandi side)"], ["421306", "Kalyan East"], ["421308", "Bhiwandi"], ["421501", "Ambernath"], ["421502", "Ambernath (Ordnance Estate)"], ["421503", "Badlapur (Kulgaon)"], ["421505", "Badlapur / Ambernath (Netaji Bazar PO)"]]},
  t: {
    callout:   { hi: 'आपने डेकोरेटर चुना है। नीचे डेकोर रेट कार्ड जोड़ा गया है — लगभग 10 मिनट और।', mr: 'तुम्ही डेकोरेटर निवडले आहे. खाली डेकोर दरपत्रक जोडले आहे — अजून सुमारे 10 मिनिटे.' },
    title:     { hi: 'डेकोर रेट कार्ड', mr: 'डेकोर दरपत्रक' },
    intro:     { hi: 'हर सवाल का जवाब बस एक नंबर। जो लागू न हो, वो खाली छोड़ दें।', mr: 'प्रत्येक प्रश्नाचे उत्तर फक्त एक आकडा. जे लागू नसेल ते रिकामे सोडा.' },
    about:     { hi: 'आपके डेकोर काम के बारे में', mr: 'तुमच्या डेकोर व्यवसायाबद्दल' },
    years:     { hi: 'कितने साल से डेकोरेशन कर रहे हैं?', mr: 'डेकोरेशनचा किती वर्षांचा अनुभव आहे?' },
    team:      { hi: 'टीम में कितने लोग हैं?', mr: 'टीममध्ये किती लोक आहेत?' },
    perday:    { hi: 'एक दिन में कितने डेकोर कर सकते हैं?', mr: 'एका दिवसात किती डेकोर करू शकता?' },
    insta:     { hi: 'Instagram / Google पेज का लिंक', mr: 'Instagram / Google पेजची लिंक' },
    howto:     { hi: 'रेट कैसे बताना है', mr: 'दर कसा सांगायचा' },
    howto_p:   { hi: 'हर डेकोर का रेट नॉर्मल बलून के हिसाब से बताएं। पेस्टल और क्रोम का एक्स्ट्रा अलग पूछेंगे।', mr: 'प्रत्येक डेकोरचा दर साध्या फुग्यांनुसार सांगा. पेस्टल आणि क्रोमचा जादा दर वेगळा विचारू.' },
    b_normal:  { hi: 'नॉर्मल', mr: 'साधे' },
    b_pastel:  { hi: 'पेस्टल', mr: 'पेस्टल' },
    b_chrome:  { hi: 'क्रोम', mr: 'क्रोम' },
    incl:      { hi: 'आपके रेट में शामिल है', mr: 'तुमच्या दरात समाविष्ट' },
    incl1:     { hi: 'सामान, फ्रेम / स्टैंड, लगाना और बाद में उतारना', mr: 'साहित्य, फ्रेम / स्टँड, लावणे आणि नंतर काढणे' },
    incl2:     { hi: 'फ्लेक्स हम छपवाकर देंगे — आपको बस लगाना है', mr: 'फ्लेक्स आम्ही छापून देऊ — तुम्हाला फक्त लावायचा आहे' },
    incl3:     { hi: 'ट्रांसपोर्ट अलग पूछेंगे', mr: 'वाहतूक खर्च वेगळा विचारू' },
    doyou:     { hi: 'क्या आप यह डेकोर करते हैं?', mr: 'तुम्ही हे डेकोर करता का?' },
    yes:       { hi: 'हाँ', mr: 'होय' },
    no:        { hi: 'नहीं', mr: 'नाही' },
    skip:      { hi: 'ठीक है — यह डेकोर आपको नहीं भेजेंगे। अगले पर जाएं।', mr: 'ठीक आहे — हे डेकोर तुम्हाला पाठवणार नाही. पुढच्यावर जा.' },
    included:  { hi: 'इसमें क्या-क्या है', mr: 'यात काय काय आहे' },
    rate:      { hi: 'इस डेकोर का आपका रेट', mr: 'या डेकोरचा तुमचा दर' },
    gal_q:     { hi: 'क्या यही रेट इन सभी डेकोर पर लागू होगा?', mr: 'हाच दर या सर्व डेकोरला लागू आहे का?' },
    gal_p:     { hi: 'हर फ़ोटो के नीचे चुनें: वही रेट · अलग रेट · नहीं कर सकते', mr: 'प्रत्येक फोटोखाली निवडा: तोच दर · वेगळा दर · करू शकत नाही' },
    gal_note:  { hi: 'ये फ़ोटो सिर्फ़ रेट बताने के लिए हैं। कृपया शेयर न करें।', mr: 'हे फोटो फक्त दर सांगण्यासाठी आहेत. कृपया शेअर करू नका.' },
    gal_wait:  { hi: 'ऊपर रेट लिखें, फिर सारे डिज़ाइन दिखेंगे।', mr: 'वर दर लिहा, मग सर्व डिझाइन दिसतील.' },
    pastel:    { hi: 'पेस्टल बलून हो तो एक्स्ट्रा', mr: 'पेस्टल फुगे असल्यास जादा' },
    chrome:    { hi: 'क्रोम बलून हो तो एक्स्ट्रा', mr: 'क्रोम फुगे असल्यास जादा' },
    setup:     { hi: 'लगाने में कितना समय लगता है?', mr: 'लावायला किती वेळ लागतो?' },
    remarks:   { hi: 'कुछ कहना है? (ज़रूरी नहीं)', mr: 'काही सांगायचे आहे? (ऐच्छिक)' },
    mic:       { hi: 'कीबोर्ड का माइक दबाकर बोलकर भी लिख सकते हैं', mr: 'कीबोर्डवरचा माइक दाबून बोलूनही लिहू शकता' },
    transport: { hi: 'ट्रांसपोर्ट', mr: 'वाहतूक' },
    tr_p:      { hi: 'हर एरिया में जाने-आने का एक फ़िक्स रेट — हर डेकोर के लिए यही।', mr: 'प्रत्येक भागात जाण्या-येण्याचा एक ठरलेला दर — प्रत्येक डेकोरसाठी हाच.' },
    tr_flex:   { hi: 'इसमें हमारे ऑफ़िस से फ्लेक्स उठाना भी शामिल है।', mr: 'यात आमच्या ऑफिसमधून फ्लेक्स घेणेही समाविष्ट आहे.' },
    map_h:     { hi: 'ज़ोन कहाँ हैं?', mr: 'झोन कुठे आहेत?' },
    map_note:  { hi: 'यह सिर्फ़ अंदाज़े का नक्शा है। ज़ोन पर टैप करें।', mr: 'हा फक्त अंदाजे नकाशा आहे. झोनवर टॅप करा.' },
    dontgo_p:  { hi: 'जहाँ नहीं जाते, वहाँ “Don\'t go” दबाएं।', mr: 'जिथे जात नाही, तिथे “Don\'t go” दाबा.' },
    flex_h:    { hi: 'फ्लेक्स और बुकिंग', mr: 'फ्लेक्स आणि बुकिंग' },
    flex_q:    { hi: 'हमारे ऑफ़िस से फ्लेक्स उठा सकते हैं?', mr: 'आमच्या ऑफिसमधून फ्लेक्स घेऊ शकता का?' },
    notice_q:  { hi: 'कितने दिन पहले बुकिंग चाहिए?', mr: 'बुकिंग किती दिवस आधी हवी?' },
    photos_h:  { hi: 'आपके काम की फ़ोटो', mr: 'तुमच्या कामाचे फोटो' },
    photos_q:  { hi: 'आपके काम की 3–5 फ़ोटो डालें', mr: 'तुमच्या कामाचे 3–5 फोटो टाका' },
    summary_h: { hi: 'आपका रेट कार्ड — भेजने से पहले एक बार चेक करें', mr: 'तुमचे दरपत्रक — पाठवण्यापूर्वी एकदा तपासा' },
    fixed:     { hi: 'ये रेट 6 महीने तक फ़िक्स रहेंगे।', mr: 'हे दर 6 महिने ठरलेले राहतील.' },
    confirm:   { hi: 'मैंने रेट चेक कर लिए, ये फ़ाइनल हैं', mr: 'मी दर तपासले, हे अंतिम आहेत' }
  }
};
