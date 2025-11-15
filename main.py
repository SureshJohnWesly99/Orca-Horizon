"""
Enhanced ORCA-HORIZON API with SMTP verification and web scraping enrichment
Version: 0.3.0
Author: Suresh Ginjupalli
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import re
import dns.resolver
import socket
import smtplib
import httpx
from bs4 import BeautifulSoup
import hashlib
import json
from datetime import datetime
from typing import Dict, Optional, List
import asyncio
import time
import random
from functools import lru_cache

app = FastAPI(
    title="ORCA-HORIZON API",
    description="AI-powered lead intelligence for sales teams",
    version="0.3.0",
    docs_url="/docs"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://orca-horizon.com", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

# Disposable domains database
DISPOSABLE_DOMAINS = {
    'tempmail.com', '10minutemail.com', 'guerrillamail.com',
    'mailinator.com', 'throwaway.email', 'yopmail.com',
    'trashmail.com', 'temp-mail.org', 'fakeinbox.com',
    'temp-mail.io', 'minuteinbox.com', 'getairmail.com'
}

# Common email providers (usually reliable)
TRUSTED_PROVIDERS = {
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
    'icloud.com', 'protonmail.com', 'aol.com', 'live.com',
    'msn.com', 'me.com', 'mac.com'
}

# Rate limiting cache for SMTP checks
SMTP_RATE_LIMIT_CACHE = {}

# User agents for web scraping
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
]

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class EmailValidationRequest(BaseModel):
    email: EmailStr

class EnrichedResponse(BaseModel):
    email: str
    valid: bool
    reachable: Optional[bool]
    disposable: bool
    domain: str
    score: int
    is_catch_all: Optional[bool] = False
    # Enrichment fields
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_size: Optional[str] = None
    company_location: Optional[str] = None
    company_founded: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    technologies_used: Optional[List[str]] = []
    social_profiles: Optional[Dict] = {}
    data_source: str
    confidence: float
    enriched_at: str

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_random_headers():
    """Generate realistic browser headers"""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

@lru_cache(maxsize=500)
def get_mx_record_cached(domain: str):
    """Cache MX lookups to reduce DNS queries"""
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        return str(sorted(mx_records, key=lambda r: r.preference)[0].exchange).rstrip('.')
    except:
        return None

def check_catch_all(mx_host: str, domain: str) -> bool:
    """Check if domain accepts all emails (catch-all)"""
    random_email = f'test{random.randint(100000, 999999)}@{domain}'
    
    try:
        server = smtplib.SMTP(timeout=5)
        server.connect(mx_host, 25)
        server.helo('orca-horizon.com')
        server.mail('verify@orca-horizon.com')
        code, _ = server.rcpt(random_email)
        try:
            server.quit()
        except:
            pass
        return code == 250  # If accepts random email, it's catch-all
    except:
        return False

def check_email_reachability(email: str) -> Dict:
    """
    Enhanced email validation with proper SMTP verification
    """
    domain = email.split('@')[1]
    
    # CRITICAL: Rate limit per domain to avoid blacklisting
    current_time = time.time()
    if domain in SMTP_RATE_LIMIT_CACHE:
        time_since_last = current_time - SMTP_RATE_LIMIT_CACHE[domain]
        if time_since_last < 2.0:  # Minimum 2 seconds between checks
            time.sleep(2.0 - time_since_last + random.uniform(0.5, 1.5))
    SMTP_RATE_LIMIT_CACHE[domain] = time.time()
    
    # Step 1: Check MX records (cached)
    mx_host = get_mx_record_cached(domain)
    if not mx_host:
        return {"reachable": False, "reason": "No MX records found"}
    
    # Step 2: Detect catch-all domains FIRST (saves unnecessary checks)
    is_catch_all = check_catch_all(mx_host, domain)
    
    # Step 3: Try SMTP verification with better error handling
    try:
        server = smtplib.SMTP(timeout=10)
        server.set_debuglevel(0)
        
        # Connect with retry logic
        for attempt in range(2):
            try:
                code, message = server.connect(mx_host, 25)
                if code == 220:
                    break
            except:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise
        
        # Use YOUR domain for HELO (important!)
        server.helo('orca-horizon.com')
        
        # Use a legitimate sender address
        server.mail('verify@orca-horizon.com')
        
        # Check the actual email
        code, message = server.rcpt(email)
        
        # ALWAYS quit properly
        try:
            server.quit()
        except:
            pass
        
        # Interpret response codes properly
        if code == 250:
            return {
                "reachable": True, 
                "is_catch_all": is_catch_all,
                "confidence": 50 if is_catch_all else 95,
                "smtp_code": code
            }
        elif code in [450, 451, 452]:  # Greylisting
            return {
                "reachable": True,  # Likely valid
                "reason": "Greylisted - likely valid",
                "confidence": 70,
                "smtp_code": code,
                "is_catch_all": is_catch_all
            }
        elif code in [550, 551, 553]:
            return {"reachable": False, "reason": "Invalid mailbox", "smtp_code": code}
        else:
            return {"reachable": None, "reason": f"Unknown response: {code}", "is_catch_all": is_catch_all}
            
    except smtplib.SMTPServerDisconnected:
        # Many servers disconnect immediately - this is NORMAL
        return {"reachable": None, "reason": "Server disconnected - cannot verify", "is_catch_all": is_catch_all}
    except Exception as e:
        return {"reachable": None, "reason": f"Verification not available: {str(e)[:50]}", "is_catch_all": is_catch_all}

# =============================================================================
# WEB SCRAPING FUNCTIONS
# =============================================================================

def extract_homepage_data(soup, domain):
    """Extract data from homepage"""
    data = {'homepage_html': str(soup)[:5000]}  # Store some HTML for tech detection
    
    # Company name from title or meta
    title_tag = soup.find('title')
    if title_tag:
        # Clean common patterns: "Company Name | Tagline" -> "Company Name"
        data['company_name'] = title_tag.text.split('|')[0].split('-')[0].strip()
    
    # Meta description
    meta_desc = soup.find('meta', {'name': 'description'})
    if meta_desc:
        data['description'] = meta_desc.get('content', '')
    
    # Social links
    social_patterns = {
        'linkedin': r'linkedin\.com/company/([^/\s"]+)',
        'twitter': r'twitter\.com/([^/\s"]+)',
        'facebook': r'facebook\.com/([^/\s"]+)',
        'github': r'github\.com/([^/\s"]+)'
    }
    
    social_links = {}
    for platform, pattern in social_patterns.items():
        match = re.search(pattern, str(soup))
        if match:
            social_links[platform] = match.group(0)
    
    if social_links:
        data['social_links'] = social_links
    
    return data

def extract_about_data(soup):
    """Extract data from about page"""
    data = {}
    
    # Look for employee count
    text = soup.get_text().lower()
    employee_patterns = [
        r'(\d+[\+\-]?)\s*employees?',
        r'team\s+of\s+(\d+)',
        r'(\d+)\s+team\s+members?',
        r'(\d+)\s+people'
    ]
    
    for pattern in employee_patterns:
        match = re.search(pattern, text)
        if match:
            data['employee_count'] = match.group(1)
            break
    
    # Look for founded year
    year_patterns = [
        r'founded\s+(?:in\s+)?(\d{4})',
        r'since\s+(\d{4})',
        r'established\s+(?:in\s+)?(\d{4})'
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['founded_year'] = match.group(1)
            break
    
    # Look for location
    location_patterns = [
        r'headquartered?\s+in\s+([^.]+)',
        r'based\s+in\s+([^.]+)',
        r'located?\s+in\s+([^.]+)'
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['location'] = match.group(1).strip()[:50]  # Limit length
            break
    
    return data

def extract_team_data(soup):
    """Extract team member information"""
    team_members = []
    
    # Common team member containers
    member_selectors = [
        '.team-member',
        '.staff-member',
        '.person',
        'article.team',
        'div[class*="team"]',
        'div[class*="staff"]'
    ]
    
    for selector in member_selectors:
        members = soup.select(selector)[:20]  # Limit to 20 members
        
        for member in members:
            person = {}
            
            # Name extraction
            name_tags = member.find_all(['h2', 'h3', 'h4', 'h5', 'span'], class_=re.compile('name|title'))
            if name_tags:
                person['name'] = name_tags[0].get_text().strip()
            
            # Title extraction  
            title_tags = member.find_all(['p', 'span', 'div'], class_=re.compile('title|role|position'))
            if title_tags:
                person['title'] = title_tags[0].get_text().strip()
            
            # Email extraction
            email_link = member.find('a', href=re.compile(r'^mailto:'))
            if email_link:
                person['email'] = email_link['href'].replace('mailto:', '')
            
            # LinkedIn extraction
            linkedin_link = member.find('a', href=re.compile(r'linkedin\.com'))
            if linkedin_link:
                person['linkedin'] = linkedin_link['href']
            
            if person.get('name'):
                team_members.append(person)
    
    return team_members

def detect_technologies(html_content):
    """Detect technologies used by the website"""
    technologies = []
    
    tech_signatures = {
        # CMS
        'WordPress': r'wp-content|wordpress',
        'Shopify': r'cdn\.shopify\.com|Shopify\.',
        'Wix': r'wixsite\.com|wix\.com',
        'Squarespace': r'squarespace\.com',
        
        # JavaScript Frameworks
        'React': r'react|__REACT',
        'Vue.js': r'vue\.js|__VUE',
        'Angular': r'ng-version|angular',
        'Next.js': r'__NEXT_DATA__',
        
        # Analytics
        'Google Analytics': r'google-analytics\.com|gtag\(|ga\(',
        'Google Tag Manager': r'googletagmanager\.com',
        'Segment': r'segment\.com|analytics\.js',
        'Mixpanel': r'mixpanel\.com',
        
        # Marketing Tools
        'HubSpot': r'hubspot\.com|hs-scripts',
        'Intercom': r'intercom\.io',
        'Drift': r'drift\.com',
        
        # E-commerce
        'Stripe': r'stripe\.com',
        'PayPal': r'paypal\.com'
    }
    
    for tech, pattern in tech_signatures.items():
        if re.search(pattern, html_content, re.IGNORECASE):
            technologies.append(tech)
    
    return technologies[:10]  # Limit to top 10

async def scrape_company_website(domain: str) -> Dict:
    """
    Enhanced company scraping with multiple data points
    """
    company_data = {
        'domain': domain,
        'company_name': None,
        'description': None,
        'employee_count': None,
        'industry': None,
        'location': None,
        'founded_year': None,
        'technologies': [],
        'social_links': {},
        'team_members': []
    }
    
    # Pages to check for maximum data extraction
    pages_to_scrape = [
        ('', 'main'),  # Homepage
        ('about', 'about'),
        ('about-us', 'about'),
        ('team', 'team'),
        ('our-team', 'team'),
        ('people', 'team'),
        ('contact', 'contact'),
        ('careers', 'careers')
    ]
    
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for page_path, page_type in pages_to_scrape[:4]:  # Limit to 4 pages
            url = f"https://{domain}/{page_path}" if page_path else f"https://{domain}"
            
            # Add delay to be respectful
            await asyncio.sleep(random.uniform(1, 2))
            
            try:
                response = await client.get(
                    url,
                    headers=get_random_headers()
                )
                
                if response.status_code != 200:
                    continue
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract based on page type
                if page_type == 'main':
                    company_data.update(extract_homepage_data(soup, domain))
                elif page_type == 'about':
                    company_data.update(extract_about_data(soup))
                elif page_type == 'team':
                    company_data['team_members'].extend(extract_team_data(soup))
                    
            except Exception as e:
                print(f"Error scraping {url}: {e}")
                continue
    
    # Detect technologies from homepage HTML
    if company_data.get('homepage_html'):
        company_data['technologies'] = detect_technologies(company_data['homepage_html'])
    
    return company_data

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    return {
        "name": "ORCA-HORIZON",
        "status": "operational",
        "version": "0.3.0",
        "author": "Suresh Ginjupalli",
        "github": "https://github.com/SureshJohnWesly99/Orca-Horizon",
        "description": "AI-powered lead intelligence for sales teams"
    }

@app.post("/api/validate")
def validate_email(request: EmailValidationRequest):
    """Enhanced 4-layer email validation with catch-all detection"""
    email = request.email.lower()
    domain = email.split('@')[1]
    
    # Layer 1: Syntax validation
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    valid_syntax = bool(re.match(pattern, email))
    
    # Layer 2: Disposable check
    is_disposable = domain in DISPOSABLE_DOMAINS
    
    # Layer 3: MX record check
    has_mx = False
    try:
        dns.resolver.resolve(domain, 'MX')
        has_mx = True
    except:
        has_mx = False
    
    # Layer 4: Reachability check (SMTP)
    reachability = check_email_reachability(email)
    is_reachable = reachability.get('reachable')
    is_catch_all = reachability.get('is_catch_all', False)
    
    # Calculate comprehensive score
    score = 0
    if valid_syntax:
        score += 25
    if not is_disposable:
        score += 25
    if has_mx:
        score += 25
    
    # Better scoring based on SMTP results
    if is_reachable == True:
        if is_catch_all:
            score += 15  # Lower score for catch-all
        else:
            score += 25  # Full score for verified
    elif is_reachable is None:
        score += 10  # Unknown is better than invalid
    
    return {
        "email": email,
        "valid": valid_syntax and has_mx,
        "reachable": is_reachable,
        "disposable": is_disposable,
        "has_mx_records": has_mx,
        "score": score,
        "domain": domain,
        "is_catch_all": is_catch_all,
        "verification_details": reachability
    }

@app.post("/api/enrich", response_model=EnrichedResponse)
async def enrich_email(request: EmailValidationRequest):
    """
    Enhanced enrichment with better company data extraction
    """
    # First validate with the improved function
    validation = validate_email(request)
    
    email = request.email.lower()
    domain = email.split('@')[1]
    username = email.split('@')[0]
    
    enriched_data = {
        **validation,
        "enriched_at": datetime.utcnow().isoformat()
    }
    
    # Skip enrichment for disposable/invalid emails
    if validation['disposable'] or not validation['valid']:
        enriched_data['data_source'] = 'skipped_invalid'
        enriched_data['confidence'] = 0.0
        return enriched_data
    
    # Extract names from email pattern
    if '.' in username or '_' in username or '-' in username:
        parts = username.replace('.', ' ').replace('_', ' ').replace('-', ' ').split()
        if parts:
            enriched_data['first_name'] = parts[0].title()
            enriched_data['last_name'] = parts[-1].title() if len(parts) > 1 else None
            enriched_data['full_name'] = ' '.join([p.title() for p in parts])
            enriched_data['confidence'] = 0.6 if len(parts) > 1 else 0.4
    else:
        enriched_data['first_name'] = username.title()
        enriched_data['full_name'] = username.title()
        enriched_data['confidence'] = 0.3
    
    # Enhanced company scraping
    if domain not in TRUSTED_PROVIDERS:
        try:
            company_data = await scrape_company_website(domain)
            
            enriched_data['company_name'] = company_data.get('company_name')
            enriched_data['company_website'] = f"https://{domain}"
            
            # Add new fields
            enriched_data['company_size'] = company_data.get('employee_count')
            enriched_data['company_location'] = company_data.get('location')
            enriched_data['company_founded'] = company_data.get('founded_year')
            enriched_data['technologies_used'] = company_data.get('technologies', [])
            enriched_data['social_profiles'] = company_data.get('social_links', {})
            
            # Try to match email with scraped team members
            if company_data.get('team_members'):
                email_lower = email.lower()
                for member in company_data['team_members']:
                    if member.get('email', '').lower() == email_lower:
                        # Found exact match!
                        enriched_data['full_name'] = member.get('name')
                        enriched_data['job_title'] = member.get('title')
                        enriched_data['linkedin_url'] = member.get('linkedin')
                        enriched_data['data_source'] = 'web_scraped_verified'
                        enriched_data['confidence'] = 0.95
                        break
                    elif member.get('name'):
                        # Try fuzzy matching
                        member_name_parts = member['name'].lower().split()
                        if enriched_data.get('first_name', '').lower() in member_name_parts:
                            enriched_data['job_title'] = member.get('title')
                            enriched_data['linkedin_url'] = member.get('linkedin')
                            enriched_data['confidence'] = 0.8
            
            # Set data source
            if not enriched_data.get('data_source'):
                enriched_data['data_source'] = 'web_scraped' if company_data.get('company_name') else 'pattern_match'
                
        except Exception as e:
            print(f"Scraping error: {e}")
            enriched_data['data_source'] = 'pattern_match'
    else:
        enriched_data['data_source'] = 'pattern_match'
    
    # Calculate overall confidence score
    if enriched_data.get('data_source') == 'web_scraped_verified':
        enriched_data['confidence'] = 0.95
    elif enriched_data.get('data_source') == 'web_scraped':
        enriched_data['confidence'] = 0.7
    elif validation.get('is_catch_all'):
        enriched_data['confidence'] = min(enriched_data.get('confidence', 0.5), 0.5)
    
    # Set company name from domain if not found
    if not enriched_data.get('company_name') and domain not in TRUSTED_PROVIDERS:
        enriched_data['company_name'] = domain.replace('.com', '').replace('-', ' ').title()
        enriched_data['company_website'] = f"https://{domain}"
    
    return enriched_data

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": "0.3.0",
        "timestamp": datetime.utcnow().isoformat()
    }

# =============================================================================
# SERVER STARTUP
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)