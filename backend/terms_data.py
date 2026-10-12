"""
Website Terms & Conditions (terms.html) as data, for the party plan PDF
(2026-10-12, per Shruti — "the T&C for website should come here in the party
plan pdf"). KEEP IN STEP WITH terms.html: when a clause changes there, change
it here too (the backend is deployed without the website files).
Each clause: {"title", "parts": [("p" | "li", text), ...]}.
"""

WEBSITE_TERMS = [
 {
  "title": "Booking Confirmation",
  "parts": [
   [
    "li",
    "Your event date will be confirmed and blocked only upon receipt of 50% advance payment."
   ],
   [
    "li",
    "Until the advance is received, Wondershop Experiences reserves the right to accept another booking for the same date."
   ]
  ]
 },
 {
  "title": "Payment Terms",
  "parts": [
   [
    "li",
    "50% Advance: To confirm the booking."
   ],
   [
    "li",
    "40% Balance: Payable 2 days prior to the event date."
   ],
   [
    "li",
    "Final 10% Balance: Payable before the commencement of the event. Kindly arrange for a family member or authorised representative to be available for the payment, as the host may be occupied with guests during the event."
   ],
   [
    "li",
    "Return gifts are payable 100% in advance (see Return Gifts below)."
   ],
   [
    "li",
    "Any pending payment must be cleared on the day of the event, before the party starts. If you plan to pay in cash, please keep the cash counted and ready in an envelope before the event."
   ]
  ]
 },
 {
  "title": "Venue Facilities",
  "parts": [
   [
    "p",
    "The client shall ensure that our team has access to:"
   ],
   [
    "li",
    "Clean washroom facilities"
   ],
   [
    "li",
    "Drinking water"
   ],
   [
    "li",
    "Basic ventilation (fan and/or air conditioning) from the beginning of setup until completion of pack-up"
   ]
  ]
 },
 {
  "title": "Venue & Society Restrictions",
  "parts": [
   [
    "p",
    "The client is responsible for informing Wondershop Experiences, in advance, of any venue or society restrictions, including but not limited to:"
   ],
   [
    "li",
    "Vendor entry permissions or gate passes."
   ],
   [
    "li",
    "Vehicle entry restrictions."
   ],
   [
    "li",
    "Movement of materials within the premises."
   ],
   [
    "li",
    "Service lift availability and usage restrictions."
   ],
   [
    "li",
    "Restrictions on electricity usage."
   ],
   [
    "li",
    "Restrictions on the use of tapes, adhesives, hooks or hanging decor."
   ],
   [
    "li",
    "Noise or music limitations."
   ],
   [
    "li",
    "Any restrictions imposed by the venue, society or caterer."
   ],
   [
    "p",
    "Any additional costs, delays, penalties or operational challenges arising due to non-disclosure of such restrictions shall be the responsibility of the client."
   ]
  ]
 },
 {
  "title": "Cancellation Policy",
  "parts": [
   [
    "li",
    "If Wondershop Experiences is unable to execute the event due to reasons attributable to us, the entire advance amount received will be refunded."
   ],
   [
    "li",
    "If the client cancels the booking for any reason, the advance amount paid shall be non-refundable."
   ]
  ]
 },
 {
  "title": "Guest Count",
  "parts": [
   [
    "li",
    "The confirmed number of children/participants cannot be reduced on the day of the event, and in any case not once our team reaches the venue."
   ],
   [
    "li",
    "Any increase in the number of participants will be charged as per the applicable rates. We cannot guarantee the same rates for any modifications after freezing the event."
   ]
  ]
 },
 {
  "title": "Sound & Music",
  "parts": [
   [
    "li",
    "For parties with more than 25 children, a professional mic and speaker setup, with a person handling it, is mandatory. Wondershop Experiences can arrange this for you at an additional cost."
   ],
   [
    "li",
    "If the client chooses to arrange the sound setup themselves, it must be in place at the venue. If the client takes this responsibility and it is not arranged, Wondershop Experiences reserves the right to leave the event, and the full payment will remain due."
   ],
   [
    "li",
    "The host is not responsible for handling the party music. Out of courtesy, the host may help with basic music needs such as the Happy Birthday or welcome song, where this can be done easily. For parties with more than 25 children, a person handling the music professionally is needed, or the parent takes responsibility for the music."
   ]
  ]
 },
 {
  "title": "Additional Requirements",
  "parts": [
   [
    "li",
    "Any additions or changes to the confirmed scope of work after booking confirmation may attract additional charges."
   ],
   [
    "li",
    "Any extra materials, activities, gifts or services requested during or before the event will be billed separately."
   ]
  ]
 },
 {
  "title": "Product & Material Availability",
  "parts": [
   [
    "p",
    "The decor elements, props, return gifts, giveaways, stationery, colours and other materials shown during the planning stage are indicative and subject to market availability. In the event that a particular item becomes unavailable after booking confirmation, Wondershop Experiences reserves the right to provide a suitable alternative of similar quality and value. We cannot guarantee the availability of the exact product, colour, brand or size discussed during the planning phase."
   ]
  ]
 },
 {
  "title": "Venue Readiness",
  "parts": [
   [
    "p",
    "The venue should be clean and ready before our team arrives for setup. Our team is not responsible for:"
   ],
   [
    "li",
    "Cleaning the venue before setup."
   ],
   [
    "li",
    "Cleaning the venue during the event."
   ],
   [
    "li",
    "Cleaning the venue after the event, unless this has been specifically agreed upon as part of the scope of work."
   ]
  ]
 },
 {
  "title": "Movement of Furniture",
  "parts": [
   [
    "p",
    "Our team is not responsible for moving furniture, heavy fixtures or venue equipment. If furniture needs to be shifted before, during or after setup, the client shall arrange adequate manpower. If requested in advance, Wondershop Experiences may assist in arranging additional manpower at an extra cost, subject to availability."
   ]
  ]
 },
 {
  "title": "Damages",
  "parts": [
   [
    "p",
    "Any damage caused to venue property, decor, equipment or materials by guests, children or third parties during the event shall be the responsibility of the client. Any repair or replacement costs arising from such damage may be recovered from the client, where applicable."
   ]
  ]
 },
 {
  "title": "Delays Beyond Our Control",
  "parts": [
   [
    "p",
    "Wondershop Experiences shall not be held responsible for delays or disruption caused by circumstances beyond our reasonable control, including but not limited to:"
   ],
   [
    "li",
    "Venue or society restrictions."
   ],
   [
    "li",
    "Delayed vendor entry."
   ],
   [
    "li",
    "Lift unavailability."
   ],
   [
    "li",
    "Power outages."
   ],
   [
    "li",
    "Extreme weather conditions."
   ],
   [
    "li",
    "Government restrictions or force majeure events."
   ]
  ]
 },
 {
  "title": "Respectful Conduct",
  "parts": [
   [
    "p",
    "We believe the best events are created when clients and our team work together with mutual respect, clear communication, and a shared focus on creating a memorable celebration for the children."
   ],
   [
    "p",
    "Both the client and the Wondershop Experiences team are expected to maintain a respectful and cordial working relationship throughout the planning, setup, event execution and pack-up."
   ],
   [
    "p",
    "In the unlikely event of any concern or issue, we request that it be addressed in a constructive and solution-oriented manner. Abusive, disrespectful, threatening, or aggressive behaviour towards any member of the Wondershop Experiences team will not be tolerated."
   ],
   [
    "p",
    "If our team is subjected to such behaviour, Wondershop Experiences reserves the right to escalate the matter, withdraw the concerned team member(s), or discontinue services if the situation compromises their safety or dignity. Such action shall not entitle the client to any refund."
   ]
  ]
 },
 {
  "title": "Event Timings & Overtime",
  "parts": [
   [
    "p",
    "Our team schedules multiple events and commitments throughout the day. We request that the event adheres to the agreed setup, event and pack-up timelines."
   ],
   [
    "p",
    "If the event is delayed or extended due to reasons attributable to the client (including delayed venue access, late start, delayed cake cutting, extended celebrations or any other client-related reason), the following shall apply:"
   ],
   [
    "li",
    "If the extension overlaps with meal timings or requires our team to remain on-site for an extended duration, the client shall arrange a wholesome meal for the team. The meal should be appropriate for an adult as a proper lunch/dinner as applicable."
   ],
   [
    "li",
    "If any member of our team has a prior commitment, another scheduled event or operational requirement, they may need to leave at the originally agreed time. In such cases, Wondershop Experiences will make reasonable efforts to minimise any disruption; however, we cannot guarantee extended services beyond the agreed duration."
   ],
   [
    "li",
    "Any extension to the agreed event duration may also attract additional charges, subject to team availability."
   ]
  ]
 },
 {
  "title": "Image Disclaimer",
  "parts": [
   [
    "p",
    "The images displayed on our website are reference images showcasing our design style and quality of work."
   ],
   [
    "p",
    "While we strive to recreate every setup as closely as possible, the final outcome may vary slightly due to factors beyond our control, including but not limited to:"
   ],
   [
    "li",
    "Venue size and layout"
   ],
   [
    "li",
    "Indoor/outdoor lighting conditions"
   ],
   [
    "li",
    "Time of the event"
   ],
   [
    "li",
    "Photography, camera settings, and image editing"
   ],
   [
    "li",
    "Availability and variations in balloons, flowers, props, and other materials"
   ],
   [
    "li",
    "Colour representation across different screens and devices"
   ],
   [
    "p",
    "Our team is committed to delivering an event that closely matches the approved concept while maintaining the same overall look, feel, and quality. However, an exact replica of any reference image cannot be guaranteed, and minor variations should be expected."
   ]
  ]
 },
 {
  "title": "Return Gifts",
  "parts": [
   [
    "li",
    "Wondershop Experiences acts as an aggregator for return gift items sourced from third-party suppliers. We do not guarantee the quality of these items, especially imported products. Customers are advised to check the items and use their own caution, including age suitability and supervision of young children."
   ],
   [
    "li",
    "Return gift orders require 100% advance payment."
   ],
   [
    "li",
    "Return gifts once sold cannot be returned or exchanged."
   ],
   [
    "li",
    "Delivery charges are extra, at actuals. Return gifts are delivered through a third-party transport service (such as Porter), booked on cash on delivery. The person receiving the parcel pays the delivery charge directly to the delivery partner."
   ],
   [
    "li",
    "Any issues during transport should be taken up with the transport vendor. We will share the vendor's contact details and offer as much support as we can; however, Wondershop Experiences has limited liability for transport-related issues."
   ]
  ]
 },
 {
  "title": "Acceptance",
  "parts": [
   [
    "p",
    "By confirming the booking and making the advance payment, the client acknowledges that they have read, understood and accepted these Terms & Conditions."
   ]
  ]
 }
]
