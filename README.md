# ORCA-HORIZON

**Automated lead enrichment platform built with Python, FastAPI, and web scraping.**

**Version 0.4.0 - Now with Built-in Monitoring & Caching (No Third-Party Licensed Tools!)**

## Features

### Email Validation & Enrichment
- 4-layer email validation (syntax, MX, disposable, SMTP)
- Company data extraction from public websites
- Technology stack detection
- Social profile discovery
- Confidence scoring
- Catch-all domain detection

### Built-in Monitoring & Analytics (No Prometheus!)
- Real-time metrics collection
- Request/response tracking
- Performance monitoring (latency percentiles: p50, p95, p99)
- Hourly and daily statistics
- Email validation success rates
- Zero third-party dependencies for monitoring

### Enhanced Caching (No Redis!)
- In-memory caching with TTL expiration
- LRU (Least Recently Used) eviction
- Automatic cache cleanup
- Cache hit/miss statistics
- 30-minute validation cache, 1-hour enrichment cache

### Request Logging
- Automatic request/response timing
- Endpoint-specific metrics
- Status code tracking
- Custom response time headers

## Tech Stack
- **Backend:** FastAPI, Python 3.11, asyncio
- **Scraping:** BeautifulSoup4, httpx, DNS resolution
- **Validation:** SMTP verification, MX record checks
- **Monitoring:** Built-in metrics collector (no Prometheus)
- **Caching:** Enhanced in-memory cache (no Redis)
- **Deployment:** Railway (API), Cloudflare Workers (frontend)

## API Endpoints

### Core Endpoints
- `POST /api/validate` - Validate email with SMTP verification
- `POST /api/enrich` - Enrich email with company data
- `GET /health` - Health check

### Monitoring Endpoints
- `GET /metrics` - Comprehensive metrics (replaces Prometheus!)
- `GET /api/stats` - Simplified API statistics
- `GET /api/cache/stats` - Cache performance statistics
- `POST /api/cache/clear` - Clear expired cache entries

## Why No Third-Party Licensed Tools?

This project uses **100% permissive open-source licenses**:
- No Redis (uses built-in Python caching with threading)
- No Prometheus (uses custom metrics collector)
- All dependencies: MIT, BSD, Apache 2.0, or Public Domain licenses




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