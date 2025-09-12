import os
import re
import json
import time
import pytz
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from collections import Counter
from typing import Optional, List, Set, Dict, Tuple
from openpyxl import Workbook
from openpyxl.styles import Alignment
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from urllib.parse import urlparse


# Load environment variables early
load_dotenv()

API_KEY = os.getenv("API_KEY")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
INTERCOM_PROD_KEY = os.getenv("INTERCOM_PROD_KEY")


# MetaMask Areas and their related subcategory columns captured in the XLSX output
# Note: We retain these for backward compatibility, but XLSX will now include ALL custom attributes dynamically.
CATEGORY_HEADERS = {
    "Card": [
        "MM Card Issue",
        "MM Card Partner issue",
        "Dashboard Issue",
        "KYC Issue",
        "Dashboard Issue - Subcategory",
        "KYC Issue - Subcategory",
    ],
    "Dashboard": [],
    "Ramps": ["Buy or Sell", "Buy issue", "Sell issue"],
    "SDK": [],
    "Security": [],
    "Snaps": ["Snaps Category"],
    "Staking": [
        "Staking Feature",
        "Validator Staking Issue",
        "Pooled Staking Issue",
        "Liquid Staking Issue",
        "Third Party Staking",
        "Bug ID",
        "Refund amount (USD)",
        "Refund Provided",
        "Withdrawals",
        "Managing Staked Tokens",
        "User Training",
        "Failed Transaction",
        "Liquid Staking Provider",
        "Staking Token Type",
        "Staking Platform",
    ],
    "Swaps": ["Swaps issue"],
    "Wallet": ["Wallet issue"],
    "Wallet API": [],
}


OUTPUT_DIR = "output_files"
INSIGHTS_DIR = "Outputs"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(INSIGHTS_DIR, exist_ok=True)


# Runtime/behavior configuration (override via env)
MAX_RUNTIME_SEC = int(os.getenv("MAX_RUNTIME_SEC", "43200"))  # default 12 hours
INFERENCE_SCAN_LIMIT = int(os.getenv("INFERENCE_SCAN_LIMIT", "500"))  # cap inference scans
DETAIL_FETCH_TIMEOUT = int(os.getenv("DETAIL_FETCH_TIMEOUT", "20"))
SEARCH_REQUEST_TIMEOUT = int(os.getenv("SEARCH_REQUEST_TIMEOUT", "60"))
LOG_EVERY = int(os.getenv("LOG_EVERY", "200"))
SEARCH_PER_PAGE = int(os.getenv("SEARCH_PER_PAGE", "150"))

STOP_WORDS = set(
    [
        "the",
        "and",
        "of",
        "to",
        "a",
        "in",
        "for",
        "on",
        "with",
        "is",
        "this",
        "that",
        "it",
        "as",
        "was",
        "but",
        "are",
        "by",
        "or",
        "be",
        "at",
        "an",
        "not",
        "can",
        "if",
        "from",
        "about",
        "we",
        "you",
        "your",
        "so",
        "which",
        "there",
        "all",
        "will",
        "what",
        "has",
        "have",
        "do",
        "does",
        "had",
        "i",
        "im",
        "ive",
        "amp",
        "•",
        "–",
        "—",
        "-",
        "_",
        "meta",
        "mask",
        "metamask",
        "customer",
        "user",
        "their",
        "no",
        "available",
        "summary",
        "question",
        "agent",
    ]
)


TZ_NY = pytz.timezone("America/New_York")

# Keywords to detect technical escalations in transcripts
ESCALATION_KEYWORDS = [
    "escalating to technical support",
    "escalated to technical support",
    "escalated your issue",
    "handing this to technical support",
    "forwarding to technical team",
    "escalating this issue",
    "escalated to tier 2",
    "escalating to tier 2",
    "our technical support team",
    "will be reviewed by tech support",
]

# Disallowed phrases to avoid low-signal insights
DISALLOWED_PHRASE_PATTERNS = [
    re.compile(r"\bhelp center\b", re.IGNORECASE),
    re.compile(r"\bcenter bot\b", re.IGNORECASE),
    re.compile(r"\bbot conversation\b", re.IGNORECASE),
    re.compile(r"\bconversation rating\b", re.IGNORECASE),
]

# ---------------------------
# Security-specific analysis helpers
# ---------------------------

# Reasons for compromises (binary per conversation)
SECURITY_COMPROMISE_REASON_PATTERNS: dict[str, list[str]] = {
    "Seed phrase exposed/shared": [r"seed\s+phrase", r"secret\s+recovery\s+phrase", r"12[-\s]?word"],
    "Private key leaked/imported": [r"private\s+key", r"export\s+key", r"imported\s+account"],
    "Signed malicious transaction": [r"signed?\s+(a\s+)?(malicious|phishing)\s+tx|transaction", r"permit\s*\(|permit2", r"signature\s+request"],
    "Approval to malicious contract": [r"approve|approval|allowance", r"revoke(\s+|\-)?(cash|tool|dot)"],
    "Phishing website / fake support": [r"phish|fake\s+(site|support)|impersonat|scam\s+site", r"telegram|whatsapp|discord\s+support"],
    "Malware/clipboard hijack": [r"malware|virus|trojan|clipboard|keylog(ger)?|stealer"],
    "SIM swap or email compromise": [r"sim\s+swap|phone\s+number\s+port|email\s+compromis|mailbox\s+hacked"],
}

# Benign/common domains to ignore from phishing extraction
SECURITY_BENIGN_DOMAINS: set[str] = set([
    "metamask.io",
    "support.metamask.io",
    "consensys.net",
    "intercom.io",
    "zendesk.com",
    "docs.metamask.io",
])

def _count_binary_reason_hits(texts: list[str], pattern_map: dict[str, list[str]]) -> list[tuple[str, int]]:
    reason_to_count: dict[str, int] = {k: 0 for k in pattern_map.keys()}
    compiled: dict[str, re.Pattern] = {k: re.compile("|".join(v), flags=re.IGNORECASE) for k, v in pattern_map.items()}
    for t in texts:
        t0 = t or ""
        for reason, patt in compiled.items():
            if patt.search(t0):
                reason_to_count[reason] += 1
    # Sort by count desc then name
    ranked = sorted(reason_to_count.items(), key=lambda kv: (-kv[1], kv[0]))
    # drop zeroes
    return [(k, v) for k, v in ranked if v > 0]

def _extract_domains_from_text(text: str) -> set[str]:
    found: set[str] = set()
    if not text:
        return found
    # url-like tokens and bare domains
    for match in re.findall(r"https?://[^\s]+|\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", text, flags=re.IGNORECASE):
        dom = match
        try:
            if match.startswith("http"):
                parsed = urlparse(match)
                dom = parsed.netloc or parsed.path
            # strip path if any
            dom = dom.split("/")[0]
            dom = dom.lower()
            if dom.startswith("www."):
                dom = dom[4:]
            # crude noise filter for emails
            if "@" in dom:
                continue
            # basic TLD check
            if "." not in dom:
                continue
            found.add(dom)
        except Exception:
            continue
    return found

def _top_suspicious_domains(texts: list[str], top_n: int = 5) -> list[tuple[str, int]]:
    domain_counts: dict[str, int] = {}
    for t in texts:
        domains = _extract_domains_from_text(t or "")
        # count once per conversation per domain
        for d in domains:
            if d in SECURITY_BENIGN_DOMAINS:
                continue
            domain_counts[d] = domain_counts.get(d, 0) + 1
    ranked = sorted(domain_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:top_n]

# ---------------------------
# Security taxonomy (user-provided terms)
# ---------------------------

SECURITY_TAXONOMY: dict[str, list[str]] = {
    # Reason
    "Reason|Ecosystem exploit": [r"ecosystem\s+exploit"],
    "Reason|Unknown": [r"unknown"],
    "Reason|Unintended contract interaction": [r"unintended\s+contract\s+interaction"],
    "Reason|No info": [r"no\s+info|no\s+information"],
    "Reason|User error": [r"user\s+error"],
    "Reason|SRP/PK compromised": [r"(srp|seed\s+phrase|secret\s+recovery\s+phrase|private\s+key)\s+(compromised|stolen|leaked)", r"key\s+comp(romised|)"],
    # Vector
    "Vector|Malware": [r"malware|virus|trojan|stealer|keylog(ger)?"],
    "Vector|Job Offer Scam": [r"job\s+offer\s+scam"],
    "Vector|Fake Application": [r"fake\s+app(lication)?"],
    "Vector|Scam Token": [r"scam\s+token"],
    "Vector|SRP Phishing": [r"(srp|seed\s+phrase|secret\s+recovery\s+phrase).*phish"],
    "Vector|Investment Scam": [r"investment\s+scam|pig\s+butcher(ing)?"],
    "Vector|Unknown": [r"unknown"],
    # Method
    "Method|Blockchain phishing": [r"blockchain\s+phish"],
    "Method|Spearphishing": [r"spear\s*phish"],
    "Method|Email Phishing": [r"email\s+phish"],
    "Method|N/A": [r"n/?a|not\s+applicable"],
    "Method|Pig butchering": [r"pig\s+butcher(ing)?"],
    "Method|Angler phishing": [r"angler\s+phish"],
    "Method|Unknown": [r"unknown"],
    # SRP/PK compromised reason
    "SRP/PK compromised reason|SRP Physically Stolen": [r"srp\s+physic(al|ally)\s+stolen"],
    "SRP/PK compromised reason|SRP Digitally Stolen": [r"srp\s+digitally\s+stolen"],
    "SRP/PK compromised reason|Rotten Seed": [r"rotten\s+seed"],
    "SRP/PK compromised reason|SRP Phished Directly": [r"srp\s+phish(ed)?\s+directly"],
    "SRP/PK compromised reason|Malware": [r"malware|stealer"],
    "SRP/PK compromised reason|Unknown": [r"unknown"],
    # User error reason
    "User error reason|Other wallet transfer": [r"other\s+wallet\s+transfer"],
    "User error reason|CEX transfer": [r"cex\s+transfer|centralized\s+exchange\s+transfer"],
    "User error reason|Off-chain scam": [r"off-?chain\s+scam"],
    "User error reason|Scam token purchase": [r"scam\s+token\s+purchase"],
    "User error reason|Direct token transfer": [r"direct\s+token\s+transfer"],
    # Unintended contract interaction reason
    "Unintended contract interaction reason|7702 batch transfer": [r"7702\s+batch\s+transfer"],
    "Unintended contract interaction reason|Token Approval & Transfer": [r"token\s+approval.*transfer"],
    "Unintended contract interaction reason|Token transfer": [r"token\s+transfer"],
    "Unintended contract interaction reason|Token Approval": [r"token\s+approval"],
}

