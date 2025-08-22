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
from typing import Optional, List, Set
from openpyxl import Workbook
from openpyxl.styles import Alignment
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# Load environment variables early
load_dotenv()

API_KEY = os.getenv("API_KEY")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
INTERCOM_PROD_KEY = os.getenv("INTERCOM_PROD_KEY")


# MetaMask Areas and their related subcategory columns captured in the XLSX output
CATEGORY_HEADERS = {
    "Card": [
        "MM Card Issue",
        "MM Card Partner issue",
        "Dashboard Issue",
        "KYC Issue",
        "Dashboard Issue - Subcategory",
        "KYC Issue - Subcategory",
    ],
    "Dashboard": ["Dashboard issue"],
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


def search_conversations(start_date_str: str, end_date_str: str):
    """Fetch all conversations from Intercom within the time window, with basic retry on errors."""
    start_timestamp = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M").timestamp()
    end_timestamp = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M").timestamp()

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
                {"field": "statistics.last_close_at", "operator": ">", "value": int(start_timestamp)},
                {"field": "statistics.last_close_at", "operator": "<", "value": int(end_timestamp)},
            ],
        },
        "pagination": {"per_page": 100},
    }

    all_conversations = []
    retries = 3

    while True:
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                all_conversations.extend(data.get("conversations", []))

                pages = data.get("pages", {})
                next_info = pages.get("next")
                if next_info and "starting_after" in next_info:
                    payload["pagination"]["starting_after"] = next_info["starting_after"]
                else:
                    break
            elif response.status_code == 500:
                if retries > 0:
                    time.sleep(5)
                    retries -= 1
                    continue
                break
            else:
                print(f"Error: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.ReadTimeout:
            if retries > 0:
                time.sleep(10)
                retries -= 1
                continue
            break
        except requests.exceptions.RequestException as ex:
            print(f"Request failed: {ex}")
            return None

    return all_conversations


def get_intercom_conversation(conversation_id: str):
    url = f"https://api.intercom.io/conversations/{conversation_id}"
    retries = 3
    headers = {"Authorization": f"Bearer {INTERCOM_PROD_KEY}"}

    while retries > 0:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 500:
                retries -= 1
                time.sleep(5)
                continue
            print(f"Error fetching conversation {conversation_id}: {response.status_code}")
            return None
        except requests.exceptions.ReadTimeout:
            retries -= 1
            time.sleep(10)
        except requests.exceptions.RequestException as ex:
            print(f"Request failed for conversation {conversation_id}: {ex}")
            return None
    return None


def filter_conversations_by_product(conversations, product: str):
    filtered = []
    for conv in conversations:
        attributes = conv.get("custom_attributes", {})
        meta_mask_area = (attributes.get("MetaMask area", "") or "").strip()
        if meta_mask_area.lower() == product.lower():
            full = get_intercom_conversation(conv["id"])  # enrich with parts
            if full:
                # Carry through the custom attributes we care about for this area
                full_attrs = full.get("custom_attributes", {}) or {}
                for col in CATEGORY_HEADERS.get(product, []):
                    full_attrs[col] = attributes.get(col, "None")
                full["custom_attributes"] = full_attrs
                filtered.append(full)
    return filtered


def store_conversations_to_xlsx(conversations, meta_mask_area: str, week_start_str: str, week_end_str: str) -> str:
    file_name = f"{meta_mask_area.lower()}_conversations_{week_start_str}_to_{week_end_str}.xlsx"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    headers = ["conversation_id", "summary", "transcript"] + CATEGORY_HEADERS.get(meta_mask_area, [])
    sheet.append(headers)

    for conv in conversations:
        conv_id = conv.get("id")
        summary = sanitize_text(get_conversation_summary(conv))
        transcript = sanitize_text(get_conversation_transcript(conv))
        attributes = conv.get("custom_attributes", {})

        row_values = [conv_id, summary, transcript]
        for field in CATEGORY_HEADERS.get(meta_mask_area, []):
            row_values.append(attributes.get(field, "N/A"))
        sheet.append(row_values)

    # Wrap long text columns
    for col in ["B", "C"]:
        for cell in sheet[col]:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(file_path)
    print(f"Saved: {file_path}")
    return file_path


# --------------------------
# Insight generation helpers
# --------------------------

def _pick_primary_issue_column(df: pd.DataFrame, area: str) -> Optional[str]:
    """Pick the most useful issue column for an area based on non-null volume."""
    candidates = [c for c in CATEGORY_HEADERS.get(area, []) if c in df.columns]
    if not candidates:
        return None
    best_col = None
    best_non_null = -1
    for c in candidates:
        non_null = df[c].replace({"N/A": None, "None": None, "": None}).dropna().shape[0]
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
    themes = AREA_THEMES.get(area, GLOBAL_THEMES)
    scores = []
    for theme in themes:
        patt = re.compile("|".join(theme.get("keywords", [])), flags=re.IGNORECASE)
        count = 0
        for t in texts:
            if not t:
                continue
            hits = len(patt.findall(t))
            count += hits
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


def analyze_xlsx_and_generate_insights(
    xlsx_file: str, meta_mask_area: str, week_start_str: str, week_end_str: str
) -> str:
    print(f"Analyzing {xlsx_file} for {meta_mask_area}…")
    df = pd.read_excel(xlsx_file)
    df.columns = df.columns.str.strip()

    issue_col = _pick_primary_issue_column(df, meta_mask_area)
    insights_file = os.path.join(
        INSIGHTS_DIR,
        f"{meta_mask_area.lower()}_insights_{week_start_str}_to_{week_end_str}.txt",
    )

    if issue_col is None:
        with open(insights_file, "w", encoding="utf-8") as f:
            f.write(
                f"📝 MetaMask {meta_mask_area} Support — Focused Issue Report\n"
                f"Date Range: {_format_human_date_range(week_start_str, week_end_str)}\n"
                f"Conversation Volume Analyzed: {len(df):,} total\n\n"
                f"No issue taxonomy found for this area."
            )
        print(f"Insights written: {insights_file}")
        return insights_file

    # Ensure combined_text exists
    if "combined_text" not in df.columns:
        summary_series = df["summary"].astype(str) if "summary" in df.columns else pd.Series([""] * len(df))
        transcript_series = df["transcript"].astype(str) if "transcript" in df.columns else pd.Series([""] * len(df))
        df["combined_text"] = summary_series.fillna("") + " " + transcript_series.fillna("")

    issues_series = (
        df[issue_col]
        .astype(str)
        .str.strip()
        .replace({"nan": None, "None": None, "N/A": None, "": None})
        .dropna()
    )

    total_area_rows = len(df)
    top_counts = issues_series.value_counts().head(3)

    # Fallback: if no labeled issues, synthesize issues from area themes
    synthesized_issues = None
    if top_counts.empty:
        area_texts = df["combined_text"].astype(str).fillna("").tolist()
        theme_scores = _score_themes(area_texts, meta_mask_area, max_themes=3)
        if theme_scores:
            synthesized_issues = [(name, score) for name, score in theme_scores]

    # Header
    human_range = _format_human_date_range(week_start_str, week_end_str)
    lines: List[str] = []
    lines.append(f"📝 MetaMask {meta_mask_area} Support — Focused Issue Report")
    lines.append(f"Date Range: {human_range}")
    lines.append(f"Conversation Volume Analyzed: {total_area_rows:,} total")
    lines.append(f"Focus: Top 3 {meta_mask_area} Issues by Volume")
    lines.append("")
    lines.append(f"📊 Top 3 {meta_mask_area} Issues")
    lines.append(f"{meta_mask_area} Issue\tConversations\t% of Total")
    if synthesized_issues is not None:
        total_for_pct = sum(v for _k, v in synthesized_issues) or 1
        for issue, cnt in synthesized_issues:
            pct = (cnt / total_for_pct * 100.0)
            lines.append(f"{issue}\t{cnt:,}\t{pct:.1f}%")
    else:
        for issue, cnt in top_counts.items():
            pct = (cnt / total_area_rows * 100.0) if total_area_rows else 0.0
            lines.append(f"{issue}\t{cnt:,}\t{pct:.1f}%")

    # Sections (dynamic for all areas)
    all_issue_texts_for_takeaways = []
    issue_iterable = []
    if synthesized_issues is not None:
        issue_iterable = synthesized_issues
    else:
        issue_iterable = list(top_counts.items())

    for issue, cnt in issue_iterable:
        lines.append("")
        title = _title_with_emoji(meta_mask_area, issue)
        lines.append(f"{title} ({cnt:,} conversations)")
        if synthesized_issues is not None:
            # Use all texts for synthesized theme issues (already theme-derived)
            issue_texts = df["combined_text"].astype(str).fillna("").tolist()
        else:
            issue_mask = df[issue_col].astype(str).str.strip().eq(str(issue))
            issue_mask = issue_mask.reindex(df.index, fill_value=False)
            issue_texts = df.loc[issue_mask, "combined_text"].astype(str).fillna("").tolist()
        all_issue_texts_for_takeaways.extend(issue_texts)
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
                    lines.append(p.title())
                    lines.append("Observed frequently in user conversations.")
                    lines.append("")
                if lines and lines[-1] == "":
                    lines.pop()
            else:
                lines.append("- No dominant topical themes detected.")

    # Key takeaways (dynamic for all areas)
    lines.append("")
    lines.append("🎯 Key Takeaways")
    if synthesized_issues is not None:
        if synthesized_issues:
            dom_issue, dom_cnt = synthesized_issues[0]
            dom_pct = (dom_cnt / max(1, sum(v for _k, v in synthesized_issues))) * 100.0
            lines.append(f"✅ {dom_issue} appears most frequently ({dom_pct:.1f}% of detected themes).")
    else:
        if not top_counts.empty:
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
    conversations = search_conversations(start_date, end_date)
    if not conversations:
        print("No conversations found in the selected time window.")
        return

    generated_xlsx: Set[str] = set()
    generated_insights: Set[str] = set()

    for area in CATEGORY_HEADERS.keys():
        filtered = filter_conversations_by_product(conversations, area)
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

    print("Uploading generated files…")
    for fpath in sorted(generated_xlsx):
        upload_to_google_drive_v3(drive_service, fpath)
    for fpath in sorted(generated_insights):
        upload_to_google_drive_v3(drive_service, fpath)
    print("All files uploaded.")


if __name__ == "__main__":
    s, e, ws, we = get_last_week_dates()
    print(f"Running script for: {s} to {e}…")
    main_function(s, e, ws, we)

