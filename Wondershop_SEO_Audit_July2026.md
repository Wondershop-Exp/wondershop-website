# Wondershop Experiences — SEO Audit
**Date:** July 2026 | **Site:** wondershop-exp.github.io/wondershop-website/ | **Auditor:** Claude

---

## Executive Summary

Wondershop has a genuine content advantage — the brand voice, depth of copy, and page design are noticeably better than most Mumbai birthday party competitors. However, the site is operating under a significant self-imposed SEO handicap: hosting on a `github.io` subdomain instead of a custom domain means Google cannot build domain authority for `wondershopexperiences.com`. On top of that, every page has an H1 that's poetic but keyword-free, there's no sitemap, no schema markup, no robots.txt, and the blog structure traps three valuable articles on a single URL that Google sees as one page.

**Top 3 priorities:**
1. **Custom domain** — move to `wondershopexperiences.com` immediately; this is the highest-leverage fix
2. **H1 + title keyword injection** — every page's H1 and title tag ignores the words parents type into Google
3. **Split the blog + build theme pages** — the blog and theme content is the strongest content asset on the site; unlocking it requires individual URLs

**Overall assessment:** Strong creative foundation, weak technical and on-page SEO. Medium-term opportunity is significant if fundamentals are fixed.

---

## Keyword Opportunity Table

| Keyword | Est. Difficulty | Opportunity | Intent | Recommended Content Type |
|---|---|---|---|---|
| kids birthday party Mumbai | High | **High** | Transactional | Homepage H1 + meta |
| birthday party planner Mumbai | High | **High** | Transactional | Homepage / dedicated LP |
| birthday party organiser Mumbai | High | **High** | Transactional | Homepage / dedicated LP |
| themed birthday party Mumbai | Medium | **High** | Transactional | Homepage section + theme LPs |
| first birthday party Mumbai | Medium | **High** | Transactional | New landing page |
| kids birthday party at home Mumbai | Medium | **High** | Transactional | New landing page |
| spy theme birthday party Mumbai | Low | **High** | Transactional | Spy theme page |
| princess birthday party Mumbai | Low | **High** | Transactional | Princess theme page |
| unicorn birthday party Mumbai | Low | **High** | Transactional | Unicorn theme page |
| birthday decorator for kids Mumbai | Medium | **Medium** | Commercial | Homepage / services |
| outdoor birthday party kids Mumbai | Low | **Medium** | Transactional | New landing page |
| kids birthday party Vikhroli | Very Low | **Medium** | Transactional | Contact / local page |
| birthday party ideas for 5 year old | Medium | **Medium** | Informational | Blog post |
| how much does a kids birthday party cost Mumbai | Low | **Medium** | Informational | Blog post |
| best venues for kids birthday Mumbai | Medium | **Medium** | Informational | Blog post |
| kids birthday planning checklist | Medium | **Medium** | Informational | Blog post (already exists — needs own URL) |
| birthday return gifts for kids India | Medium | **Medium** | Informational | Blog post (already exists — needs own URL) |
| stress free birthday party Mumbai | Very Low | **Medium** | Commercial | Homepage copy angle |
| kids party host Mumbai | Low | **Low** | Commercial | Services section |
| birthday party Pune kids | Medium | **Low** | Transactional | Future Pune-specific LP |

---

## On-Page Issues by Page