def _score_taxonomy(texts: list[str], taxonomy: dict[str, list[str]], top_n: int = 6) -> list[tuple[str, int]]:
    compiled = {k: re.compile("|".join(v), flags=re.IGNORECASE) for k, v in taxonomy.items()}
    counts: dict[str, int] = {k: 0 for k in taxonomy.keys()}
    for t in texts:
        tt = t or ""
        for label, patt in compiled.items():
            if patt.search(tt):
                counts[label] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(k, v) for k, v in ranked if v > 0][:top_n]

# ---------------------------
# Additional area taxonomies (user-provided terms)
# ---------------------------

SWAPS_TAXONOMY: dict[str, list[str]] = {
    # Swap Feature
    "Swap Feature|Native Swap": [r"native\s+swap"],
    "Swap Feature|Bridge": [r"\bbridge\b"],
    "Swap Feature|Cross-Chain Swap": [r"cross[- ]?chain\s+swap"],
    # Swap issues
    "Swap issues|Conflicting Token Price Data": [r"conflict(ing)?\s+token\s+price"],
    "Swap issues|Insufficient Funds": [r"insufficient\s+funds"],
    "Swap issues|UI Functionality Issue": [r"ui\s+(function(al)?|issue)"],
    "Swap issues|Approval Transaction Only": [r"approval\s+transaction\s+only"],
    "Swap issues|Received incorrect amount / Price Impact": [r"(incorrect|wrong)\s+amount|price\s+impact"],
    "Swap issues|Unsupported/Blocked Token": [r"(unsupported|blocked)\s+token"],
    "Swap issues|No Trade Routes Available": [r"no\s+trade\s+routes?\s+available"],
    "Swap issues|Failed Transaction": [r"failed\s+transaction"],
    "Swap issues|User Training": [r"user\s+training|how\s+to\s+swap"],
    "Swap issues|Error Fetching Quotes": [r"error\s+fetch(ing)?\s+quotes?"],
    "Swap issues|No Quotes Available": [r"no\s+quotes?\s+available"],
    # Bridge issues
    "Bridge issues|Received an incorrect number of tokens": [r"incorrect\s+number\s+of\s+tokens"],
    "Bridge issues|Approval Transaction Only": [r"approval\s+transaction\s+only"],
    "Bridge issues|UI Functionality Issue": [r"bridge\s+ui\s+issue|ui\s+(function(al)?|issue)"],
    "Bridge issues|Received the wrong token": [r"received\s+the\s+wrong\s+token"],
    "Bridge issues|Bridge UI Issue": [r"bridge\s+ui\s+issue"],
    "Bridge issues|Network/Token not supported": [r"(network|token)\s+not\s+supported"],
    "Bridge issues|No Trade Routes Available": [r"no\s+(bridge\s+)?(trade\s+)?routes?\s+available"],
    "Bridge issues|No bridge options available": [r"no\s+bridge\s+options?\s+available"],
    "Bridge issues|Bridge Refunded": [r"bridge\s+refund(ed)?"],
    "Bridge issues|Other": [r"bridge.*other"],
    "Bridge issues|Failed transaction": [r"failed\s+transaction"],
    "Bridge issues|User Training": [r"user\s+training|how\s+to\s+bridge"],
    "Bridge issues|Haven't received the funds / Bridge processing": [r"haven'?t\s+received\s+the\s+funds|bridge\s+processing"],
    # Swap: Network
    "Swap: Network|Solana": [r"solana"],
    "Swap: Network|BNB Smart Chain": [r"bnb\s+smart\s+chain|bsc"],
    "Swap: Network|Avalanche": [r"avalanche|avax"],
    "Swap: Network|Arbitrum One": [r"arbitrum(\s+one)?"],
    "Swap: Network|Ethereum Mainnet": [r"ethereum\s+mainnet|eth(\s+mainnet)?"],
    "Swap: Network|Linea": [r"linea"],
    "Swap: Network|Base": [r"\bbase\b"],
    "Swap: Network|Polygon": [r"polygon|matic"],
    "Swap: Network|Unknown": [r"unknown\s+network"],
    # Bridge: Network
    "Bridge: Network|Pulse": [r"pulse"],
    "Bridge: Network|Arbitrum One": [r"arbitrum(\s+one)?"],
    "Bridge: Network|BNB Smart Chain": [r"bnb\s+smart\s+chain|bsc"],
    "Bridge: Network|Solana": [r"solana"],
    "Bridge: Network|Ethereum Mainnet": [r"ethereum\s+mainnet|eth(\s+mainnet)?"],
    "Bridge: Network|Linea": [r"linea"],
    "Bridge: Network|Polygon": [r"polygon|matic"],
    "Bridge: Network|Avalanche": [r"avalanche|avax"],
    "Bridge: Network|Base": [r"\bbase\b"],
    # Swap: Transaction issue
    "Swap: Transaction issue|Execution Reverted": [r"execution\s+revert(ed)?"],
    "Swap: Transaction issue|Failed transaction (local)": [r"failed\s+transaction\s*\(local\)"],
    # Bridge Provider
    "Bridge Provider|Hop": [r"\bhop\b"],
    "Bridge Provider|Stargate": [r"stargate"],
    "Bridge Provider|Axelar": [r"axelar"],
    "Bridge Provider|Mayan": [r"mayan"],
    "Bridge Provider|deBridge": [r"debridge"],
    "Bridge Provider|Celer cBridge": [r"celer|cbridge"],
    "Bridge Provider|Across": [r"across"],
    "Bridge Provider|Circle": [r"circle"],
    "Bridge Provider|Squid": [r"squid"],
    "Bridge Provider|Relay": [r"relay"],
    # Swap: Platform
    "Swap: Platform|Portfolio": [r"portfolio"],
    "Swap: Platform|Extension": [r"extension"],
    "Swap: Platform|Mobile": [r"mobile"],
    # Bridge: Transaction issue
    "Bridge: Transaction issue|Failed transaction (on-chain)": [r"failed\s+transaction\s*\(on[- ]?chain\)"],
    "Bridge: Transaction issue|Pending transaction (local)": [r"pending\s+transaction\s*\(local\)"],
    "Bridge: Transaction issue|Out of gas": [r"out\s+of\s+gas"],
    "Bridge: Transaction issue|Failed transaction (local)": [r"failed\s+transaction\s*\(local\)"],
    # Swap: User Training
    "Swap: User Training|Approval issue": [r"approval\s+issue"],
    "Swap: User Training|Not enough gas": [r"not\s+enough\s+gas"],
    "Swap: User Training|General question": [r"general\s+question"],
    "Swap: User Training|Token not imported": [r"token\s+not\s+imported"],
    "Swap: User Training|Gas included Swap Education": [r"gas\s+included\s+swap\s+education"],
    "Swap: User Training|Tx review / Successful Swap": [r"tx\s+review|successful\s+swap"],
    # Bridge: User training
    "Bridge: User training|Approval Transaction Only": [r"approval\s+transaction\s+only"],
    "Bridge: User training|Bridge UI Issue": [r"bridge\s+ui\s+issue"],
    "Bridge: User training|No bridge options available": [r"no\s+bridge\s+options?\s+available"],
    "Bridge: User training|UI Functionality Issue": [r"ui\s+(function(al)?|issue)"],
    "Bridge: User training|Network/token not supported": [r"(network|token)\s+not\s+supported"],
    "Bridge: User training|Bridge Refunded": [r"bridge\s+refund(ed)?"],
    "Bridge: User training|Failed transaction": [r"failed\s+transaction"],
    "Bridge: User training|Haven't received the funds / Bridge processing": [r"haven'?t\s+received\s+the\s+funds|bridge\s+processing"],
    # Bridge: Platform
    "Bridge: Platform|Portfolio": [r"portfolio"],
    "Bridge: Platform|Extension": [r"extension"],
    "Bridge: Platform|Mobile": [r"mobile"],
}

RAMPS_TAXONOMY: dict[str, list[str]] = {
    # Platform
    "Ramps: Platform|Portfolio": [r"portfolio"],
    "Ramps: Platform|Extension": [r"extension"],
    "Ramps: Platform|Mobile": [r"mobile"],
    # Payment provider
    "Ramps: Payment provider|Mercuryo": [r"mercuryo"],
    "Ramps: Payment provider|Transak": [r"transak"],
    "Ramps: Payment provider|MoonPay": [r"moon\s?pay"],
    "Ramps: Payment provider|Banxa": [r"banxa"],
    # Buy or Sell
    "Ramps: Buy or Sell|Buy": [r"\bbuy\b"],
    "Ramps: Buy or Sell|Sell": [r"\bsell\b"],
    # Buy Issue
    "Ramps: Buy Issue|Unsupported Region": [r"unsupported\s+region"],
    "Ramps: Buy Issue|Purchase failed or declined": [r"(purchase|buy)\s+(failed|declined)"],
    "Ramps: Buy Issue|Error in Buy Flow (Vendor)": [r"error\s+in\s+buy\s+flow\s*\(vendor\)"],
    "Ramps: Buy Issue|Funds did not arrive": [r"funds\s+did\s+not\s+arrive"],
    "Ramps: Buy Issue|Verification process issue (Vendor)": [r"verification\s+process\s+issue\s*\(vendor\)"],
    "Ramps: Buy Issue|Error in Buy Flow (MetaMask)": [r"error\s+in\s+buy\s+flow\s*\(metamask\)"],
    "Ramps: Buy Issue|User Training": [r"user\s+training|how\s+to\s+buy"],
    # Sell Issue
    "Ramps: Sell Issue|Sale failed or declined": [r"sale\s+(failed|declined)"],
    "Ramps: Sell Issue|Unsupported Region": [r"unsupported\s+region"],
    "Ramps: Sell Issue|Error in Sell flow (MetaMask)": [r"error\s+in\s+sell\s+flow\s*\(metamask\)"],
    "Ramps: Sell Issue|User Training": [r"user\s+training|how\s+to\s+sell"],
    "Ramps: Sell Issue|Insufficient tokens for sale or gas": [r"insufficient\s+(tokens|gas)"],
    "Ramps: Sell Issue|Error in Sell flow (Vendor)": [r"error\s+in\s+sell\s+flow\s*\(vendor\)"],
    "Ramps: Sell Issue|Payment did not arrive at cash-out destination": [r"payment\s+did\s+not\s+arrive|cash[- ]?out\s+destination"],
    # Network
    "Ramps: Network|Polygon": [r"polygon|matic"],
    "Ramps: Network|Bitcoin": [r"bitcoin|btc"],
    "Ramps: Network|BNB Smart Chain": [r"bnb\s+smart\s+chain|bsc"],
    "Ramps: Network|Base": [r"\bbase\b"],
    "Ramps: Network|Unknown": [r"unknown\s+network"],
    "Ramps: Network|Ethereum": [r"ethereum|eth(\s+mainnet)?"],
}

