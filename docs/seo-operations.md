# Public website SEO operations

## Release checklist

1. Configure the production `PUBLIC_SITE_URL` and deploy.
2. Confirm the homepage returns one H1, a canonical URL, unique title and
   description, Open Graph metadata, and valid Hospital JSON-LD.
3. Confirm private pages and APIs return `X-Robots-Tag: noindex`.
4. Validate `/robots.txt` and `/sitemap.xml` on the public hostname.
5. Verify the domain property in Google Search Console using the authorized
   account. If HTML-token verification is selected, store the issued token in
   `GOOGLE_SITE_VERIFICATION`; never commit it.
6. Submit the sitemap and request homepage inspection. Record the release date
   and monitor indexing errors rather than claiming immediate indexing.
7. Run Lighthouse/PageSpeed on representative mobile and desktop connections.
   Track LCP, CLS and INP field data after enough real traffic exists.

## Ethical backlink and local discovery strategy

- Complete and maintain the hospital's Google Business Profile with consistent
  name, address, phone, hours, and the canonical website URL.
- Seek accurate listings in recognized healthcare, professional-association,
  insurer/TPA, and local-government directories where the hospital qualifies.
- Ask genuine partners, community health programs, and referring organizations
  to link to useful, relevant hospital resources.
- Publish clinically reviewed, original patient education and service guides
  that answer local patient questions and can earn editorial links.
- Periodically audit referring domains and reclaim legitimate broken or outdated
  links after public URL changes.

Do not buy links, exchange links at scale, automate directory submissions,
create fake reviews, or use private blog networks. External outreach requires
explicit organizational approval and must not disclose patient information.

## Measurement

Use Search Console to report indexed pages, impressions, clicks, CTR, and
average position by date and query. Use web analytics for consent-compliant
engagement measurement. Ranking and clicks are outcomes measured after release,
not acceptance criteria that application code can guarantee.
