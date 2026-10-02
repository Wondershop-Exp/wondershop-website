/* Wondershop Return Gifts catalogue — ONE shared source (2026-10-02, per Shruti).
 *
 * Used by builder.html (Build-a-Birthday's Return Gifts step) AND the package
 * pages (unicorn-basic / turf-basic / spy-basic), so adding, repricing or
 * retiring a gift here updates every page at once.
 *
 * Fields: id, n (name), img (under img/), gallery, e (emoji fallback),
 * type (bags | games | personalized | stationery | home), gtheme (theme filter,
 * a string or an array), age, unit (selling price per piece), bg, tag,
 * hidden:true (retired — kept so old bookings still resolve, never offered),
 * pkgs: package pages that RECOMMEND this gift by default
 *       ('unicorn-basic', 'spy-basic', 'turf-basic'). Tag a new gift with the
 *       relevant package(s) and it shows up there automatically; untagged
 *       gifts are still available on every package page via "View all
 *       return gifts".
 *
 * Every return gift is a vendor item: subject to stock availability, billed
 * separately from the event, and paid 100% in advance via a payment link once
 * the team confirms stock (see WS_GIFT_STOCK_NOTE). Mirrored server-side in
 * backend/catalogue_data.py GIFTS — keep prices in step.
 */
(function(){
const WS_TSHIRT_INFO="<h4>👕 What is the t-shirt quality?</h4><ul><li>100% cotton t-shirts.</li></ul><h4>🎨 Can it be customised to the theme?</h4><ul><li>Yes — we print both <b>names</b> and <b>designs</b>.</li><li>Designs are chosen from our pre-decided theme designs; your child's (or each guest's) name can be printed along with it.</li></ul><div class=\"gal-info-note\">Our Party Experience Lead will share the design options for your theme before the party.</div>";
window.WS_TSHIRT_INFO=WS_TSHIRT_INFO;
const TSHIRT_INFO=WS_TSHIRT_INFO;
window.WS_GIFTS=[
  {id:'g1',hidden:true,n:'3D Printed Personalized FIFA World Cup',img:'return-gifts/fifa-world-cup-3d.jpg',e:'⚽',type:'personalized',gtheme:'generic',age:'5-12',unit:850,bg:'#F0F7FF',tag:''},
  {id:'g2',n:'900ml Tumbler',img:'return-gifts/tumbler-900ml.jpg',e:'🥤',type:'home',gtheme:'generic',age:'3-12',unit:750,bg:'#F0FDF4',tag:''},
  {id:'g3',pkgs:['unicorn-basic'],n:'Baby Frost Pouch',img:'return-gifts/baby-frost-pouch.jpg',e:'👝',type:'bags',gtheme:'generic',age:'3-12',unit:245,bg:'#FFF0F7',tag:''},
  {id:'g4',n:'Codenames (Board Game)',img:'return-gifts/board-game-codenames.jpg',e:'🎲',type:'games',gtheme:'generic',age:'10-14',unit:475,bg:'#FFFBDC',tag:''},
  {id:'g5',n:'Neon Chest Bag',img:'return-gifts/chest-bag-neon.jpg',e:'🎒',type:'bags',gtheme:'generic',age:'5-12',unit:275,bg:'#FFF0F7',tag:''},
  {id:'g6',n:'Foam Duffle Bag',img:'return-gifts/foam-duffle-bag.jpg',e:'🎒',type:'bags',gtheme:'generic',age:'3-12',unit:300,bg:'#FFF0F7',tag:''},
  {id:'g7',pkgs:['unicorn-basic'],n:'Jelly Tote Bag',img:'return-gifts/jelly-tote-bag.jpg',e:'👜',type:'bags',gtheme:'generic',age:'3-12',unit:500,bg:'#FFF0F7',tag:''},
  {id:'g8',pkgs:['unicorn-basic'],n:'Jewellery Organizer with Initial',img:'return-gifts/jewellery-organizer-initial.jpg',e:'💍',type:'personalized',gtheme:'generic',age:'5-12',unit:500,bg:'#F0F7FF',tag:''},
  {id:'g9',hidden:true,n:'Kids Travel Trolley',img:'return-gifts/kids-travel-trolley.jpg',e:'🧳',type:'home',gtheme:'generic',age:'3-10',unit:1200,bg:'#F0FDF4',tag:''},
  {id:'g10',hidden:true,n:'LCD Compass Box with Calculator',img:'return-gifts/lcd-compass-calculator.jpg',e:'📐',type:'stationery',gtheme:'generic',age:'6-14',unit:210,bg:'#FFFBDC',tag:''},
  {id:'g11',n:'Mafia (Board Game)',img:'return-gifts/board-game-mafia.jpg',e:'🎲',type:'games',gtheme:'generic',age:'10-14',unit:300,bg:'#FFFBDC',tag:''},
  {id:'g12',hidden:true,n:'Magic Water Painting Book',img:'return-gifts/magic-water-painting-book.jpg',e:'🎨',type:'stationery',gtheme:'generic',age:'3-8',unit:375,bg:'#FFFBDC',tag:''},
  {id:'g13',hidden:true,n:'Neon Bag with Double Packet',img:'return-gifts/neon-bag-double-packet.jpg',e:'🎒',type:'bags',gtheme:'generic',age:'3-12',unit:400,bg:'#FFF0F7',tag:''},
  {id:'g14',n:'Neon Duffle Bag',img:'return-gifts/neon-duffle-bag.jpg',e:'🎒',type:'bags',gtheme:'generic',age:'3-12',unit:350,bg:'#FFF0F7',tag:''},
  {id:'g15',hidden:true,n:'Personalized Drawstring Pouch',img:'return-gifts/personalized-drawstring-pouch.jpg',e:'👝',type:'bags',gtheme:'generic',age:'3-12',unit:500,bg:'#FFF0F7',tag:''},
  {id:'g16',hidden:true,n:'Personalized Drawstring Bag & Pouch Combo',img:'return-gifts/personalized-drawstring-combo.jpg',e:'🎒',type:'bags',gtheme:'generic',age:'3-12',unit:750,bg:'#FFF0F7',tag:''},
  {id:'g17',hidden:true,n:'Personalized Duffle Bag',img:'return-gifts/personalized-duffle-bag.jpg',e:'🎒',type:'bags',gtheme:'generic',age:'3-12',unit:650,bg:'#FFF0F7',tag:''},
  {id:'g18',pkgs:['turf-basic'],n:'Personalized Football',img:'return-gifts/personalized-football-1.jpg',gallery:[{type:'img',src:'img/return-gifts/personalized-football-1.jpg'},{type:'img',src:'img/return-gifts/personalized-football-2.jpg'}],e:'⚽',type:'personalized',gtheme:'generic',age:'5-12',unit:600,bg:'#F0F7FF',tag:''},
  {id:'g19',hidden:true,n:'Personalized Pouch',img:'return-gifts/personalized-pouch.jpg',e:'👝',type:'bags',gtheme:'generic',age:'3-12',unit:325,bg:'#FFF0F7',tag:''},
  {id:'g20',n:'Space Rocket Piggy Bank with Password',img:'return-gifts/space-rocket-piggy-bank.jpg',e:'🚀',type:'personalized',gtheme:'space',age:'3-10',unit:410,bg:'#F0F7FF',tag:''},
  {id:'g21',hidden:true,n:'Theme Based Penstand',img:'return-gifts/theme-penstand.jpg',e:'✏️',type:'stationery',gtheme:'generic',age:'5-12',unit:450,bg:'#FFFBDC',tag:''},
  {id:'g22',n:'Toy Storage Box',img:'return-gifts/toy-storage-box.jpg',e:'📦',type:'home',gtheme:'generic',age:'3-10',unit:375,bg:'#F0FDF4',tag:''},
  {id:'g23',hidden:true,n:'Train Night Lamp',img:'return-gifts/train-night-lamp.jpg',e:'🚂',type:'home',gtheme:'generic',age:'3-8',unit:300,bg:'#F0FDF4',tag:''},
  {id:'g24',n:'5 Pcs Steel Straw Set',img:'return-gifts/steel-straw-set.jpg',e:'🥤',type:'home',gtheme:'generic',age:'3-12',unit:190,bg:'#F0FDF4',tag:''},
  {id:'g25',pkgs:['spy-basic', 'turf-basic'],n:'Personalized Cap',img:'return-gifts/personalized-cap.png',e:'🧢',type:'personalized',gtheme:'generic',age:'3-12',unit:500,bg:'#F0F7FF',tag:''},
  {id:'g26',pkgs:['unicorn-basic', 'spy-basic', 'turf-basic'],n:'Live T-shirt Printing',img:'return-gifts/live-tshirt-printing.png',info:TSHIRT_INFO,gallery:[{type:'img',src:'img/return-gifts/live-tshirt-printing.png'},{type:'video',src:'img/return-gifts/live-tshirt-video.mp4'}],e:'👕',type:'personalized',gtheme:'generic',age:'5-14',unit:550,bg:'#F0F7FF',tag:''},
  // Added 2026-10-02, per Shruti. Priced per piece.
  {id:'g27',n:'Squishy Dumpling',img:'return-gifts/squishy-dumpling-plain-1.jpg',gallery:[{type:'img',src:'img/return-gifts/squishy-dumpling-plain-1.jpg'},{type:'img',src:'img/return-gifts/squishy-dumpling-plain-2.jpg'},{type:'img',src:'img/return-gifts/squishy-dumpling-plain-3.jpg'},{type:'img',src:'img/return-gifts/squishy-dumpling-plain-4.jpg'},{type:'img',src:'img/return-gifts/squishy-dumpling-plain-5.jpg'}],e:'🥟',type:'games',gtheme:'generic',age:'3-12',unit:199,bg:'#FFF0F7',tag:''},
  {id:'g28',n:'Bath Bomb',img:'return-gifts/bath-bombs-small.jpg',gallery:[{type:'img',src:'img/return-gifts/bath-bombs-small.jpg'},{type:'img',src:'img/return-gifts/bath-bombs-small-1.jpg'},{type:'img',src:'img/return-gifts/bath-bombs-small-2.jpg'}],e:'🛁',type:'home',gtheme:'generic',age:'3-12',unit:85,bg:'#F0FDF4',tag:''},
  // Harry Potter & K-pop range, added 2026-10-02 per Shruti. gtheme may be an
  // array for items sold in both designs (see renderGifts theme check).
  {id:'g29',n:'Insulated Steel Lunch Box',img:'return-gifts/hp-kpop-steel-lunch-box.jpg',e:'🍱',type:'home',gtheme:['hp','kpop'],age:'5-14',unit:546,bg:'#F0FDF4',tag:''},
  {id:'g30',n:'Steel Mug',img:'return-gifts/hp-kpop-steel-mug.jpg',e:'☕',type:'home',gtheme:['hp','kpop'],age:'5-14',unit:440,bg:'#F0FDF4',tag:''},
  {id:'g31',n:'Insulated Steel Flask (approx. 260 ml)',img:'return-gifts/hp-kpop-steel-flask-260ml.jpg',e:'🧴',type:'home',gtheme:['hp','kpop'],age:'5-14',unit:580,bg:'#F0FDF4',tag:''},
  {id:'g32',n:'Harry Potter Bluetooth Headphones',img:'return-gifts/hp-bluetooth-headphones.jpg',e:'🎧',type:'home',gtheme:'hp',age:'7-14',unit:700,bg:'#F0FDF4',tag:''},
  {id:'g33',n:'K-pop Bluetooth Headphones',img:'return-gifts/kpop-bluetooth-headphones.jpg',e:'🎧',type:'home',gtheme:'kpop',age:'8-14',unit:700,bg:'#F0FDF4',tag:''},
  {id:'g34',n:'LED Alarm Clock',img:'return-gifts/hp-kpop-led-alarm-clock.jpg',e:'⏰',type:'home',gtheme:['hp','kpop'],age:'5-14',unit:420,bg:'#F0FDF4',tag:''},
  {id:'g35',n:'Harry Potter Karaoke Speaker Set',img:'return-gifts/hp-karaoke-speaker-set.jpg',e:'🎤',type:'games',gtheme:'hp',age:'7-14',unit:600,bg:'#FFF0F7',tag:''},
  {id:'g36',n:'K-pop Chest Bag (Leather Finish)',img:'return-gifts/kpop-chest-bag.jpg',e:'👜',type:'bags',gtheme:'kpop',age:'8-14',unit:380,bg:'#FFF0F7',tag:''},
  {id:'g37',n:'Harry Potter Chest Bag (Leather Finish)',img:'return-gifts/hp-chest-bag.jpg',e:'👜',type:'bags',gtheme:'hp',age:'7-14',unit:380,bg:'#FFF0F7',tag:''},
  {id:'g38',n:'Harry Potter Backpack (Leather Finish)',img:'return-gifts/hp-backpack.jpg',e:'🎒',type:'bags',gtheme:'hp',age:'7-14',unit:570,bg:'#FFF0F7',tag:''},
  {id:'g39',n:'K-pop Backpack (Leather Finish)',img:'return-gifts/kpop-backpack.jpg',e:'🎒',type:'bags',gtheme:'kpop',age:'8-14',unit:570,bg:'#FFF0F7',tag:''},
  {id:'g40',n:'Harry Potter A4 Folder (4 designs)',img:'return-gifts/hp-a4-folder.jpg',e:'📁',type:'stationery',gtheme:'hp',age:'7-14',unit:270,bg:'#FFFBDC',tag:''},
  {id:'g41',n:'K-pop A4 Folder (4 designs)',img:'return-gifts/kpop-a4-folder.jpg',e:'📁',type:'stationery',gtheme:'kpop',age:'8-14',unit:270,bg:'#FFFBDC',tag:''},
  {id:'g42',n:'Harry Potter Pencil Pouch',img:'return-gifts/hp-pencil-pouch.jpg',e:'✏️',type:'stationery',gtheme:'hp',age:'7-14',unit:200,bg:'#FFFBDC',tag:''},
  // Budget range (under Rs 250), added 2026-10-02 per Shruti.
  {id:'g43',n:'UNO Cards',img:'return-gifts/uno-cards.jpg',e:'🃏',type:'games',gtheme:'generic',age:'7-14',unit:90,bg:'#FFFBDC',tag:''},
  {id:'g44',n:'Wooden Car Pen Stand',img:'return-gifts/wooden-car-pen-stand.jpg',e:'🚗',type:'stationery',gtheme:'generic',age:'3-10',unit:110,bg:'#FFFBDC',tag:''},
  {id:'g45',n:'Minion Sketch Pen Set',img:'return-gifts/minion-sketch-pen-set.jpg',e:'🖍️',type:'stationery',gtheme:'generic',age:'3-10',unit:100,bg:'#FFFBDC',tag:''},
  {id:'g46',n:'Silicone Coin Pouch',img:'return-gifts/silicone-coin-pouch.jpg',e:'👛',type:'bags',gtheme:'generic',age:'3-12',unit:100,bg:'#FFF0F7',tag:''},
  {id:'g47',pkgs:['unicorn-basic'],n:'Fruit Pencil Pouch',img:'return-gifts/fruit-pencil-pouch.jpg',e:'🍉',type:'bags',gtheme:'generic',age:'3-12',unit:100,bg:'#FFF0F7',tag:''},
  {id:'g48',n:'Labubu Bag Charm / Keychain',img:'return-gifts/labubu-bag-charm.jpg',e:'🔑',type:'home',gtheme:'generic',age:'5-14',unit:80,bg:'#F0FDF4',tag:''},
  {id:'g49',n:'Cube Scale (20 cm)',img:'return-gifts/cube-scale-20cm.jpg',e:'📏',type:'stationery',gtheme:'generic',age:'5-14',unit:100,bg:'#FFFBDC',tag:''},
  {id:'g50',n:'Kaleidoscope',img:'return-gifts/kaleidoscope.jpg',e:'🔭',type:'games',gtheme:'generic',age:'3-10',unit:110,bg:'#FFFBDC',tag:''},
  {id:'g51',n:'Kids Folder',img:'return-gifts/kids-folder.jpg',e:'📁',type:'stationery',gtheme:'generic',age:'5-14',unit:160,bg:'#FFFBDC',tag:''},
  {id:'g52',n:'Lego Band',img:'return-gifts/lego-band.jpg',e:'⌚',type:'home',gtheme:'generic',age:'4-12',unit:140,bg:'#F0FDF4',tag:''},
  {id:'g53',n:'Lego Pencil Set',img:'return-gifts/lego-pencil-set.jpg',e:'✏️',type:'stationery',gtheme:'generic',age:'4-12',unit:130,bg:'#FFFBDC',tag:''},
  {id:'g54',n:'Kids Lunch Bag (assorted prints)',img:'return-gifts/kids-lunch-bag.jpg',e:'🍱',type:'bags',gtheme:'generic',age:'3-12',unit:120,bg:'#FFF0F7',tag:''},
  {id:'g55',n:'Magnetic Planner with Whiteboard Marker',img:'return-gifts/magnetic-planner.jpg',e:'🗓️',type:'stationery',gtheme:'generic',age:'6-14',unit:130,bg:'#FFFBDC',tag:''},
  {id:'g56',pkgs:['spy-basic'],n:'Binoculars',img:'return-gifts/binoculars.jpg',e:'🔭',type:'games',gtheme:'generic',age:'3-10',unit:120,bg:'#FFFBDC',tag:''},
  {id:'g57',n:'Pinball Game',img:'return-gifts/pinball-game.jpg',e:'🎯',type:'games',gtheme:'generic',age:'4-12',unit:210,bg:'#FFFBDC',tag:''},
  {id:'g58',pkgs:['turf-basic'],n:'Swimming Goggles (assorted designs)',img:'return-gifts/swimming-goggles.jpg',e:'🥽',type:'home',gtheme:'generic',age:'4-12',unit:200,bg:'#F0FDF4',tag:''},
  {id:'g59',n:'Rechargeable Mini Fan',img:'return-gifts/rechargeable-mini-fan.jpg',e:'🌀',type:'home',gtheme:'generic',age:'5-14',unit:200,bg:'#F0FDF4',tag:''},
  // Rs 200-1200 range, added 2026-10-02 per Shruti.
  {id:'g60',n:'Habit Tracker',img:'return-gifts/habit-tracker.jpg',e:'✅',type:'stationery',gtheme:'generic',age:'5-12',unit:320,bg:'#FFFBDC',tag:''},
  {id:'g61',n:'Digital Alarm Clock',img:'return-gifts/digital-alarm-clock.jpg',e:'⏰',type:'home',gtheme:'generic',age:'5-14',unit:300,bg:'#F0FDF4',tag:''},
  {id:'g62',pkgs:['unicorn-basic'],n:'DIY Decorate-your-own Mug',img:'return-gifts/diy-decorate-your-own-mug.jpg',e:'☕',type:'personalized',gtheme:'generic',age:'4-12',unit:320,bg:'#F0F7FF',tag:''},
  {id:'g63',n:'Mini Pocket Wireless Speaker',img:'return-gifts/mini-pocket-wireless-speaker.jpg',e:'🔊',type:'home',gtheme:'generic',age:'6-14',unit:270,bg:'#F0FDF4',tag:''},
  {id:'g64',n:'Gobble Game',img:'return-gifts/gobble-game.jpg',e:'🎲',type:'games',gtheme:'generic',age:'5-12',unit:280,bg:'#FFFBDC',tag:''},
  {id:'g65',pkgs:['turf-basic'],n:'Solo Practice Ball Game',img:'return-gifts/solo-practice-ball-game.jpg',e:'🎾',type:'games',gtheme:'generic',age:'4-12',unit:300,bg:'#FFFBDC',tag:''},
  {id:'g66',n:'Metal Book Reading Stand',img:'return-gifts/metal-book-reading-stand.jpg',e:'📖',type:'stationery',gtheme:'generic',age:'5-14',unit:380,bg:'#FFFBDC',tag:''},
  {id:'g67',n:'12-compartment Folder',img:'return-gifts/12-compartment-folder.jpg',e:'📁',type:'stationery',gtheme:'generic',age:'5-14',unit:300,bg:'#FFFBDC',tag:''},
  {id:'g68',n:'Dobble Game',img:'return-gifts/dobble-game.jpg',e:'🎲',type:'games',gtheme:'generic',age:'5-14',unit:300,bg:'#FFFBDC',tag:''},
  {id:'g69',n:'K-pop Multipurpose Pouch',img:'return-gifts/k-pop-pouch.jpg',e:'👝',type:'bags',gtheme:'kpop',age:'8-14',unit:220,bg:'#FFF0F7',tag:''},
  {id:'g70',n:'Harry Potter Multipurpose Pouch',img:'return-gifts/harry-potter-pouch.jpg',e:'👝',type:'bags',gtheme:'hp',age:'7-14',unit:220,bg:'#FFF0F7',tag:''},
  {id:'g71',n:'Harry Potter Diary',img:'return-gifts/harry-potter-diary.jpg',e:'📓',type:'stationery',gtheme:'hp',age:'7-14',unit:500,bg:'#FFFBDC',tag:''},
  {id:'g72',n:'LED Neon Drawing Board',img:'return-gifts/led-neon-drawing-board.jpg',e:'💡',type:'stationery',gtheme:'generic',age:'4-12',unit:400,bg:'#FFFBDC',tag:''},
  {id:'g73',n:'Soup Cup Lunch Box',img:'return-gifts/soup-cup-lunch-box.jpg',e:'🥣',type:'home',gtheme:'generic',age:'3-12',unit:530,bg:'#F0FDF4',tag:''},
  {id:'g74',pkgs:['spy-basic'],n:'Password Compass Box',img:'return-gifts/password-compass-box.jpg',e:'🔐',type:'stationery',gtheme:'space',age:'5-12',unit:600,bg:'#FFFBDC',tag:''},
  {id:'g75',n:'Science 61 Experiment Kit',img:'return-gifts/science-61-experiment-kit.jpg',e:'🧪',type:'games',gtheme:'generic',age:'8-14',unit:600,bg:'#FFFBDC',tag:''},
  {id:'g76',n:'Lunch Bag (assorted prints)',img:'return-gifts/lunch-bag-many-prints.jpg',e:'🎒',type:'bags',gtheme:'generic',age:'3-12',unit:630,bg:'#FFF0F7',tag:''},
  {id:'g77',pkgs:['turf-basic'],n:'Pickleball Set',img:'return-gifts/pickleball-set.jpg',e:'🏓',type:'games',gtheme:'generic',age:'8-14',unit:770,bg:'#FFFBDC',tag:''},
  {id:'g78',pkgs:['spy-basic'],n:'Retro Handheld Game (400 games)',img:'return-gifts/retro-handheld-game-400-games.jpg',e:'🎮',type:'games',gtheme:'generic',age:'6-14',unit:525,bg:'#FFFBDC',tag:''},
  {id:'g79',n:'Glow-in-the-dark Blanket (assorted designs)',img:'return-gifts/glow-in-the-dark-blanket-many-designs.jpg',e:'🌙',type:'home',gtheme:'generic',age:'3-12',unit:672,bg:'#F0FDF4',tag:''},
  {id:'g80',n:'Calligraphy Pen Set with Wax Seal',img:'return-gifts/calligraphy-pen-set-with-wax-seal.jpg',e:'🖋️',type:'stationery',gtheme:'generic',age:'10-14',unit:840,bg:'#FFFBDC',tag:''},
  {id:'g81',n:'Lego Photo Frame',img:'return-gifts/lego-photo-frame.jpg',e:'🖼️',type:'home',gtheme:'generic',age:'4-12',unit:532,bg:'#F0FDF4',tag:''},
  {id:'g82',n:'3D Pen',img:'return-gifts/3d-pen.jpg',e:'✏️',type:'stationery',gtheme:'generic',age:'8-14',unit:630,bg:'#FFFBDC',tag:''},
  {id:'g83',n:'Insulated Food Jar Lunch Box',img:'return-gifts/insulated-food-jar-lunch-box.jpg',e:'🥣',type:'home',gtheme:'generic',age:'5-14',unit:672,bg:'#F0FDF4',tag:''},
  {id:'g84',n:'Steel Sipper Tumbler',img:'return-gifts/fancy-steel-sipper-tumbler.jpg',e:'🥤',type:'home',gtheme:'generic',age:'5-14',unit:700,bg:'#F0FDF4',tag:''},
  {id:'g85',n:'Pastel Calculator',img:'return-gifts/pastel-calculator.jpg',e:'🧮',type:'stationery',gtheme:'generic',age:'6-14',unit:700,bg:'#FFFBDC',tag:''},
  {id:'g86',n:'Insulated Ice Flask (500 ml)',img:'return-gifts/insulated-ice-flask-500ml.jpg',e:'🧊',type:'home',gtheme:'generic',age:'6-14',unit:840,bg:'#F0FDF4',tag:''},
  {id:'g87',n:'Charm Tote Bag (assorted colours)',img:'return-gifts/charm-tote-bag.jpg',e:'👜',type:'bags',gtheme:'generic',age:'6-14',unit:700,bg:'#FFF0F7',tag:''},
  {id:'g88',n:'Cluedo Board Game',img:'return-gifts/cluedo-board-game.jpg',e:'🔍',type:'games',gtheme:'generic',age:'8-14',unit:770,bg:'#FFFBDC',tag:''},
  {id:'g89',n:'Controller Video Game (520 games)',img:'return-gifts/controller-video-game-520-games.jpg',e:'🎮',type:'games',gtheme:'generic',age:'6-14',unit:770,bg:'#FFFBDC',tag:''},
  {id:'g90',n:'Kids Bluetooth Headphones (assorted themes)',img:'return-gifts/kids-bluetooth-headphones-many-themes.jpg',e:'🎧',type:'home',gtheme:'generic',age:'4-12',unit:672,bg:'#F0FDF4',tag:''},
  {id:'g91',n:'Taboo Game',img:'return-gifts/taboo-game.jpg',e:'🗣️',type:'games',gtheme:'generic',age:'12-14',unit:630,bg:'#FFFBDC',tag:''},
  {id:'g92',n:'Astronaut Galaxy Projector',img:'return-gifts/astronaut-galaxy-projector.jpg',e:'🧑‍🚀',type:'home',gtheme:'space',age:'4-14',unit:770,bg:'#F0FDF4',tag:''},
  {id:'g93',n:'Kids Lunch Box (assorted prints)',img:'return-gifts/kids-lunch-box-many-prints.jpg',e:'🍱',type:'home',gtheme:'generic',age:'3-12',unit:595,bg:'#F0FDF4',tag:''},
  {id:'g94',n:'Kids Bento Box',img:'return-gifts/kids-bento-box.jpg',e:'🍱',type:'home',gtheme:'generic',age:'3-12',unit:511,bg:'#F0FDF4',tag:''},
];

window.WS_GIFT_STOCK_NOTE='Return gifts are sourced from our vendors and are subject to stock availability. They are billed separately from your party: once our team confirms stock, we\'ll send you a payment link on email and WhatsApp (100% advance). Delivery charges are extra, at actuals.';

// Legacy package-page ids (old turf-basic links / saved carts) -> catalogue ids.
const LEGACY={cap1:'g25',tshirt1:'g26'};
window.wsGiftById=function(id){
  id=LEGACY[id]||id;
  return window.WS_GIFTS.find(g=>g.id===id)||null;
};
// Gifts a package page recommends by default: every live (non-hidden) gift
// tagged for that package, in catalogue order. Falls back to a few popular
// live gifts if nothing is tagged yet, so the section is never empty.
window.wsGiftsFor=function(pkg,limit){
  const live=window.WS_GIFTS.filter(g=>!g.hidden);
  let out=live.filter(g=>(g.pkgs||[]).includes(pkg));
  if(out.length<3){out=out.concat(live.filter(g=>!out.includes(g)&&[].concat(g.gtheme).includes('generic')).slice(0,3-out.length));}
  return limit?out.slice(0,limit):out;
};
// Card shape the package pages' renderToggleGrid() expects.
window.wsPkgGiftItem=function(g){
  return {id:g.id, ic:g.e, img:'img/'+g.img, name:g.n, d:'Ages '+g.age+' · vendor item, subject to stock', perChild:g.unit};
};

// ── "View all return gifts" picker for the package pages ─────────────────
// A self-contained overlay (own styles) listing every live gift with type
// chips; + Add / ✓ Added calls opts.onToggle(id) and re-renders.
let _opts=null,_type='all';
const TYPES=[['all','All'],['bags','Bags & Pouches'],['games','Games'],['personalized','Personalized'],['stationery','Stationery'],['home','Home & Lifestyle']];
function css(){
  if(document.getElementById('wsgCss'))return;
  const s=document.createElement('style');s.id='wsgCss';
  s.textContent=`.wsg-ov{position:fixed;inset:0;background:rgba(25,18,40,.55);z-index:9999;display:flex;align-items:flex-end;justify-content:center}
@media(min-width:720px){.wsg-ov{align-items:center}}
.wsg-box{background:#fff;width:min(980px,100%);max-height:92vh;border-radius:18px 18px 0 0;display:flex;flex-direction:column;overflow:hidden;font-family:inherit}
@media(min-width:720px){.wsg-box{border-radius:18px}}
.wsg-hd{padding:16px 18px 10px;border-bottom:1px solid #EEE8F6}
.wsg-top{display:flex;justify-content:space-between;align-items:center;gap:12px}
.wsg-h{font-size:18px;font-weight:800;color:#2D2140;margin:0}
.wsg-x{border:none;background:#F3EEFC;color:#3B2A55;width:34px;height:34px;border-radius:50%;font-size:18px;cursor:pointer;flex:none}
.wsg-note{font-size:12px;color:#6B5B85;line-height:1.5;margin:6px 0 10px}
.wsg-chips{display:flex;gap:6px;overflow-x:auto;padding-bottom:2px}
.wsg-chip{flex:none;border:1px solid #E3DCEE;background:#fff;color:#3B2A55;border-radius:999px;padding:6px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
.wsg-chip.on{background:#3B2A55;color:#fff;border-color:#3B2A55}
.wsg-list{flex:1 1 auto;min-height:0;overflow-y:auto;padding:14px 18px 18px;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));grid-auto-rows:max-content;align-content:start;gap:12px}
.wsg-card{border:1.5px solid #EEE8F6;border-radius:14px;overflow:hidden;display:flex;flex-direction:column;background:#fff}
.wsg-card.on{border-color:#E65A96;box-shadow:0 0 0 2px rgba(230,90,150,.15)}
.wsg-img{aspect-ratio:4/3;background:#F6F3FA center/cover no-repeat;display:flex;align-items:center;justify-content:center;font-size:34px}
.wsg-b{padding:10px 12px 12px;display:flex;flex-direction:column;gap:6px;flex:1}
.wsg-n{font-size:13.5px;font-weight:700;color:#2D2140;line-height:1.3}
.wsg-m{font-size:11.5px;color:#7A7287}
.wsg-f{display:flex;justify-content:space-between;align-items:center;margin-top:auto;gap:8px}
.wsg-p{font-size:14px;font-weight:800;color:#2D2140}
.wsg-add{border:none;border-radius:999px;padding:7px 14px;font-size:12.5px;font-weight:700;cursor:pointer;background:#E65A96;color:#fff}
.wsg-add.on{background:#E7F6EC;color:#166534}
.wsg-ft{padding:12px 18px;border-top:1px solid #EEE8F6;display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:13px;color:#3B2A55}
.wsg-done{border:none;border-radius:999px;padding:10px 20px;font-weight:800;background:#3B2A55;color:#fff;cursor:pointer}`;
  document.head.appendChild(s);
}
function fmt(n){return '₹'+Math.round(n).toLocaleString('en-IN');}
function render(){
  const ov=document.getElementById('wsgOv');if(!ov||!_opts)return;
  const sel=_opts.selected();const kids=_opts.kids?_opts.kids():null;
  const live=window.WS_GIFTS.filter(g=>!g.hidden&&(_type==='all'||g.type===_type));
  ov.querySelector('.wsg-chips').innerHTML=TYPES.map(t=>'<button type="button" class="wsg-chip'+(t[0]===_type?' on':'')+'" data-t="'+t[0]+'">'+t[1]+'</button>').join('');
  ov.querySelector('.wsg-list').innerHTML=live.map(g=>{
    const on=sel.includes(g.id);
    const img=g.img?'style="background-image:url(\'img/'+g.img+'\')"':'';
    return '<div class="wsg-card'+(on?' on':'')+'"><div class="wsg-img" '+img+'>'+(g.img?'':g.e)+'</div><div class="wsg-b"><div class="wsg-n">'+g.n+'</div><div class="wsg-m">Ages '+g.age+' · '+fmt(g.unit)+' per child</div><div class="wsg-f"><span class="wsg-p">'+(kids?fmt(g.unit*kids):fmt(g.unit))+'</span><button type="button" class="wsg-add'+(on?' on':'')+'" data-id="'+g.id+'">'+(on?'✓ Added':'+ Add')+'</button></div></div></div>';
  }).join('')||'<div class="wsg-m">No gifts in this category yet.</div>';
  ov.querySelector('.wsg-cnt').textContent=sel.length?(sel.length+' gift'+(sel.length>1?'s':'')+' selected'+(kids?' · '+kids+' of each':'')):'No gifts selected';
}
window.wsOpenAllGifts=function(opts){
  css();_opts=opts;_type='all';
  let ov=document.getElementById('wsgOv');
  if(!ov){
    ov=document.createElement('div');ov.id='wsgOv';ov.className='wsg-ov';
    ov.innerHTML='<div class="wsg-box" role="dialog" aria-modal="true" aria-label="All return gifts"><div class="wsg-hd"><div class="wsg-top"><h3 class="wsg-h">All return gifts</h3><button type="button" class="wsg-x" aria-label="Close">✕</button></div><div class="wsg-note"></div><div class="wsg-chips"></div></div><div class="wsg-list"></div><div class="wsg-ft"><span class="wsg-cnt"></span><button type="button" class="wsg-done">Done</button></div></div>';
    document.body.appendChild(ov);
    ov.addEventListener('click',e=>{
      if(e.target===ov||e.target.closest('.wsg-x')||e.target.closest('.wsg-done')){ov.remove();return;}
      const c=e.target.closest('.wsg-chip');if(c){_type=c.dataset.t;render();return;}
      const a=e.target.closest('.wsg-add');if(a&&_opts){_opts.onToggle(a.dataset.id);render();}
    });
    document.addEventListener('keydown',function esc(e){if(e.key==='Escape'){const o=document.getElementById('wsgOv');if(o)o.remove();document.removeEventListener('keydown',esc);}});
  }
  ov.querySelector('.wsg-note').textContent=window.WS_GIFT_STOCK_NOTE;
  render();
};
})();