DASHBOARD_TAXONOMY: dict[str, list[str]] = {
    # Network
    "Dashboard: Network|Polygon": [r"polygon|matic"],
    "Dashboard: Network|BNB Smart Chain": [r"bnb\s+smart\s+chain|bsc"],
    "Dashboard: Network|Arbitrum": [r"arbitrum"],
    "Dashboard: Network|Linea": [r"linea"],
    "Dashboard: Network|Unknown": [r"unknown\s+network"],
    "Dashboard: Network|Ethereum": [r"ethereum|eth(\s+mainnet)?"],
    # Issue
    "Dashboard: Issue|Dashboard Feature request": [r"feature\s+request"],
    "Dashboard: Issue|Account Issue": [r"account\s+issue"],
    "Dashboard: Issue|MetaMask Missions Campaign": [r"missions?\s+campaign"],
    "Dashboard: Issue|Token/NFT Issue": [r"token|nft\s+issue"],
    "Dashboard: Issue|Balance/Fiat Issue": [r"(balance|fiat)\s+issue"],
    "Dashboard: Issue|Transaction Issue": [r"transaction\s+issue"],
    "Dashboard: Issue|User Training": [r"user\s+training|how\s+to"],
    # Platform
    "Dashboard: Platform|Portfolio": [r"portfolio"],
    "Dashboard: Platform|Extension": [r"extension"],
    "Dashboard: Platform|Mobile": [r"mobile"],
    # Portfolio User Training
    "Portfolio User Training|Importing a token/NFT": [r"import(ing)?\s+(a\s+)?(token|nft)"],
    "Portfolio User Training|Airdrops": [r"airdrops?"],
    "Portfolio User Training|General Question": [r"general\s+question"],
    "Portfolio User Training|Send/Receive/Transfer funds": [r"(send|receive|transfer)\s+funds"],
    "Portfolio User Training|Connecting an account": [r"connecting\s+an\s+account"],
    "Portfolio User Training|Dapp tab": [r"dapp\s+tab"],
    # Balance issue
    "Dashboard: Balance issue|Incorrect/Missing Price Data": [r"incorrect|missing\s+price\s+data"],
    "Dashboard: Balance issue|Incorrect Token Balance": [r"incorrect\s+token\s+balance"],
    "Dashboard: Balance issue|No Token/Fiat Balance": [r"no\s+(token|fiat)\s+balance"],
    # Account issue
    "Dashboard: Account issue|Watched account not in MetaMask": [r"watched\s+account\s+not\s+in\s+metamask"],
    "Dashboard: Account issue|Connecting or accessing new account": [r"(connecting|accessing)\s+new\s+account"],
    "Dashboard: Account issue|Managing an account": [r"managing\s+an\s+account"],
    "Dashboard: Account issue|Removing an account": [r"removing\s+an\s+account"],
    # Tokens issue
    "Dashboard: Tokens issue|Token/NFT not displaying properly": [r"not\s+display(ing)?\s+properly"],
    "Dashboard: Tokens issue|Token/NFT import": [r"(token|nft)\s+import"],
}

WALLET_TAXONOMY: dict[str, list[str]] = {
    # Issue
    "Wallet: Issue|External dApp issue": [r"(external\s+)?dapp\s+issue|not\s+meta\s?mask\s+related"],
    "Wallet: Issue|Balance issue": [r"balance\s+issue"],
    "Wallet: Issue|Opening MetaMask": [r"opening\s+metamask|slow\s+password\s+opening"],
    "Wallet: Issue|User training": [r"user\s+training|how\s+to"],
    "Wallet: Issue|Other": [r"wallet.*other"],
    "Wallet: Issue|Transaction issue": [r"transaction\s+issue"],
    "Wallet: Issue|Back-up or restore": [r"back[- ]?up|restore"],
    # Platform
    "Wallet: Platform|Portfolio": [r"portfolio"],
    "Wallet: Platform|Extension": [r"extension"],
    "Wallet: Platform|Mobile": [r"mobile"],
    # Network
    "Wallet: Network|Arbitrum": [r"arbitrum"],
    "Wallet: Network|BNB Smart Chain": [r"bnb\s+smart\s+chain|bsc"],
    "Wallet: Network|Solana": [r"solana"],
    "Wallet: Network|Ethereum": [r"ethereum|eth(\s+mainnet)?"],
    "Wallet: Network|Base": [r"\bbase\b"],
    # User training
    "Wallet: User training|Tokens sent on wrong network": [r"tokens?\s+sent\s+on\s+wrong\s+network"],
    "Wallet: User training|Custom network not added": [r"custom\s+network\s+not\s+added"],
    "Wallet: User training|General Question": [r"general\s+question"],
    "Wallet: User training|Tokens sent to smart contract": [r"tokens?\s+sent\s+to\s+smart\s+contract"],
    "Wallet: User training|Token not imported": [r"token\s+not\s+imported"],
    "Wallet: User training|Tokens sent to wrong address": [r"tokens?\s+sent\s+to\s+wrong\s+address"],
    "Wallet: User training|Not enough gas": [r"not\s+enough\s+gas"],
    # Transaction issue
    "Wallet: Transaction issue|FLI due to tx and signature": [r"fli\s+due\s+to\s+tx\s+and\s+signature"],
    "Wallet: Transaction issue|Pending transaction (local)": [r"pending\s+transaction\s*\(local\)"],
    "Wallet: Transaction issue|Failed transaction (on-chain)": [r"failed\s+transaction\s*\(on[- ]?chain\)"],
    "Wallet: Transaction issue|Pending transaction (on-chain)": [r"pending\s+transaction\s*\(on[- ]?chain\)"],
    "Wallet: Transaction issue|Failed transaction (local)": [r"failed\s+transaction\s*\(local\)"],
    # Back-up or restore
    "Wallet: Back-up or restore|SRP/PK not valid": [r"(srp|seed\s+phrase|private\s+key)\s+not\s+valid"],
    "Wallet: Back-up or restore|SRP/PK never backed up": [r"(srp|seed\s+phrase|private\s+key).*never\s+back(ed)?\s+up"],
    "Wallet: Back-up or restore|SRP/PK restored wrong account": [r"restor(ed|ing)\s+wrong\s+account"],
    "Wallet: Back-up or restore|Imported loose account(s)": [r"imported\s+loose\s+account"],
    "Wallet: Back-up or restore|Password issue": [r"password\s+issue"],
    "Wallet: Back-up or restore|SRP/PK and password lost": [r"(srp|seed\s+phrase|private\s+key).*password\s+lost"],
    # External Dapp issue
    "Wallet: External Dapp issue|Not receiving prompt from Dapp": [r"not\s+receiving\s+prompt\s+from\s+dapp"],
    "Wallet: External Dapp issue|Connectivity to Dapp": [r"connect(ion|ivity)\s+to\s+dapp"],
    "Wallet: External Dapp issue|Not MetaMask related": [r"not\s+metamask\s+related"],
    "Wallet: External Dapp issue|Dapp issue": [r"dapp\s+issue"],
    # Hardware wallet
    "Wallet: Hardware wallet|Other HW": [r"other\s+hw|other\s+hardware"],
    "Wallet: Hardware wallet|Keystone QR": [r"keystone\s+qr"],
    "Wallet: Hardware wallet|Trezor": [r"trezor"],
    "Wallet: Hardware wallet|Ledger": [r"ledger"],
    # Hardware wallet issue
    "Wallet: Hardware wallet issue|Unable to add account to MetaMask": [r"unable\s+to\s+add\s+account\s+to\s+metamask"],
    "Wallet: Hardware wallet issue|Failed transaction": [r"failed\s+transaction"],
    "Wallet: Hardware wallet issue|Unable to sign tx on device": [r"unable\s+to\s+sign\s+tx\s+on\s+device"],
    # NFT issue
    "Wallet: NFT issue|NFT display issue": [r"nft\s+display\s+issue"],
    "Wallet: NFT issue|Transferring an NFT": [r"transferring\s+an\s+nft|nft\s+transfer"],
    "Wallet: NFT issue|Importing an NFT": [r"import(ing)?\s+an\s+nft"],
}

STAKING_TAXONOMY: dict[str, list[str]] = {
    # Feature
    "Staking: Feature|Stablecoin Lending issue": [r"stablecoin\s+lending\s+issue"],
    "Staking: Feature|Validator Staking issue": [r"validator\s+staking\s+issue"],
    "Staking: Feature|Liquid Staking": [r"liquid\s+staking"],
    "Staking: Feature|Pooled Staking issue": [r"pooled\s+staking\s+issue"],
    "Staking: Feature|Third Party Staking": [r"third\s+party\s+staking"],
    # Platform
    "Staking: Platform|Extension": [r"extension"],
    "Staking: Platform|Portfolio": [r"portfolio"],
    "Staking: Platform|Mobile": [r"mobile"],
    # Issue
    "Staking: Issue|Other": [r"staking.*other"],
    "Staking: Issue|User Training": [r"user\s+training|how\s+to\s+stake"],
    "Staking: Issue|Can't stake my tokens": [r"can'?t\s+stake\s+my\s+tokens"],
    "Staking: Issue|Managing staked tokens": [r"managing\s+staked\s+tokens"],
    "Staking: Issue|Failed transaction": [r"failed\s+transaction"],
    "Staking: Issue|Withdrawing": [r"withdrawing|withdraw(al)?"],
    # Network
    "Staking: Network|Base": [r"\bbase\b"],
    "Staking: Network|BNB Smart Chain": [r"bnb\s+smart\s+chain|bsc"],
    "Staking: Network|Bitcoin": [r"bitcoin|btc"],
    "Staking: Network|Ethereum": [r"ethereum|eth(\s+mainnet)?"],
    "Staking: Network|Optimism": [r"optimism"],
    # Liquid Staking Provider
    "Liquid Staking: Provider|Lido": [r"lido"],
    # Withdrawal issue
    "Staking: Withdrawal issue|User Error": [r"user\s+error"],
    "Staking: Withdrawal issue|Platform Error": [r"platform\s+error"],
    "Staking: Withdrawal issue|Other": [r"withdraw(al)?.*other"],
    # Failed transaction issue
    "Staking: Failed transaction issue|Failed locally": [r"failed\s+locally"],
    # User Training details
    "Staking: User Training|How to stake": [r"how\s+to\s+stake"],
    "Staking: User Training|What is staking": [r"what\s+is\s+staking"],
    "Staking: User Training|How to Claim rewards": [r"how\s+to\s+claim\s+rewards"],
    "Staking: User Training|How to unstake": [r"how\s+to\s+unstake"],
}

SNAPS_TAXONOMY: dict[str, list[str]] = {
    # Platform
    "Snaps: Platform|Extension": [r"extension"],
    # Network
    "Snaps: Network|Ethereum": [r"ethereum|eth"],
    "Snaps: Network|Solana": [r"solana"],
    "Snaps: Network|Bitcoin": [r"bitcoin|btc"],
    "Snaps: Network|Starknet": [r"starknet"],
    # Issue
    "Snaps: Issue|General Question": [r"general\s+question"],
    "Snaps: Issue|Connectivity issue": [r"connect(ion|ivity)\s+issue"],
    "Snaps: Issue|Installation issue": [r"install(ation)?\s+issue"],
    "Snaps: Issue|Transaction issue": [r"transaction\s+issue"],
    "Snaps: Issue|Key Management issue": [r"key\s+management\s+issue"],
    "Snaps: Issue|Allowlist request": [r"allowlist\s+request"],
    # Client
    "Snaps: Client|MetaMask": [r"metamask"],
    "Snaps: Client|MetaMask Flask": [r"flask"],
}