| Page | Issue | Severity | Recommended Fix |
|---|---|---|---|
| **Homepage** | H1 is "Think Birthdays, Think Wondershop." — zero keyword signal | **Critical** | Change to "Mumbai's Most-Loved Kids Birthday Party Experience" or similar |
| **Homepage** | Title missing "Mumbai" or "kids birthday" upfront | High | Lead with keyword: "Kids Birthday Party Mumbai — Wondershop Experiences" |
| **Homepage** | Meta description doesn't open with primary keyword | Medium | Start with "Plan a magical kids birthday party in Mumbai..." |
| **Homepage** | Hero image alt="Wondershop birthday celebration" — generic | Medium | "Kids birthday party Mumbai — themed celebration by Wondershop" |
| **Homepage** | No FAQ section or FAQPage schema | High | Add 5-6 FAQs with schema (cost, lead time, themes, areas served) |
| **Homepage** | No LocalBusiness / Organization schema | **Critical** | Add JSON-LD schema with address, phone, service area, hours |
| **Gallery** | H1 is "Every birthday is a memory we made" — no keyword | High | "Kids Birthday Party Gallery — Mumbai Celebrations by Wondershop" |
| **Gallery** | Title is just "Gallery — Wondershop Experiences" | High | "Birthday Party Gallery Mumbai — Themed Decor & Events | Wondershop" |
| **Gallery** | 24 images named 1.jpg, 2.jpg … 24.jpg | **Critical** | Rename to descriptive slugs: spy-theme-birthday-mumbai.jpg, princess-party-decor.jpg |
| **Gallery** | Images "sana decor pic google v2.jpg", "yuwan spy decor.jpg" have spaces | High | Rename with hyphens; spaces break URLs and confuse crawlers |
| **Gallery** | Alt text for several images is generic ("Birthday decor", "Beautiful birthday decor") | Medium | Use descriptive, keyword-rich alt text for every image |
| **Gallery** | Very thin text content (mostly images); Google has little to index | High | Add a 100-150 word intro paragraph with keyword-rich copy |
| **About Us** | H1 "Built by parents, for parents" — zero keyword signal | High | "Meet the Team Behind Mumbai's Best Kids Birthday Experience" |
| **About Us** | Title is "About Us — Wondershop Experiences" | Medium | "About Wondershop — Mumbai Kids Birthday Party Specialists" |
| **About Us** | Image "google profile cover.png" has spaces in filename | Medium | Rename to "wondershop-team-mumbai.png" |
| **About Us** | H2s ("Our Vision", "Our Mission") have zero SEO value | Low | Weave in keyword phrases naturally where appropriate |
| **Contact** | H1 is "We'd love to hear about your child's birthday" | Medium | "Contact Wondershop — Kids Birthday Party Planner, Mumbai" |
| **Contact** | Meta description mentions channels only, no keyword | High | "Get in touch with Mumbai's top kids birthday party planners..." |
| **Contact** | No LocalBusiness schema with hours, address, serviceArea | **Critical** | Add JSON-LD with full structured address, hours, geo coordinates |
| **Contact** | No embedded Google Map | Low | Embed map for Vikhroli address |
| **Blog** | All 3 articles live on one URL (blogs.html#anchor) | **Critical** | Each article needs its own page: /blogs/spy-theme-birthday-party-guide/ |
| **Blog** | No Article / BlogPosting schema on any article | High | Add JSON-LD Article schema with datePublished, author, headline |
| **Blog** | Blog images reference filenames with spaces | High | Fix filenames and update references |
| **Blog** | No internal linking from blog posts to relevant theme pages | Medium | Add contextual links in each post to the builder / relevant theme sections |
| **All pages** | © 2025 in footer (outdated) | Low | Update to © 2026 |
| **All pages** | No breadcrumb schema | Low | Add BreadcrumbList JSON-LD |

---

## Content Gap Analysis

These are topics competitors rank for (or parents clearly search) that Wondershop has no dedicated content for:

| Topic / Keyword | Why It Matters | Format | Priority | Effort |
|---|---|---|---|---|
| Theme landing pages (Spy, Princess, Unicorn, Dino, Jungle, F1, K-Pop, etc.) | Blue Sparrow, Party Planet rank for "[theme] birthday party Mumbai". Each theme LP can rank independently and drive conversion. | Dedicated page per theme (/spy-theme-birthday-party-mumbai/) | **High** | Moderate (1 page per theme × 10 themes) |
| First birthday party Mumbai | Huge parent search moment; high emotion, high budget. Nobody in Wondershop's content addresses this directly. | Landing page + blog post | **High** | Moderate |
| "How much does a kids birthday party cost in Mumbai" | #1 informational question from budget-conscious parents; can convert to "our packages start at…" | Blog post with pricing context | **High** | Quick (2-3 hrs) |
| "Best birthday party venues for kids in Mumbai" | Informational, drives traffic from undecided parents. Competitors blog about this. | Blog post | **High** | Quick |
| Area/neighbourhood pages | CherishX has city-area pages (Khar, Andheri, etc.). Parents search "birthday party in Bandra". | Location LPs: /kids-birthday-party-bandra/, /powai/, /andheri/ | **Medium** | Moderate per page |
| Birthday party activities for kids (beyond decor) | Parents searching "what activities for kids birthday party" — a gap Wondershop can answer with its DIY/activity offering. | Blog post | **Medium** | Quick |
| Kids birthday party planning checklist | Already written on blogs.html but trapped as an anchor link. Needs its own URL. | Standalone blog page | **High** | Quick (copy already exists) |
| Return gift ideas for kids birthday | Already written. Same fix — needs its own URL. | Standalone blog page | **High** | Quick |
| FAQ page | Competitors have FAQ schema in search results (rich snippets). Wondershop has none. | New /faq.html page with schema | **High** | Quick |
| Pricing / packages page | Parents want to know cost upfront before calling. A transparent pricing page reduces friction and ranks for "birthday party package Mumbai". | New /packages.html page | **Medium** | Moderate |

---

## Technical SEO Checklist

| Check | Status | Details |
|---|---|---|
| Custom domain (not github.io) | **FAIL** | Site lives on `wondershop-exp.github.io` — Google can't build DA for `wondershopexperiences.com`. Fix before anything else. |
| HTTPS | PASS | github.io is served over HTTPS by default |
| sitemap.xml | **FAIL** | No sitemap found. Google has no map of the site's pages. |
| robots.txt | **FAIL** | No robots.txt found. |
| Mobile responsive | PASS | Site uses responsive CSS (observed across pages) |
| LocalBusiness schema | **FAIL** | No JSON-LD schema detected on any page |
| FAQPage schema | **FAIL** | No FAQ schema — missing rich snippet opportunity |
| Article schema on blog | **FAIL** | Blog articles have no schema |
| Image filenames (no spaces) | **FAIL** | Multiple images use spaces and/or sequential numbers (1.jpg–24.jpg) |
| Image alt text | PARTIAL | Some pages have good alt text; gallery has generic alts |
| H1 per page (keyword-targeted) | **FAIL** | Every page has exactly one H1, but none contain target keywords |
| Title tags (keyword-first) | PARTIAL | Titles exist on all pages; keywords are de-prioritised or absent |
| Meta descriptions | PARTIAL | All pages have meta descriptions; keyword placement weak |
| Internal linking (contextual) | PARTIAL | Nav links present; no in-content contextual links between pages |
| Blog URL structure | **FAIL** | All blog content on one URL with anchor fragments |
| Image compression | UNKNOWN | Cannot assess from static fetch; verify with PageSpeed Insights |
| Core Web Vitals | UNKNOWN | Check via Google Search Console / PageSpeed Insights |
| Google Search Console | UNKNOWN | Verify whether site is registered and submitted |
| Google Business Profile | UNKNOWN | Verify GBP is claimed and fully completed for local SEO |

---

## Competitor SEO Comparison

| Dimension | Wondershop | CherishX | Party Planet India | Blue Sparrow |
|---|---|---|---|---|
| Domain type | github.io subdomain ❌ | Custom domain ✅ | Custom domain ✅ | Custom domain ✅ |
| H1 keyword targeting | None on any page ❌ | Strong ✅ | Strong ✅ | Partial ⚠️ |
| Blog / content | 3 articles (single URL) ⚠️ | Extensive, indexed ✅ | Large blog, indexed ✅ | Moderate ✅ |
| Theme landing pages | None ❌ | City × theme pages ✅ | Theme-specific pages ✅ | Partial ✅ |
| Schema markup | None ❌ | Yes ✅ | Yes ✅ | Partial ⚠️ |
| sitemap / robots | None ❌ | Yes ✅ | Yes ✅ | Yes ✅ |
| Image SEO | Spaces in filenames ❌ | Clean URLs ✅ | Mixed ⚠️ | Good ✅ |
| Brand / UX quality | **Best in class ✅** | Generic ⚠️ | Functional ⚠️ | Good ✅ |
| Local area targeting | None ❌ | City-area pages ✅ | Moderate ⚠️ | None ❌ |

---

## Prioritized Action Plan

### Quick Wins — Do This Week

| Action | Expected Impact | Effort |
|---|---|---|
| **1. Point custom domain to the site** — connect `wondershopexperiences.com` to GitHub Pages via CNAME | **Very High** — unlocks all future SEO investment | 30 mins |
| **2. Update H1s on all pages** to include target keywords (see table above) | High — immediate ranking signal improvement | 1 hour |
| **3. Update title tags on Gallery, About, Contact, Blog** to lead with keyword | High | 30 mins |
| **4. Create sitemap.xml** listing all pages and add it to the root | High — Google will discover all pages faster | 1 hour |
| **5. Create robots.txt** (allow all, point to sitemap) | Medium | 15 mins |
| **6. Rename 1.jpg–24.jpg** to descriptive, hyphenated names (spy-birthday-mumbai.jpg, etc.) | High — unlocks Google Image Search traffic | 2-3 hours (rename + update all references in HTML) |
| **7. Fix image filenames with spaces** (sana decor pic.jpg → sana-decor-wondershop.jpg) | High | 30 mins |
| **8. Add LocalBusiness JSON-LD schema** to index.html and contact.html | High — enables rich results for local searches | 1 hour |
| **9. Register in Google Search Console** and submit sitemap | High — required for Google to track your rankings | 30 mins |
| **10. Update © 2025 → © 2026** in footer across all pages | Low | 10 mins |

### Strategic Investments — This Quarter

| Action | Expected Impact | Effort |
|---|---|---|
| **Split blog into individual pages** — /blogs/spy-theme-guide.html, /blogs/return-gifts.html, /blogs/planning-checklist.html | **Very High** — 3 URLs instead of 1; each can rank independently | 1 day |
| **Build 8–10 theme landing pages** — one page per theme (/spy-theme-birthday-party-mumbai/, /princess-birthday-party-mumbai/, etc.) with 300+ words, images, and a clear CTA | **Very High** — long-tail ranking engine; converts searchers with clear intent | 1-2 days |
| **Write "How much does a kids birthday party cost in Mumbai"** blog post with transparent pricing ranges | High — most-searched informational query; converts undecided parents | 3-4 hours |
| **Write "Best venues for kids birthday party in Mumbai"** — covers home, turf, restaurant, banquet with recommendations | High — broad informational query, positions Wondershop as expert | 3-4 hours |
| **Add FAQPage schema** and a visible FAQ section to the homepage | High — FAQ rich snippets appear above competitors in search | 2 hours |
| **Build 3–5 neighbourhood landing pages** (/birthday-party-bandra/, /andheri/, /powai/) | Medium-High — hyperlocal traffic; low competition | 1 day |
| **Create a /packages/ or /pricing/ page** with transparent tier breakdown | Medium — reduces "how much does it cost?" calls and ranks for pricing queries | Half day |
| **Google Business Profile** — claim, complete, and post weekly | High — local pack visibility (the map results above organic) | Ongoing |
| **Add Article schema to each blog post** after splitting | Medium — enables rich snippets for blog posts | 1 hour |
| **Internal linking audit** — add contextual links from each blog post to relevant theme pages and the builder | Medium — passes authority between pages | 2 hours |

---

## Appendix: Suggested H1 Rewrites

| Page | Current H1 | Suggested H1 |
|---|---|---|
| Homepage | "Think Birthdays, Think Wondershop." | "Mumbai's Most-Loved Kids Birthday Party Experience" |
| Gallery | "Every birthday is a memory we made" | "Kids Birthday Party Gallery — Mumbai Celebrations" |
| About Us | "Built by parents, for parents" | "Mumbai's Kids Birthday Specialists — Meet the Wondershop Team" |
| Contact | "We'd love to hear about your child's birthday" | "Plan a Kids Birthday Party in Mumbai — Contact Wondershop" |
| Blog | (none — uses a section heading) | "Birthday Planning Blog — Ideas, Themes & Tips for Mumbai Parents" |

---

## Appendix: Suggested Title Tag Rewrites

| Page | Current Title | Suggested Title |
|---|---|---|
| Homepage | "Wondershop Experiences — Plan Your Child's Dream Birthday" | "Kids Birthday Party Mumbai — Themed Experiences | Wondershop" |
| Gallery | "Gallery — Wondershop Experiences" | "Birthday Party Gallery Mumbai — Themes & Decor | Wondershop" |
| About Us | "About Us — Wondershop Experiences" | "About Wondershop — Mumbai Kids Birthday Party Specialists" |
| Contact | "Contact Us — Wondershop Experiences" | "Contact Wondershop — Kids Birthday Planner Mumbai" |
| Blog | "Birthday Planning Blog — Wondershop Experiences" | "Kids Birthday Planning Blog Mumbai — Wondershop Experiences" |

---

*Audit covers: index.html, gallery.html, about-us.html, contact.html, blogs.html. Pages not audited in detail: builder.html (tool/conversion page), testimonials.html, individual theme pages (none exist yet). Competitor data based on web research July 2026. Volume estimates are relative without a connected SEO tool — connect Ahrefs or Semrush for precise data.*
