# ORCA-HORIZON

**Automated lead enrichment platform built with Python, FastAPI, and web scraping.**

## Features
- 4-layer email validation (syntax, MX, disposable, SMTP)
- Company data extraction from public websites
- Technology stack detection
- Social profile discovery
- Confidence scoring

## Tech Stack
- **Backend:** FastAPI, Python 3.11, asyncio
- **Scraping:** BeautifulSoup4, httpx, DNS resolution
- **Validation:** SMTP verification, MX record checks
- **Deployment:** Railway (API), Cloudflare Workers (frontend)




## Limitations
- Works best on tech companies with public team pages
- Some sites have anti-scraping protection (Cloudflare, etc.)
- SMTP verification limited by rate limits
- No JavaScript rendering (sites requiring JS may fail)

## Demo
Live demo: https://orca-horizon.com

## Future Enhancements
- Add AI-powered lead scoring
- Implement database for lead storage
- Add batch CSV processing
- Integrate with CRM systems