CARD_TAXONOMY: dict[str, list[str]] = {
    # Closed Conversations by Network
    "Closed Conversations by Network|BNB Smart Chain": [r"bnb\s+smart\s+chain|bsc"],
    "Closed Conversations by Network|Base": [r"\bbase\b"],
    "Closed Conversations by Network|Linea": [r"linea"],
    "Closed Conversations by Network|Polygon": [r"polygon|matic"],
    "Closed Conversations by Network|Arbitrum": [r"arbitrum"],
    "Closed Conversations by Network|Solana": [r"solana"],
    "Closed Conversations by Network|Ethereum": [r"ethereum|eth(\s+mainnet)?"],
    # MM Card Issues segmented
    "MM Card Issues segmented|Wallet restore issue or SRP lost": [r"wallet\s+restore\s+issue|srp\s+lost|seed\s+phrase\s+lost"],
    "MM Card Issues segmented|Error in buy flow": [r"error\s+in\s+buy\s+flow"],
    "MM Card Issues segmented|Refunds": [r"refunds?"],
    "MM Card Issues segmented|User training": [r"user\s+training|how\s+to"],
    "MM Card Issues segmented|Security": [r"security"],
    "MM Card Issues segmented|Approval Spending Cap Only": [r"approval\s+spending\s+cap\s+only"],
    "MM Card Issues segmented|Transaction failure": [r"transaction\s+failure|failed\s+transaction"],
    "MM Card Issues segmented|Other": [r"card.*other"],
    "MM Card Issues segmented|Purchase failed": [r"purchase\s+failed"],
    "MM Card Issues segmented|Withdrawal Issues": [r"withdraw(al)?\s+issues"],
    "MM Card Issues segmented|Partner issue": [r"partner\s+issue"],
    # MM Card Swap Issues segmented
    "MM Card Swap Issues segmented|User Training": [r"user\s+training"],
    "MM Card Swap Issues segmented|Failed Transaction": [r"failed\s+transaction"],
    # MM Card Partner Issues segmented
    "MM Card Partner Issues segmented|Reset password": [r"reset\s+password"],
    "MM Card Partner Issues segmented|Wants to change email": [r"change\s+email"],
    "MM Card Partner Issues segmented|Wants to chnge phone number": [r"change\s+phone\s+number"],
    "MM Card Partner Issues segmented|Didn't receive confirmation email": [r"did(n't| not)\s+receive\s+confirmation\s+email"],
    "MM Card Partner Issues segmented|Didn't receive confirmation SMS": [r"did(n't| not)\s+receive\s+confirmation\s+sms"],
    "MM Card Partner Issues segmented|Didn't receive password reset email": [r"did(n't| not)\s+receive\s+password\s+reset\s+email"],
    "MM Card Partner Issues segmented|Dashboard Issue": [r"dashboard\s+issue"],
    "MM Card Partner Issues segmented|KYC Issue": [r"kyc\s+issue"],
    "MM Card Partner Issues segmented|Other": [r"partner.*other"],
    # MM Card Bridge Issues segmented
    "MM Card Bridge Issues segemented|Failed transaction": [r"failed\s+transaction"],
    "MM Card Bridge Issues segemented|User Training": [r"user\s+training"],
    # AI Topic
    "AI Topic|Card integration": [r"card\s+integration"],
    "AI Topic|Card troubleshooting": [r"card\s+troubleshooting"],
    "AI Topic|Email confirmation": [r"email\s+confirmation"],
    "AI Topic|Card account disabling": [r"account\s+disabl(ing|ed)"],
    "AI Topic|Wallet creation": [r"wallet\s+creation"],
    "AI Topic|Fund transfers": [r"fund\s+transfers"],
    "AI Topic|Gas fees": [r"gas\s+fees?"],
    "AI Topic|KYC process and verification issues": [r"kyc\s+process|verification\s+issues"],
    "AI Topic|Wallet balances": [r"wallet\s+balances?"],
    "AI Topic|Account updates": [r"account\s+updates?"],
}

# ---------------------------
# Area detection helpers
# ---------------------------

AREA_ATTRIBUTE_KEYS = [
    "MetaMask area",
    "MetaMask Area",
    "metamask area",
    "MetaMask Area Name",
    "Area",
    "area",
    "Product",
    "product",
    "Topic",
    "topic",
    "MM area",
    "mm area",
]

_AREA_SYNONYMS = {
    "wallet api": "Wallet API",
    "walletapi": "Wallet API",
    "wallet-api": "Wallet API",
    "wallet_api": "Wallet API",
    "api": "Wallet API",
    "sdk": "SDK",
    "developer sdk": "SDK",
    "dev sdk": "SDK",
    "security": "Security",
    "fraud": "Security",
    "phishing": "Security",
    "scam": "Security",
    "portfolio dashboard": "Dashboard",
}

_area_regex_cache: dict[str, re.Pattern] = {}

# Known Intercom category attribute names from the provided compact JSON list
KNOWN_ATTRIBUTE_NAMES: Set[str] = set([
    "Back-up or restore",
    "Confirmation issue",
    "External dApp issue",
    "Hawrdware wallet issue",
    "Hardware wallet issue",
    "NFT issue",
    "Social login",
    "Notification issue",
    "Opening MetaMask",
    "Transaction issue",
    "User training",
    "Wallet User Training",
    "MM Travel",
    "MM Card Issue",
    "MM Card Partner issue",
    "Balance/Fiat Issue",
    "Token/NFT Issue",
    "Account issue",
    "Portfolio Transaction issues",
    "Portfolio User Training",
    "Dashboard Feature request",
    "Buy issue",
    "Sell issue",
    "SRP/PK compromised",
    "Unintended contract interaction",
    "User error",
    "No funds lost",
    "Stablecoin Lending issue",
    "Validator Staking issue",
    "Pooled Staking issue",
    "Liquid Staking",
    "Third Party Staking Issue",
    "Native Swaps issue",
    "Network",
    "User type",
    "Developer?",
    "MetaMask platform",
    "Extension OS",
])

# Area-specific hints for which attribute columns most likely represent the primary issue
KNOWN_ISSUE_COLUMN_HINTS: Dict[str, List[str]] = {
    "Wallet": [
        "Back-up or restore",
        "Confirmation issue",
        "External dApp issue",
        "Hardware wallet issue",
        "Hawrdware wallet issue",
        "NFT issue",
        "Opening MetaMask",
        "Transaction issue",
        "User training",
        "Balance issue",
    ],
    "Dashboard": [
        "Dashboard Feature request",
        "Account issue",
        "Token/NFT Issue",
        "Balance/Fiat Issue",
        "Portfolio Transaction issues",
        "Portfolio User Training",
    ],
    "Ramps": [
        "Buy issue",
        "Sell issue",
        "Buy or Sell",
    ],
    "Swaps": [
        "Native Swaps issue",
        "Swaps issue",
        "Bridge issues",
    ],
    "Staking": [
        "Stablecoin Lending issue",
        "Validator Staking issue",
        "Pooled Staking issue",
        "Liquid Staking",
        "Third Party Staking Issue",
    ],
    "Card": [
        "MM Card Issue",
        "MM Card Partner issue",
    ],
}

# Columns that are not issues and must be excluded from primary issue detection
NON_ISSUE_COLUMN_NAMES: Set[str] = set([
    "User type",
    "Developer?",
    "MetaMask platform",
    "Extension OS",
    "Network",
    "MM Travel",
])

# Per-area issue source columns prioritized. We count by these categories dynamically.
AREA_ISSUE_SOURCES: Dict[str, List[str]] = {
    "Wallet": [
        "Wallet issue",
        "User training",
        "Transaction issue",
        "Balance issue",
        "Back-up or restore",
        "External dApp issue",
        "NFT issue",
        "Opening MetaMask",
        "Confirmation issue",
        "Hardware wallet issue",
        "Hawrdware wallet issue",
    ],
    "Dashboard": [
        "Dashboard: Issue",
        "Dashboard Feature request",
        "Account issue",
        "Token/NFT Issue",
        "Balance/Fiat Issue",
        "Portfolio Transaction issues",
        "Portfolio User Training",
    ],
    "Ramps": [
        "Buy issue",
        "Sell issue",
        "Buy or Sell",
    ],
    "Swaps": [
        "Swaps issue",
        "Native Swaps issue",
    ],
    "Card": [
        "MM Card Issue",
        "MM Card Partner issue",
    ],
    "Staking": [
        "Stablecoin Lending issue",
        "Validator Staking issue",
        "Pooled Staking issue",
        "Liquid Staking",
        "Third Party Staking Issue",
    ],
    "Security": [
        "SRP/PK compromised",
        "Unintended contract interaction",
        "User error",
        "No funds lost",
    ],
    "Snaps": [
        "Snaps: Issue",
        "Snaps Category",
    ],
}

def _normalize_area_string(value: str) -> str:
    v = (value or "").strip().lower()
    v = v.replace("_", " ").replace("-", " ")
    v = re.sub(r"\s+", " ", v)
    # map synonyms
    if v in _AREA_SYNONYMS:
        return _AREA_SYNONYMS[v]
    # Title-case for canonical known names if exact
    for canonical in CATEGORY_HEADERS.keys():
        if v == canonical.lower():
            return canonical
    return value.strip()

def _get_area_attribute(attributes: dict) -> Optional[str]:
    for key in AREA_ATTRIBUTE_KEYS:
        if key in attributes and attributes.get(key):
            return _normalize_area_string(str(attributes.get(key)))
    # Also try case-insensitive search across keys
    for k, v in attributes.items():
        if isinstance(k, str) and k.lower().strip() in [x.lower() for x in AREA_ATTRIBUTE_KEYS] and v:
            return _normalize_area_string(str(v))
    return None

def _compile_area_regex(area: str) -> re.Pattern:
    if area in _area_regex_cache:
        return _area_regex_cache[area]
    theme_list = AREA_THEMES.get(area, GLOBAL_THEMES)
    # collect keywords and add area name itself as a hint
    keyword_patterns = []
    for theme in theme_list:
        keyword_patterns.extend(theme.get("keywords", []))
    # add area-specific direct hints
    direct_hints = []
    if area == "Security":
        direct_hints = [r"security", r"phish", r"scam", r"fraud", r"compromis", r"hack"]
    elif area == "SDK":
        direct_hints = [r"sdk", r"developer", r"integration", r"build", r"compile"]
    elif area == "Wallet API":
        direct_hints = [r"wallet api", r"api", r"rest", r"endpoint", r"rate limit", r"401|403|404|429|500"]
    pattern = re.compile("|".join(keyword_patterns + direct_hints), flags=re.IGNORECASE)
    _area_regex_cache[area] = pattern
    return pattern

