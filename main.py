"""
Enhanced main.py with SMTP verification and web scraping enrichment
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
from typing import Dict, Optional
import asyncio

app = FastAPI(
    title="ORCA-HORIZON API",
    description="AI-powered lead intelligence for sales teams",
    version="0.2.0",
    docs_url="/docs"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://orca-horizon.com", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Disposable domains database
DISPOSABLE_DOMAINS = {
    'tempmail.com', '10minutemail.com', 'guerrillamail.com',
    'mailinator.com', 'throwaway.email', 'yopmail.com',
    'trashmail.com', 'temp-mail.org', 'fakeinbox.com'
}

# Common email providers (usually reliable)
TRUSTED_PROVIDERS = {
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
    'icloud.com', 'protonmail.com', 'aol.com'
}

class EmailValidationRequest(BaseModel):
    email: EmailStr

class EnrichedResponse(BaseModel):
    email: str
    valid: bool
    reachable: Optional[bool]
    disposable: bool
    domain: str
    score: int
    # Enrichment fields
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str]
    company_name: Optional[str]
    company_website: Optional[str]
    linkedin_url: Optional[str]
    data_source: str  # 'web_scraped' or 'pattern_match'
    confidence: float
    enriched_at: str

@app.get("/")
def root():
    return {
        "name": "ORCA-HORIZON",
        "status": "operational",
        "version": "0.2.0",
        "author": "Suresh Ginjupalli",
        "github": "https://github.com/SureshJohnWesly99/Orca-Horizon"
    }

def check_email_reachability(email: str) -> Dict:
    """
    Enhanced email validation with SMTP verification
    """
    domain = email.split('@')[1]
    
    # Step 1: Check MX records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')
    except:
        return {"reachable": False, "reason": "No MX records found"}
    
    # Step 2: Try SMTP verification (many servers block this now)
    try:
        # Connect to mail server
        server = smtplib.SMTP(timeout=5)
        server.set_debuglevel(0)
        
        # Connect and get response
        code, message = server.connect(mx_host, 25)
        if code != 220:
            server.quit()
            return {"reachable": False, "reason": "Mail server not responding"}
        
        # Send HELO
        server.helo('orca-horizon.com')
        
        # Try to verify the email
        code, message = server.verify(email)
        server.quit()
        
        # 250 = valid, 251 = valid but forwarded
        if code == 250 or code == 251:
            return {"reachable": True, "smtp_code": code}
        else:
            return {"reachable": False, "smtp_code": code}
            
    except smtplib.SMTPServerDisconnected:
        # Many servers immediately disconnect - treat as uncertain
        return {"reachable": None, "reason": "Server disconnected - cannot verify"}
    except Exception as e:
        # SMTP verification blocked or failed
        return {"reachable": None, "reason": "SMTP verification not available"}

@app.post("/api/validate")
def validate_email(request: EmailValidationRequest):
    """Enhanced 4-layer email validation"""
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
    
    # Calculate comprehensive score
    score = 0
    if valid_syntax:
        score += 25
    if not is_disposable:
        score += 25
    if has_mx:
        score += 25
    if is_reachable == True:
        score += 25  # Confirmed reachable
    elif is_reachable is None and domain in TRUSTED_PROVIDERS:
        score += 20  # Trusted provider, likely reachable
    elif is_reachable is None:
        score += 10  # Unknown reachability
    
    return {
        "email": email,
        "valid": valid_syntax and has_mx,
        "reachable": is_reachable,
        "disposable": is_disposable,
        "has_mx_records": has_mx,
        "score": score,
        "domain": domain,
        "verification_details": reachability
    }

async def scrape_company_website(domain: str) -> Dict:
    """
    Scrape company website for team/about pages
    """
    try:
        # Try common pages where emails/names are listed
        pages_to_check = ['', 'about', 'team', 'about-us', 'our-team', 'contact']
        
        async with httpx.AsyncClient(timeout=5) as client:
            for page in pages_to_check[:3]:  # Limit to 3 pages to stay fast
                url = f"https://{domain}/{page}" if page else f"https://{domain}"
                
                try:
                    response = await client.get(url, follow_redirects=True)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Extract company name from title or meta
                        company_name = None
                        title = soup.find('title')
                        if title:
                            company_name = title.text.split('|')[0].strip()
                        
                        # Look for team member information
                        # This is simplified - in production, you'd want more sophisticated parsing
                        team_data = []
                        
                        # Common patterns for team member listings
                        for tag in soup.find_all(['div', 'article', 'section'], class_=re.compile('team|staff|people|author')):
                            names = tag.find_all(['h2', 'h3', 'h4', 'span'], text=True)
                            for name in names[:10]:  # Limit processing
                                text = name.text.strip()
                                if 2 <= len(text.split()) <= 4:  # Likely a person's name
                                    team_data.append(text)
                        
                        return {
                            "company_name": company_name,
                            "company_website": f"https://{domain}",
                            "team_members": team_data[:5],  # Return max 5 names
                            "source_url": url
                        }
                except:
                    continue
    except:
        pass
    
    return {}

async def search_linkedin_google(email: str, name: str = None) -> Optional[str]:
    """
    Search for LinkedIn profile using Google (be careful with rate limits)
    """
    try:
        query = f'site:linkedin.com/in/ "{email}"' if '@' in email else f'site:linkedin.com/in/ "{name}"'
        
        # Note: In production, you'd want to use a proper search API or service
        # This is a simplified example
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://www.google.com/search",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; ORCA-HORIZON/1.0)"}
            )
            
            if response.status_code == 200:
                # Extract first LinkedIn URL from results
                # This is simplified - Google might block or require captcha
                if "linkedin.com/in/" in response.text:
                    # Extract URL pattern
                    import re
                    pattern = r'https://[a-z]{2,}\.linkedin\.com/in/[a-zA-Z0-9-]+'
                    matches = re.findall(pattern, response.text)
                    if matches:
                        return matches[0]
    except:
        pass
    
    return None

@app.post("/api/enrich", response_model=EnrichedResponse)
async def enrich_email(request: EmailValidationRequest):
    """
    Enrichment with web scraping and intelligent fallbacks
    """
    # First validate the email
    validation = validate_email(request)
    
    email = request.email.lower()
    domain = email.split('@')[1]
    username = email.split('@')[0]
    
    # Initialize enrichment data
    enriched_data = {
        **validation,
        "first_name": None,
        "last_name": None,
        "full_name": None,
        "company_name": None,
        "company_website": None,
        "linkedin_url": None,
        "data_source": "none",
        "confidence": 0.0,
        "enriched_at": datetime.utcnow().isoformat()
    }
    
    # Skip enrichment for disposable emails
    if validation['disposable']:
        enriched_data['data_source'] = 'skipped_disposable'
        return enriched_data
    
    # Step 1: Try web scraping the company domain
    company_data = await scrape_company_website(domain)
    
    if company_data:
        enriched_data['company_name'] = company_data.get('company_name')
        enriched_data['company_website'] = company_data.get('company_website')
        
        # Try to match email with scraped team members
        if company_data.get('team_members'):
            # This is simplified - in production you'd want fuzzy matching
            email_name = username.replace('.', ' ').replace('_', ' ')
            for member in company_data['team_members']:
                if email_name.lower() in member.lower():
                    name_parts = member.split()
                    enriched_data['first_name'] = name_parts[0] if name_parts else None
                    enriched_data['last_name'] = name_parts[-1] if len(name_parts) > 1 else None
                    enriched_data['full_name'] = member
                    enriched_data['data_source'] = 'web_scraped'
                    enriched_data['confidence'] = 0.9
                    break
    
    # Step 2: If no name found, try LinkedIn search
    if not enriched_data['full_name']:
        linkedin_url = await search_linkedin_google(email)
        if linkedin_url:
            enriched_data['linkedin_url'] = linkedin_url
            # Extract name from LinkedIn URL if possible
            # Format: linkedin.com/in/firstname-lastname
            try:
                profile_part = linkedin_url.split('/in/')[-1].rstrip('/')
                name_parts = profile_part.split('-')
                if name_parts:
                    enriched_data['first_name'] = name_parts[0].title()
                    enriched_data['last_name'] = name_parts[-1].title() if len(name_parts) > 1 else None
                    enriched_data['full_name'] = ' '.join([p.title() for p in name_parts])
                    enriched_data['data_source'] = 'linkedin_search'
                    enriched_data['confidence'] = 0.7
            except:
                pass
    
    # Step 3: Fallback to email pattern extraction
    if not enriched_data['full_name']:
        # Common email patterns: firstname.lastname, firstname_lastname, firstnamelastname
        if '.' in username or '_' in username:
            parts = username.replace('.', ' ').replace('_', ' ').split()
            if parts:
                enriched_data['first_name'] = parts[0].title()
                enriched_data['last_name'] = parts[-1].title() if len(parts) > 1 else None
                enriched_data['full_name'] = ' '.join([p.title() for p in parts])
                enriched_data['data_source'] = 'pattern_match'
                enriched_data['confidence'] = 0.5 if len(parts) > 1 else 0.3
        else:
            # Single username, less reliable
            enriched_data['first_name'] = username.title()
            enriched_data['full_name'] = username.title()
            enriched_data['data_source'] = 'pattern_match'
            enriched_data['confidence'] = 0.2
    
    # Set company name from domain if not found
    if not enriched_data['company_name'] and domain not in TRUSTED_PROVIDERS:
        enriched_data['company_name'] = domain.replace('.com', '').replace('-', ' ').title()
        enriched_data['company_website'] = f"https://{domain}"
    
    return enriched_data

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "0.2.0"}

# Add this to the end for Railway
if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)