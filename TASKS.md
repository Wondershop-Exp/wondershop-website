# Tasks

## Active

### Security
- [ ] **Rotate Google OAuth credentials (Client ID/Secret/Refresh Token)** - a `.env` backup (`backend/_to_delete/env.bak.*`) containing the live Gmail OAuth Client ID, Client Secret, and Refresh Token was accidentally staged in a git commit on 2026-08-15. GitHub's push protection blocked the push before it reached the remote, and the bad commit was amended out locally, but the credential did leave the machine during the blocked push attempt. Regenerate in Google Cloud Console and update the corresponding Railway env vars (used for sending booking confirmation/team emails) to be fully safe.

### Integrations
- [ ] **Get a Google Maps API key & paste it into builder.html** - Places Autocomplete is already wired into the Checkout venue address and Return Gift delivery address fields (auto-fills the Google Maps link, no more copy-paste) but needs a real key to go live. See Claude's step-by-step guide from 2026-08-16 for exact instructions (Google Cloud Console → new project → enable Places API + Maps JavaScript API → enable billing → create & restrict API key → paste into `WS_GMAPS_KEY` near the top of builder.html, replacing `YOUR_GOOGLE_MAPS_API_KEY`).

### SEO — Quick Wins (do this week)
- [ ] **Connect custom domain** - point wondershopexperiences.com to GitHub Pages via CNAME; highest-leverage SEO fix
- [ ] **Claim & complete Google Business Profile** - set service area to all Mumbai, add photos, list services (birthday decor, kids party, birthday planner); needed for "decor near me" searches
- [ ] **Rewrite H1s on all pages** - homepage, gallery, about us, contact, blog (see audit doc for suggested copy)
- [ ] **Update title tags on all pages** - lead with keyword e.g. "Kids Birthday Party Mumbai — Wondershop Experiences"
- [ ] **Create sitemap.xml** - list all pages, place in site root
- [ ] **Create robots.txt** - allow all, reference sitemap
- [ ] **Add LocalBusiness JSON-LD schema** - to index.html and contact.html (address, phone, hours, service area)
- [ ] **Rename gallery images** - replace 1.jpg–24.jpg and filenames with spaces with descriptive hyphenated names (e.g. spy-theme-birthday-mumbai.jpg); update all HTML references
- [ ] **Register in Google Search Console** - submit sitemap after custom domain is live
- [ ] **Add "party planner" language to homepage** - currently missing this high-intent keyword variant
- [ ] **Update © 2025 → © 2026** in footer across all pages

### SEO — Strategic (this quarter)
- [ ] **Split blog into individual pages** - /blogs/spy-theme-guide.html, /blogs/return-gifts.html, /blogs/planning-checklist.html; 3 rankable URLs instead of 1
- [ ] **Build 8–10 theme landing pages** - one page per theme (/spy-theme-birthday-party-mumbai/ etc.) with 300+ words, gallery images, CTA
- [ ] **Write blog: "How much does a kids birthday party cost in Mumbai"** - most-searched informational query; converts undecided parents
- [ ] **Write blog: "Decor ideas for kids birthday parties in Mumbai"** - targets your exact keyword; links to gallery
- [ ] **Write blog: "Best venues for kids birthday party in Mumbai"** - broad informational, positions Wondershop as expert
- [ ] **Add FAQPage schema + FAQ section to homepage** - enables rich snippets in search results
- [ ] **Build 3–5 neighbourhood landing pages** - /birthday-party-bandra/, /andheri/, /powai/ for hyperlocal traffic
- [ ] **Create /packages/ pricing page** - reduces "how much does it cost" friction; ranks for pricing queries
- [ ] **Add enquiry/contact form to Contact page** - complement to WhatsApp CTA for parents who prefer filling a form
- [ ] **Add Article schema to blog posts** after splitting - enables rich snippets
- [ ] **Internal linking audit** - add contextual links from blog posts to theme pages and builder

## Waiting On

- [ ] **New "Imposter" theme** - waiting on product manager for decor/pricing details (emoji/icon, age range, price, balloon count & colors, panel setup, session length, on-site items needed) before it can be added to the builder's THEMES list. Requested alongside Spy theme; Laser Tunnel & Dark Room stay Spy-only for now.
- [ ] **2 remaining Unicorn Basic activities** - Bracelet Making and Hair Braiding still requested for unicorn-basic.html but don't exist in the ACTS catalogue. (Glitter Station and Slime Making have since been added with real pricing from Shruti; Nail Art Station, a21, was a real catalogue match added earlier.) Waiting on Shruti for icon, age range, duration, and pricing for the last 2.
- [ ] **Fix the 3 "Our Promise / Vision / Mission" cards on the Our Story page** - Shruti flagged the current cards "aren't proper" (2026-08-16) and will share the correct reference images to rebuild them with. Currently using placeholder character icons (kid-joy.png etc.) in the "Our Promise" card as a stand-in — swap once real images arrive.

## Someday

- [ ] **Curate theme based on a budget** - let a customer enter their budget and have the builder suggest/filter themes (and decor tiers) that fit it, instead of having to browse everything and price it out manually. (2026-08-16, per Shruti)

## Done

- [x] ~~Fix blogs.html~~ - phone numbers updated, nav tagline removed, YouTube added to footer
- [x] ~~Homepage revamp~~ - all 23+ changes applied to index.html
- [x] ~~Fix CORS for GitHub Pages~~ (Railway ALLOWED_ORIGINS updated)
- [x] ~~Fix contact.html~~ - full CSS rewrite, updated contact details
- [x] ~~Fix gallery.html~~ - CSS injected, phone numbers updated
- [x] ~~Fix testimonials.html~~ - CSS injected, phone numbers updated
- [x] ~~Fix about-us.html~~ - CSS injected, phone numbers updated
- [x] ~~Fix doSearch bug across all secondary pages~~