def _text_suggests_area(text: str, area: str) -> bool:
    if not text:
        return False
    patt = _compile_area_regex(area)
    return bool(patt.search(text))

# ---------------------------
# Area-specific curated themes
# ---------------------------
# Each theme: {"name": str, "explanation": str, "keywords": [regex strings]}
GLOBAL_THEMES = [
    {"name": "📩 Support Escalation Requests", "explanation": "Users wait on live agents to take action or confirm issues manually.", "keywords": [r"(live|real) ?agent", r"escalat", r"please\s+help", r"wait(ing)?\s+for\s+support"]},
]

AREA_THEMES = {
    "Wallet": [
        {"name": "🪙 Token Import Confusion", "explanation": "Users cannot see tokens due to missing contract imports or wrong network.", "keywords": [r"import token", r"contract address", r"add(ing)? token", r"wrong network", r"not\s+show(ing)? token"]},
        {"name": "⛽ Gas & Transaction Failures", "explanation": "Transactions are stuck or fail due to low gas, congestion, or bad estimates.", "keywords": [r"gas", r"tx ?fail(ed|ure)?", r"transaction (stuck|pending)", r"insufficient.*(funds|gas)"]},
        {"name": "🔐 Recovery Phrase Misunderstanding", "explanation": "Users expect to restore wallets without having saved their seed phrase.", "keywords": [r"seed phrase", r"recovery phrase", r"restore wallet", r"lost (seed|recovery)"]},
        {"name": "🔀 Network/Chain Selection Issues", "explanation": "Confusion switching networks, especially BNB Smart Chain.", "keywords": [r"BNB", r"smart chain", r"switch network", r"wrong chain"]},
        {"name": "🌍 Non-English Language Usage", "explanation": "Many requests are written in Spanish, Indonesian, or Portuguese.", "keywords": [r"espa[nñ]ol", r"indones(ian|ia)", r"portugu[eê]s", r"bahasa"]},
    ] + GLOBAL_THEMES,
    "Swaps": [
        {"name": "⛽ Gas & Transaction Failures", "explanation": "Swaps fail or revert due to gas, slippage, or network conditions.", "keywords": [r"gas", r"revert", r"fail(ed)?", r"stuck"]},
        {"name": "📉 Price Impact & Slippage", "explanation": "High price impact or slippage causes unexpected received amounts.", "keywords": [r"slippage", r"price impact", r"min(imum)? received", r"impact too (high|large)"]},
        {"name": "🔒 Allowance/Approval Issues", "explanation": "Token approvals/allowances block or confuse swap execution.", "keywords": [r"allowance", r"approval", r"approve token", r"permit"]},
        {"name": "🌉 Route/Bridge Limitations", "explanation": "Bridging paths or routes are unavailable or limited.", "keywords": [r"bridge", r"route", r"path", r"routing"]},
    ] + GLOBAL_THEMES,
    "Ramps": [
        {"name": "🧾 KYC/Verification", "explanation": "Identity or verification steps block on/off-ramp flows.", "keywords": [r"KYC", r"verif(y|ication)", r"identity", r"document"]},
        {"name": "💳 Payment/Bank Failures", "explanation": "Card/bank payments are declined or fail to settle.", "keywords": [r"card", r"bank", r"declin(ed|e)", r"payment (fail|error)"]},
        {"name": "📈 On/Off-Ramp Limits", "explanation": "Transaction limits prevent completing the desired ramp amount.", "keywords": [r"limit", r"cap", r"threshold", r"maximum"]},
    ] + GLOBAL_THEMES,
    "Staking": [
        {"name": "🔓 Withdrawals & Unstaking", "explanation": "Unstake/withdrawal delays or confusion about timelines and status.", "keywords": [r"unstak(e|ing)", r"withdraw(al)?", r"claim"]},
        {"name": "💸 Rewards/APR Timing", "explanation": "Questions about reward accrual timing, APR changes, or visibility.", "keywords": [r"reward", r"APR", r"yield", r"interest"]},
        {"name": "🧭 Validator/Delegation Issues", "explanation": "Selecting, changing, or interacting with validators is confusing.", "keywords": [r"validator", r"delegate", r"delegation"]},
        {"name": "🤝 Third-Party Staking Providers", "explanation": "External staking provider issues impact user experience.", "keywords": [r"third party", r"provider", r"Lido|Rocket Pool|StakeWise|Figment"]},
    ] + GLOBAL_THEMES,
    "Card": [
        {"name": "🧾 KYC/Verification", "explanation": "Identity or verification steps block card provisioning or use.", "keywords": [r"KYC", r"verif(y|ication)", r"identity", r"document"]},
        {"name": "💳 Payment Failures", "explanation": "Transactions are declined or fail for card users.", "keywords": [r"declin(ed|e)", r"payment (fail|error)", r"card error"]},
        {"name": "🏦 Partner/Issuer Issues", "explanation": "Card partner or issuer-specific service disruptions.", "keywords": [r"issuer", r"partner", r"processor", r"provider"]},
    ] + GLOBAL_THEMES,
    "Dashboard": [
        {"name": "📊 Data/Balance Mismatch", "explanation": "Displayed balances or activity differ from on-chain reality.", "keywords": [r"balance", r"not\s+match", r"mismatch", r"wrong amount"]},
        {"name": "🔄 Sync/Refresh Problems", "explanation": "Data takes too long to refresh or fails to sync.", "keywords": [r"refresh", r"sync", r"update", r"delay"]},
    ] + GLOBAL_THEMES,
    "SDK": [
        {"name": "🧩 Integration Errors", "explanation": "Build-time or runtime errors during SDK integration.", "keywords": [r"build", r"compile", r"runtime", r"stack trace", r"exception"]},
        {"name": "🔑 Auth/Permissions", "explanation": "Authentication or permission scopes fail or are unclear.", "keywords": [r"auth", r"permission", r"scope", r"token"]},
    ] + GLOBAL_THEMES,
    "Security": [
        {"name": "🎣 Phishing/Scams", "explanation": "Users report phishing, scams, or suspicious dapps.", "keywords": [r"phish", r"scam", r"fraud", r"malicious"]},
        {"name": "🔐 Recovery/Compromise", "explanation": "Accounts compromised or recovery concerns raised.", "keywords": [r"compromis", r"hack", r"recovery", r"seed phrase"]},
    ] + GLOBAL_THEMES,
    "Snaps": [
        {"name": "🧩 Compatibility/Permissions", "explanation": "Snaps fail due to compatibility or permission prompts.", "keywords": [r"permission", r"compatib(le|ility)", r"snap (fail|error)"]},
    ] + GLOBAL_THEMES,
    "Wallet API": [
        {"name": "🔑 Auth/Rate Limits", "explanation": "API authentication or rate limiting impacts usage.", "keywords": [r"rate limit", r"429", r"auth(entication)?", r"token"]},
        {"name": "📡 Request/Response Errors", "explanation": "Unexpected API errors or schema mismatches.", "keywords": [r"400|401|403|404|500", r"schema", r"invalid", r"error response"]},
    ] + GLOBAL_THEMES,
}

THEME_RECOMMENDATIONS = {
    "🪙 Token Import Confusion": "Improve token detection and network hints; add auto-import suggestions post-swap.",
    "⛽ Gas & Transaction Failures": "Provide clearer gas guidance and fallback strategies when estimates fail.",
    "🔐 Recovery Phrase Misunderstanding": "Reinforce recovery responsibilities during onboarding and restore flows.",
    "🔀 Network/Chain Selection Issues": "Add inline prompts when actions likely require a different network.",
    "🌍 Non-English Language Usage": "Add localized guides and language-aware automated replies for top languages.",
    "📉 Price Impact & Slippage": "Explain price impact up front and suggest safe slippage ranges.",
    "🔒 Allowance/Approval Issues": "Surface allowance state and provide clear approval steps in-flow.",
    "🌉 Route/Bridge Limitations": "Offer alternative routes or explain current routing limitations upfront.",
    "🧾 KYC/Verification": "Preflight checks and clearer KYC status messaging to reduce drop-offs.",
    "💳 Payment/Bank Failures": "Improve decline reason messaging and provide next-step guidance in-app.",
    "📈 On/Off-Ramp Limits": "Show user-specific limits and eligibility criteria before order initiation.",
    "🔓 Withdrawals & Unstaking": "Display realistic timelines and status for unstake/withdrawal stages.",
    "💸 Rewards/APR Timing": "Explain reward accrual cadence and APR variability in-product.",
    "🧭 Validator/Delegation Issues": "Guide validator selection and delegation changes with clearer UI steps.",
    "🤝 Third-Party Staking Providers": "Link provider-specific status pages and constraints inside the flow.",
    "📊 Data/Balance Mismatch": "Provide reconciliation tips and a quick refresh/sync action.",
    "🔄 Sync/Refresh Problems": "Show last-sync timestamp and retry/backoff status visibly.",
    "🧩 Integration Errors": "Expand SDK error docs with common fixes and code samples.",
    "🔑 Auth/Permissions": "Clarify required scopes and token lifetimes with examples.",
    "🎣 Phishing/Scams": "Embed anti-phishing education and quick-report flows.",
    "🔐 Recovery/Compromise": "Provide immediate compromise guidance and revoke-approval steps.",
    "🧩 Compatibility/Permissions": "Preflight required permissions and Snap compatibility checks.",
    "🔑 Auth/Rate Limits": "Document rate limits and recommend pagination/backoff patterns.",
    "📡 Request/Response Errors": "Include schema validators and example payloads in docs and tooling.",
}


def get_last_week_dates():
    """Return start and end strings for last week (Mon 00:00 to Sun 23:59) and YYYYMMDD tokens."""
    est_zone = pytz.timezone("America/New_York")
    now = datetime.now(est_zone)

    last_monday = now - timedelta(days=now.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)

    start_date = last_monday.strftime("%Y-%m-%d 00:00")
    end_date = last_sunday.strftime("%Y-%m-%d 23:59")

    week_start_str = last_monday.strftime("%Y%m%d")
    week_end_str = last_sunday.strftime("%Y%m%d")

    return start_date, end_date, week_start_str, week_end_str


def _daily_windows_utc(start_date_str: str, end_date_str: str):
    """Yield UTC second windows for each EST day in [start, end]."""
    start_naive = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M")
    end_naive = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M")
    cur = TZ_NY.localize(start_naive)
    end = TZ_NY.localize(end_naive)
    while cur <= end:
        day_end = min(cur.replace(hour=23, minute=59), end)
        yield int(cur.astimezone(pytz.utc).timestamp()), int(day_end.astimezone(pytz.utc).timestamp())
        cur = (cur + timedelta(days=1)).replace(hour=0, minute=0)


