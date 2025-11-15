"""
ORCA-HORIZON: AI-Powered Lead Intelligence
Author: Suresh Ginjupalli
Portfolio Project
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import re
from typing import Dict

app = FastAPI(
    title="ORCA-HORIZON API",
    description="AI-powered lead intelligence for sales teams",
    version="0.1.0-beta",
    docs_url="/docs"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://orca-horizon.com", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class EmailValidationRequest(BaseModel):
    email: EmailStr

@app.get("/")
def root():
    return {
        "name": "ORCA-HORIZON",
        "status": "operational",
        "author": "Suresh Ginjupalli",
        "github": "https://github.com/SureshJohnWesly99/Orca-Horizon"
    }

@app.post("/api/validate")
def validate_email(request: EmailValidationRequest):
    """3-layer email validation"""
    email = request.email.lower()
    domain = email.split('@')[1]
    
    # Layer 1: Syntax check
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    valid = bool(re.match(pattern, email))
    
    # Layer 2: Disposable check
    disposable_domains = ['tempmail.com', '10minutemail.com', 'guerrillamail.com']
    is_disposable = domain in disposable_domains
    
    score = 95 if valid and not is_disposable else 30
    
    return {
        "email": email,
        "valid": valid,
        "disposable": is_disposable,
        "score": score,
        "domain": domain
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}