def remove_html_tags(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"<.*?>", "", text)


def sanitize_text(text: str) -> str:
    if text:
        return text.replace("\u200b", "").encode("utf-8", "ignore").decode("utf-8")
    return ""


def get_conversation_summary(conversation: dict) -> str:
    if "conversation_parts" in conversation:
        parts = conversation["conversation_parts"].get("conversation_parts", [])
        for part in parts:
            if part.get("part_type") == "conversation_summary":
                return remove_html_tags(part.get("body", ""))
    return "No summary available"


def get_conversation_transcript(conversation: dict) -> str:
    transcript_lines = []
    if "conversation_parts" in conversation:
        parts = conversation["conversation_parts"].get("conversation_parts", [])
        for part in parts:
            if part.get("part_type") == "comment":
                author = part.get("author", {}).get("type", "Unknown")
                comment = remove_html_tags(part.get("body", ""))
                transcript_lines.append(f"{author}: {comment}")
    return "\n".join(transcript_lines) if transcript_lines else "No transcript available"


def _iso_from_ts(ts: Optional[int]) -> str:
    if ts is None:
        return ""
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def search_conversations(start_date_str: str, end_date_str: str, session: Optional[requests.Session] = None, end_time: Optional[float] = None):
    """Robust daily-chunked fetch over created_at, updated_at, and last_close_at; deduplicate by id."""
    sess = session or requests.Session()
    def _search_window(field: str, start_ts: int, end_ts: int, per_page: int = SEARCH_PER_PAGE, timeout_s: int = SEARCH_REQUEST_TIMEOUT, max_retries: int = 4):
        url = "https://api.intercom.io/conversations/search"
        headers = {
            "Authorization": f"Bearer {INTERCOM_PROD_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "query": {
                "operator": "AND",
                "value": [
                    {"field": field, "operator": ">", "value": int(start_ts)},
                    {"field": field, "operator": "<", "value": int(end_ts)},
                ],
            },
            "pagination": {"per_page": per_page},
        }

        collected = []
        retries = max_retries
        page_idx = 0
        while True:
            if end_time and time.time() > end_time:
                print(f"[Search] Time budget exceeded during {field} window; returning partial results.")
                break
            try:
                resp = sess.post(url, headers=headers, json=payload, timeout=timeout_s)
                if resp.status_code == 200:
                    data = resp.json()
                    collected.extend(data.get("conversations", []))
                    pages = data.get("pages", {})
                    nxt = pages.get("next")
                    if nxt and "starting_after" in nxt:
                        payload["pagination"]["starting_after"] = nxt["starting_after"]
                        page_idx += 1
                        if page_idx % 5 == 0:
                            print(f"[Search] {field} window page {page_idx} — total collected so far: {len(collected)}")
                    else:
                        break
                elif resp.status_code == 500:
                    if retries > 0:
                        time.sleep(5)
                        retries -= 1
                        continue
                    break
                else:
                    print(f"[{field}] Error {resp.status_code}: {resp.text[:200]}")
                    break
            except requests.exceptions.ReadTimeout:
                if retries > 0:
                    time.sleep(10)
                    retries -= 1
                    continue
                break
            except requests.exceptions.RequestException as ex:
                print(f"[{field}] Request failed: {ex}")
                break
        return collected

    by_id = {}
    windows = list(_daily_windows_utc(start_date_str, end_date_str))
    total_days = len(windows)
    for day_idx, (s_ts, e_ts) in enumerate(windows, start=1):
        # If end_time is provided, it is advisory. We still finish all day windows to ensure full week coverage.
        print(f"[Search] Day {day_idx}/{total_days} window starting…")
        # Closed in window
        closed = _search_window("statistics.last_close_at", s_ts, e_ts)
        for c in closed:
            by_id[c["id"]] = c
        # Created in window (captures open+closed)
        created = _search_window("created_at", s_ts, e_ts)
        for c in created:
            by_id[c["id"]] = c
        # Updated in window (captures active conversations touched)
        updated = _search_window("updated_at", s_ts, e_ts)
        for c in updated:
            by_id[c["id"]] = c

    print(f"[Search] Total unique conversations collected: {len(by_id)}")
    return list(by_id.values())


def get_intercom_conversation(conversation_id: str, session: Optional[requests.Session] = None, cache: Optional[dict] = None, timeout_s: int = DETAIL_FETCH_TIMEOUT):
    if cache is not None and conversation_id in cache:
        return cache[conversation_id]
    url = f"https://api.intercom.io/conversations/{conversation_id}"
    retries = 3
    headers = {"Authorization": f"Bearer {INTERCOM_PROD_KEY}"}
    sess = session or requests.Session()

    while retries > 0:
        try:
            response = sess.get(url, headers=headers, timeout=timeout_s)
            if response.status_code == 200:
                data = response.json()
                if cache is not None:
                    cache[conversation_id] = data
                return data
            if response.status_code == 500:
                retries -= 1
                time.sleep(5)
                continue
            print(f"Error fetching conversation {conversation_id}: {response.status_code}")
            return None
        except requests.exceptions.ReadTimeout:
            retries -= 1
            time.sleep(5)
        except requests.exceptions.RequestException as ex:
            print(f"Request failed for conversation {conversation_id}: {ex}")
            return None
    return None


def filter_conversations_by_product(conversations, product: str, session: Optional[requests.Session], detail_cache: dict, end_time: Optional[float]):
    filtered = []
    target = product.strip()
    total = len(conversations)
    scanned_for_inference = 0
    for idx, conv in enumerate(conversations, start=1):
        # Do not abort early here; we want to finish area processing once search is complete
        if idx % LOG_EVERY == 0:
            print(f"[Area {product}] Scanned {idx}/{total}, matches so far: {len(filtered)}")
        attributes = conv.get("custom_attributes", {}) or {}
        labeled_area = _get_area_attribute(attributes)

        matched = False
        if labeled_area and labeled_area.lower() == target.lower():
            matched = True
        else:
            # Fallback to text inference if area label is missing/mismatched for select areas
            if target in ("Security", "SDK", "Wallet API"):
                if scanned_for_inference >= INFERENCE_SCAN_LIMIT:
                    pass
                else:
                    scanned_for_inference += 1
                    # Pull minimal details to build text for inference
                    full_preview = get_intercom_conversation(conv["id"], session=session, cache=detail_cache) or {}
                    summary = sanitize_text(get_conversation_summary(full_preview))
                    transcript = sanitize_text(get_conversation_transcript(full_preview))
                    combined = f"{summary} \n {transcript}".strip()
                    if _text_suggests_area(combined, target):
                        matched = True
                        # reuse full_preview as the enriched payload
                        conv = full_preview if full_preview else conv

        if matched:
            full = conv if conv.get("conversation_parts") else get_intercom_conversation(conv["id"], session=session, cache=detail_cache)  # enrich with parts
            if full:
                # Merge all attributes; do not prune. Also, add detected area for convenience.
                full_attrs = dict(attributes)
                detected_area = _get_area_attribute(full.get("custom_attributes", {}) or {}) or labeled_area or target
                if detected_area:
                    full_attrs["MetaMask Area (detected)"] = detected_area
                # Carry through area-specific columns for backward compatibility
                for col in CATEGORY_HEADERS.get(product, []):
                    if col not in full_attrs:
                        full_attrs[col] = attributes.get(col, "None")
                # Attach merged attributes
                full["custom_attributes"] = full_attrs
                filtered.append(full)
    print(f"[Area {product}] Matched {len(filtered)} conversations.")
    return filtered


def _gather_attribute_columns(conversations: List[dict]) -> List[str]:
    """Collect union of all custom attribute keys across conversations."""
    cols: Set[str] = set()
    for conv in conversations:
        attrs = conv.get("custom_attributes", {}) or {}
        for k in attrs.keys():
            cols.add(str(k))
    # Prefer to show area keys near the front if present
    ordered = []
    preferred_front = ["MetaMask Area (detected)"] + AREA_ATTRIBUTE_KEYS
    for p in preferred_front:
        if p in cols:
            ordered.append(p)
            cols.remove(p)
    # Keep known attribute names next
    for k in sorted([c for c in cols if c in KNOWN_ATTRIBUTE_NAMES]):
        ordered.append(k)
    remaining = [c for c in cols if c not in KNOWN_ATTRIBUTE_NAMES]
    ordered.extend(sorted(remaining))
    return ordered


def store_conversations_to_xlsx(conversations, meta_mask_area: str, week_start_str: str, week_end_str: str) -> str:
    file_name = f"{meta_mask_area.lower()}_conversations_{week_start_str}_to_{week_end_str}.xlsx"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    # Dynamic attribute headers
    attribute_headers = _gather_attribute_columns(conversations)

    headers = [
        "conversation_id",
        "created_at_iso",
        "updated_at_iso",
        "last_close_at_iso",
        "state",
        "summary",
        "transcript",
    ] + attribute_headers
    sheet.append(headers)

    for conv in conversations:
        conv_id = conv.get("id")
        created_at_iso = _iso_from_ts(conv.get("created_at"))
        updated_at_iso = _iso_from_ts(conv.get("updated_at"))
        last_close_at_iso = _iso_from_ts(((conv.get("statistics") or {}).get("last_close_at")))
        state = conv.get("state", "")
        summary = sanitize_text(get_conversation_summary(conv))
        transcript = sanitize_text(get_conversation_transcript(conv))
        attributes = conv.get("custom_attributes", {}) or {}

        row_values = [conv_id, created_at_iso, updated_at_iso, last_close_at_iso, state, summary, transcript]
        for field in attribute_headers:
            val = attributes.get(field, "N/A")
            if isinstance(val, (dict, list, tuple)):
                try:
                    val = json.dumps(val, ensure_ascii=False)
                except Exception:
                    val = str(val)
            row_values.append(val)
        sheet.append(row_values)

    # Wrap long text columns
    for col in ["F", "G"]:  # summary, transcript
        for cell in sheet[col]:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(file_path)
    print(f"Saved: {file_path}")
    return file_path


# --------------------------
# Insight generation helpers
# --------------------------

def _get_area_taxonomy(area: str) -> Optional[dict]:
    area_norm = (area or "").strip()
    return {
        "Swaps": SWAPS_TAXONOMY,
        "Ramps": RAMPS_TAXONOMY,
        "Dashboard": DASHBOARD_TAXONOMY,
        "Wallet": WALLET_TAXONOMY,
        "Staking": STAKING_TAXONOMY,
        "Snaps": SNAPS_TAXONOMY,
        "Card": CARD_TAXONOMY,
        "Security": SECURITY_TAXONOMY,  # limited reuse for classification lists
    }.get(area_norm)


def _pick_primary_issue_column(df: pd.DataFrame, area: str) -> Optional[str]:
    """Pick the most useful issue column for an area based on non-null volume with heuristics."""
    # 1) Try configured CATEGORY_HEADERS for backward compatibility
    candidates = [c for c in CATEGORY_HEADERS.get(area, []) if c in df.columns]

    # 2) Try area-specific known issue column hints
    for hint in KNOWN_ISSUE_COLUMN_HINTS.get(area, []):
        if hint in df.columns and hint not in candidates:
            candidates.append(hint)

    # 3) Try any columns whose names imply issue/reason/problem
    regex_hints = re.compile(r"(issue|reason|problem|error|training|incident)", re.IGNORECASE)
    for c in df.columns:
        if c in ("conversation_id", "summary", "transcript", "combined_text", "state", "created_at_iso", "updated_at_iso", "last_close_at_iso"):
            continue
        if c in NON_ISSUE_COLUMN_NAMES:
            continue
        if regex_hints.search(str(c)) and c not in candidates:
            candidates.append(c)

    # Never consider known non-issue fields
    candidates = [c for c in candidates if c not in NON_ISSUE_COLUMN_NAMES]

    if not candidates:
        return None

    best_col = None
    best_non_null = -1
    for c in candidates:
        non_null = df[c].replace({"N/A": None, "None": None, "": None, "nan": None}).dropna().shape[0]
        if non_null > best_non_null:
            best_non_null = non_null
            best_col = c
    return best_col


def _format_human_date_range(week_start_str: str, week_end_str: str) -> str:
    try:
        s = datetime.strptime(week_start_str, "%Y%m%d")
        e = datetime.strptime(week_end_str, "%Y%m%d")
        return f"{s.strftime('%B %-d')} – {e.strftime('%B %-d, %Y')}"
    except Exception:
        # Fallback without platform-specific day formatting
        s = datetime.strptime(week_start_str, "%Y%m%d")
        e = datetime.strptime(week_end_str, "%Y%m%d")
        return f"{s.strftime('%B %d')} – {e.strftime('%B %d, %Y')}"


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9']+", text)
    return [t for t in tokens if t not in STOP_WORDS]


def _top_phrases(texts: List[str], max_phrases: int = 5) -> List[str]:
    """Return up to max_phrases of the most frequent bigrams/trigrams from texts."""
    bigram_counts: Counter = Counter()
    trigram_counts: Counter = Counter()

    for txt in texts:
        tokens = _tokenize(txt or "")
        if not tokens:
            continue
        # bigrams
        for i in range(len(tokens) - 1):
            bigram = (tokens[i], tokens[i + 1])
            if all(t not in STOP_WORDS for t in bigram):
                bigram_counts[bigram] += 1
        # trigrams
        for i in range(len(tokens) - 2):
            trigram = (tokens[i], tokens[i + 1], tokens[i + 2])
            if all(t not in STOP_WORDS for t in trigram):
                trigram_counts[trigram] += 1

    # Combine and pick top
    combined = []
    combined.extend(list(bigram_counts.items()))
    combined.extend(list(trigram_counts.items()))
    combined.sort(key=lambda kv: kv[1], reverse=True)

    phrases = []
    for ngram, _cnt in combined[: max_phrases * 2]:
        phrase = ", ".join(ngram) if len(ngram) > 2 else " ".join(ngram)
        if phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) >= max_phrases:
            break
    return phrases


def _score_themes(texts: List[str], area: str, max_themes: int = 5) -> List[tuple[str, int]]:
    """Score themes by counting conversations where the theme appears at least once (binary per conversation)."""
    themes = AREA_THEMES.get(area, GLOBAL_THEMES)
    scores = []
    for theme in themes:
        patt = re.compile("|".join(theme.get("keywords", [])), flags=re.IGNORECASE)
        count = 0
        for t in texts:
            if not t:
                continue
            # Count once per conversation if there is at least one match
            if patt.search(t):
                count += 1
        if count > 0:
            scores.append((theme["name"], count))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:max_themes]


def _theme_details(area: str, theme_name: str) -> tuple[str, str]:
    for theme in AREA_THEMES.get(area, GLOBAL_THEMES):
        if theme["name"] == theme_name:
            return theme["name"], theme.get("explanation", "")
    for theme in GLOBAL_THEMES:
        if theme["name"] == theme_name:
            return theme["name"], theme.get("explanation", "")
    return theme_name, "Observed frequently in user conversations."


def _title_with_emoji(area: str, issue: str) -> str:
    key = (issue or "").strip().lower()
    if area.lower() == "wallet":
        if key == "user training":
            return "👨‍🏫 User Training"
        if key == "transaction issue":
            return "🔁 Transaction Issue"
        if key == "balance issue":
            return "💰 Balance Issue"
    return f"🔎 {issue or 'Issue'}"


def _theme_pattern(area: str, theme_name: str) -> Optional[re.Pattern]:
    for theme in AREA_THEMES.get(area, GLOBAL_THEMES):
        if theme["name"] == theme_name:
            return re.compile("|".join(theme.get("keywords", [])), flags=re.IGNORECASE)
    return None


def _series_nonempty_mask(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.replace({"nan": "", "None": "", "N/A": ""})
    return s != ""


def _compute_top_issues(df: pd.DataFrame, area: str) -> tuple[List[tuple[str, int]], Dict[str, pd.Series]]:
    """Compute top issues based on provided category columns for the area.
    Returns (sorted_issues, label_to_mask)."""
    label_to_count: Dict[str, int] = {}
    label_to_mask: Dict[str, pd.Series] = {}
    source_cols = [c for c in AREA_ISSUE_SOURCES.get(area, []) if c in df.columns]

    if not source_cols:
        return [], {}

    for col in source_cols:
        col_series = df[col]
        # If column appears to have categorical values (strings beyond empty), count by value
        # Otherwise treat presence in the column as the issue named by the column itself
        nonempty_mask = _series_nonempty_mask(col_series)
        if nonempty_mask.sum() == 0:
            continue
        # Heuristic: if there are multiple distinct non-empty values and the column name ends with 'issue' or contains ':'
        distinct_vals = (
            col_series[nonempty_mask].astype(str).str.strip().replace({"nan": ""}).value_counts()
        )
        if len(distinct_vals.index) > 1 or any(x in col.lower() for x in ["issue", ":"]):
            # Count by values
            for val, cnt in distinct_vals.items():
                if not val:
                    continue
                label = val
                label_to_count[label] = label_to_count.get(label, 0) + int(cnt)
                mask = col_series.astype(str).str.strip().eq(val)
                if label in label_to_mask:
                    label_to_mask[label] = label_to_mask[label] | mask
                else:
                    label_to_mask[label] = mask
        else:
            # Treat the column name as the issue label
            label = col
            cnt = int(nonempty_mask.sum())
            label_to_count[label] = label_to_count.get(label, 0) + cnt
            if label in label_to_mask:
                label_to_mask[label] = label_to_mask[label] | nonempty_mask
            else:
                label_to_mask[label] = nonempty_mask

    # Remove known non-issue labels if they slipped in
    for bad in list(label_to_count.keys()):
        if bad in NON_ISSUE_COLUMN_NAMES:
            label_to_count.pop(bad, None)
            label_to_mask.pop(bad, None)

    # Rank and take top 3
    sorted_issues = sorted(label_to_count.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return sorted_issues, label_to_mask


def analyze_xlsx_and_generate_insights(
    xlsx_file: str, meta_mask_area: str, week_start_str: str, week_end_str: str
) -> str:
    print(f"Analyzing {xlsx_file} for {meta_mask_area}…")
    df = pd.read_excel(xlsx_file)
    df.columns = df.columns.str.strip()

    # Compute top issues via category sources first
    top_issue_list, issue_masks = _compute_top_issues(df, meta_mask_area)

    issue_col = None  # legacy path disabled when dynamic issues are present
    if not top_issue_list:
        # Fallback to legacy single-column heuristic if no sources available
        issue_col = _pick_primary_issue_column(df, meta_mask_area)

    insights_file = os.path.join(
        INSIGHTS_DIR,
        f"{meta_mask_area.lower()}_insights_{week_start_str}_to_{week_end_str}.txt",
    )

    # Ensure combined_text exists early for all paths
    if "combined_text" not in df.columns:
        summary_series = df["summary"].astype(str) if "summary" in df.columns else pd.Series([""] * len(df))
        transcript_series = df["transcript"].astype(str) if "transcript" in df.columns else pd.Series([""] * len(df))
        df["combined_text"] = summary_series.fillna("") + " " + transcript_series.fillna("")

    # Escalation detection
    def _is_escalated(text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in ESCALATION_KEYWORDS)

    if "transcript" in df.columns:
        escalation_count = df["transcript"].astype(str).apply(_is_escalated).sum()
    else:
        escalation_count = 0

    # If no taxonomy column exists, synthesize issues directly from area themes
    synthesized_issues = None
    issues_series = None
    top_counts = None

    if top_issue_list:
        # Use dynamic issues
        top_counts = top_issue_list
    else:
        if issue_col is None:
            area_texts_all = df["combined_text"].astype(str).fillna("").tolist()
            theme_scores_all = _score_themes(area_texts_all, meta_mask_area, max_themes=3)
            if theme_scores_all:
                synthesized_issues = [(name, score) for name, score in theme_scores_all]
            else:
                phrases = _top_phrases(area_texts_all, max_phrases=3)
                synthesized_issues = [(p.title(), 1) for p in phrases] if phrases else []
        else:
            issues_series = (
                df[issue_col]
                .astype(str)
                .str.strip()
                .replace({"nan": None, "None": None, "N/A": None, "": None})
                .dropna()
            )
            vc = issues_series.value_counts().head(3)
            top_counts = list(vc.items())
            if not top_counts:
                area_texts = df["combined_text"].astype(str).fillna("").tolist()
                theme_scores = _score_themes(area_texts, meta_mask_area, max_themes=3)
                if theme_scores:
                    synthesized_issues = [(name, score) for name, score in theme_scores]

    total_area_rows = len(df)

    # Header
    human_range = _format_human_date_range(week_start_str, week_end_str)
    lines: List[str] = []
    lines.append(f"📝 MetaMask {meta_mask_area} Support — Focused Issue Report")
    lines.append(f"Date Range: {human_range}")
    lines.append(f"Conversation Volume Analyzed: {total_area_rows:,} total")
    if total_area_rows:
        esc_pct = (escalation_count / total_area_rows * 100.0) if total_area_rows else 0.0
        # Replace with simplified phrasing without percentage
        lines.append(f"Conversations Elevated to Technical Support: {escalation_count:,}")
    lines.append(f"Focus: Top 3 {meta_mask_area} Issues by Volume")
    lines.append("")
    lines.append(f"📊 Top 3 {meta_mask_area} Issues")
    lines.append(f"{meta_mask_area} Issue\tConversations\t% of Total")

    if synthesized_issues is not None:
        for issue, cnt in synthesized_issues:
            pct = (cnt / total_area_rows * 100.0) if total_area_rows else 0.0
            lines.append(f"{issue}\t{cnt:,}\t{pct:.1f}%")
    else:
        for issue, cnt in top_counts:
            pct = (cnt / total_area_rows * 100.0) if total_area_rows else 0.0
            lines.append(f"{issue}\t{cnt:,}\t{pct:.1f}%")

    # Sections (dynamic for all areas)
    all_issue_texts_for_takeaways = []
    issue_iterable = []
    if synthesized_issues is not None:
        issue_iterable = synthesized_issues
    else:
        issue_iterable = list(top_counts)

    def _clean_sample(text: str, limit: int = 240) -> str:
        t = remove_html_tags(text or "").strip()
        return (t[: limit].rstrip() + ("…" if len(t) > limit else "")) if t else ""

    def _is_low_signal(phrase: str) -> bool:
        return any(pat.search(phrase) for pat in DISALLOWED_PHRASE_PATTERNS)

    for issue, cnt in issue_iterable:
        lines.append("")
        title = _title_with_emoji(meta_mask_area, issue)
        lines.append(f"{title} ({cnt:,} conversations)")
        if synthesized_issues is not None:
            patt = _theme_pattern(meta_mask_area, issue)
            all_texts = df["combined_text"].astype(str).fillna("").tolist()
            issue_texts = [t for t in all_texts if patt and patt.search(t)]
            current_mask = None
        else:
            if top_issue_list:
                current_mask = issue_masks.get(issue)
                if current_mask is None:
                    current_mask = pd.Series([False] * len(df))
                issue_texts = df.loc[current_mask, "combined_text"].astype(str).fillna("").tolist()
            else:
                issue_mask = df[issue_col].astype(str).str.strip().eq(str(issue))
                issue_mask = issue_mask.reindex(df.index, fill_value=False)
                current_mask = issue_mask
                issue_texts = df.loc[current_mask, "combined_text"].astype(str).fillna("").tolist()
        all_issue_texts_for_takeaways.extend(issue_texts)

        # Area-specific diagnostics
        if meta_mask_area == "Security":
            total_issue_conversations = max(1, len(issue_texts))
            issue_key = (issue or "").lower()
            # Leading reasons for Recovery/Compromise
            if ("compromise" in issue_key) or ("recovery" in issue_key):
                reason_counts = _count_binary_reason_hits(issue_texts, SECURITY_COMPROMISE_REASON_PATTERNS)
                if reason_counts:
                    lines.append("Why this occurs (leading reasons):")
                    for reason, rcnt in reason_counts[:5]:
                        pct = rcnt / total_issue_conversations * 100.0
                        lines.append(f"- {reason}: {rcnt:,} ({pct:.1f}%)")
                # Taxonomy breakdowns (Reason/Vector/Method/User error/Unintended interaction)
                tax = _score_taxonomy(issue_texts, SECURITY_TAXONOMY, top_n=6)
                if tax:
                    lines.append("Related classifications:")
                    for label, rcnt in tax:
                        pct = rcnt / total_issue_conversations * 100.0
                        # pretty print "Category|Value"
                        if "|" in label:
                            cat, val = label.split("|", 1)
                            lines.append(f"- {cat}: {val} — {rcnt:,} ({pct:.1f}%)")
                        else:
                            lines.append(f"- {label}: {rcnt:,} ({pct:.1f}%)")
            # Top suspicious domains/dapps for Phishing/Scams
            if ("phishing" in issue_key) or ("scam" in issue_key) or ("🎣" in issue):
                top_domains = _top_suspicious_domains(issue_texts, top_n=5)
                if top_domains:
                    lines.append("Most common suspicious domains/dapps:")
                    for dom, dcnt in top_domains:
                        pct = dcnt / total_issue_conversations * 100.0
                        lines.append(f"- {dom}: {dcnt:,} ({pct:.1f}%)")
        # Generic taxonomy diagnostics for other areas (Swaps, Ramps, Dashboard, Wallet)
        if meta_mask_area in ("Swaps", "Ramps", "Dashboard"):
            total_issue_conversations = max(1, len(issue_texts))
            area_tax = _get_area_taxonomy(meta_mask_area)
            if area_tax:
                tax_scores = _score_taxonomy(issue_texts, area_tax, top_n=8)
                if tax_scores:
                    lines.append("Related classifications:")
                    for label, rcnt in tax_scores:
                        pct = rcnt / total_issue_conversations * 100.0
                        if "|" in label:
                            cat, val = label.split("|", 1)
                            lines.append(f"- {cat}: {val} — {rcnt:,} ({pct:.1f}%)")
                        else:
                            lines.append(f"- {label}: {rcnt:,} ({pct:.1f}%)")

        # Prefer theme-based explanations when available
        theme_scores = _score_themes(issue_texts, meta_mask_area, max_themes=5)
        if theme_scores:
            for theme_name, _score in theme_scores:
                h, expl = _theme_details(meta_mask_area, theme_name)
                lines.append(h)
                lines.append(expl or "Observed frequently in user conversations.")
                lines.append("")
            if lines and lines[-1] == "":
                lines.pop()
        else:
            # Fallback to phrases
            phrases = _top_phrases(issue_texts, max_phrases=5)
            if phrases:
                for p in phrases:
                    if _is_low_signal(p):
                        continue
                    lines.append(p.title())
                    lines.append("Observed frequently in user conversations.")
                    lines.append("")
                if lines and lines[-1] == "":
                    lines.pop()
            else:
                lines.append("- No dominant topical themes detected.")

        # Representative examples
        # Prefer summaries; if empty, fallback to transcript snippets
        lines.append("")
        lines.append("Representative examples:")
        examples = []
        if synthesized_issues is None and 'summary' in df.columns:
            if top_issue_list:
                subset = df.loc[current_mask, 'summary'].astype(str).fillna("")
            else:
                subset = df.loc[issue_mask, 'summary'].astype(str).fillna("")
            for s in subset.head(5).tolist():
                cleaned = _clean_sample(s)
                if cleaned and not _is_low_signal(cleaned):
                    examples.append(f"- {cleaned}")
                if len(examples) >= 3:
                    break
        if len(examples) < 3 and 'transcript' in df.columns:
            if synthesized_issues is None:
                if top_issue_list:
                    tsubset = df.loc[current_mask, 'transcript'].astype(str).fillna("")
                else:
                    tsubset = df.loc[issue_mask, 'transcript'].astype(str).fillna("")
            else:
                patt = _theme_pattern(meta_mask_area, issue)
                all_transcripts = df['transcript'].astype(str).fillna("")
                mask = all_transcripts.apply(lambda s: bool(patt.search(s)) if patt and isinstance(s, str) else False)
                tsubset = all_transcripts[mask]
            for s in tsubset.head(8).tolist():
                cleaned = _clean_sample(s)
                if cleaned and not _is_low_signal(cleaned):
                    examples.append(f"- {cleaned}")
                if len(examples) >= 3:
                    break
        if examples:
            lines.extend(examples)

    # Key takeaways (dynamic for all areas)
    lines.append("")
    lines.append("🎯 Key Takeaways")
    if synthesized_issues is not None:
        if synthesized_issues:
            dom_issue, dom_cnt = synthesized_issues[0]
            dom_pct = (dom_cnt / max(1, total_area_rows)) * 100.0
            lines.append(f"✅ {dom_issue} appears most frequently ({dom_pct:.1f}% of analyzed conversations).")
    else:
        if top_counts is not None and not top_counts.empty:
            top_issue, top_cnt = next(iter(top_counts.items()))
            top_pct = (top_cnt / total_area_rows * 100.0) if total_area_rows else 0.0
            lines.append(f"✅ {top_issue} drives a significant share ({top_pct:.1f}%) of weekly volume.")

    # Theme-driven recommendations
    top_area_themes = _score_themes(all_issue_texts_for_takeaways, meta_mask_area, max_themes=3)
    if top_area_themes:
        rec_added = set()
        for theme_name, _score in top_area_themes:
            rec = THEME_RECOMMENDATIONS.get(theme_name)
            if rec and rec not in rec_added:
                lines.append(f"✅ {rec}")
                rec_added.add(rec)
    lines.append("✅ Consider proactive guidance and clearer in-product messaging to reduce repeat issues.")

    with open(insights_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Insights written: {insights_file}")
    return insights_file


def upload_to_google_drive_v3(service, file_path: str) -> bool:
    file_name = os.path.basename(file_path)
    folder_id = GDRIVE_FOLDER_ID

    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=True)

    try:
        created = (
            service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        )
        print(f"Uploaded {file_name} (File ID: {created.get('id')})")
        return True
    except Exception as ex:
        print(f"Upload failed for {file_name}: {ex}")
        return False


def authenticate_google_drive_via_service_account():
    try:
        env_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if env_json:
            service_account_info = json.loads(env_json)
        else:
            with open("service_account_key.json") as f:
                service_account_info = json.load(f)

        credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build("drive", "v3", credentials=credentials)
        return drive_service
    except Exception as ex:
        print(f"Google Drive auth failed: {ex}")
        return None


def main_function(start_date: str, end_date: str, week_start_str: str, week_end_str: str):
    print(f"Searching for conversations from {start_date} to {end_date}…")
    start_ts = time.time()
    deadline = start_ts + MAX_RUNTIME_SEC if MAX_RUNTIME_SEC > 0 else None
    session = requests.Session()
    detail_cache: dict = {}

    conversations = search_conversations(start_date, end_date, session=session, end_time=deadline)
    if not conversations:
        print("No conversations found in the selected time window.")
        return

    generated_xlsx: Set[str] = set()
    generated_insights: Set[str] = set()

    for area in CATEGORY_HEADERS.keys():
        print(f"[Area {area}] Filtering conversations…")
        filtered = filter_conversations_by_product(conversations, area, session=session, detail_cache=detail_cache, end_time=deadline)
        if not filtered:
            continue

        xlsx_path = store_conversations_to_xlsx(filtered, area, week_start_str, week_end_str)
        generated_xlsx.add(xlsx_path)

        insights_path = analyze_xlsx_and_generate_insights(
            xlsx_path, area, week_start_str, week_end_str
        )
        if insights_path:
            generated_insights.add(insights_path)

    drive_service = authenticate_google_drive_via_service_account()
    if drive_service is None:
        print("Skipping uploads due to Drive auth failure.")
        return

    if not generated_xlsx and not generated_insights:
        print("Nothing to upload (no files generated).")
        return
    print(f"Uploading generated files… (XLSX={len(generated_xlsx)}, Insights={len(generated_insights)})")
    for fpath in sorted(generated_xlsx):
        upload_to_google_drive_v3(drive_service, fpath)
    for fpath in sorted(generated_insights):
        upload_to_google_drive_v3(drive_service, fpath)
    print("All files uploaded.")


if __name__ == "__main__":
    s, e, ws, we = get_last_week_dates()
    print(f"Running script for: {s} to {e}…")
    main_function(s, e, ws, we)