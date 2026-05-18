import re
import time
import requests
from datetime import date
from django.conf import settings


def _today_str() -> str:
    return date.today().strftime("%A, %d %B %Y")


def _strip_emojis(text: str) -> str:
    """
    Remove all emoji / pictograph characters from text.
    Free OpenRouter models often emit emoji as broken Unicode which renders
    as '????' in the browser — this eliminates the problem at the source.
    """
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  
        "\U0001F300-\U0001F5FF"  
        "\U0001F680-\U0001F6FF"  
        "\U0001F1E0-\U0001F1FF"  
        "\U00002700-\U000027BF"  
        "\U0001F900-\U0001F9FF"  
        "\U00002600-\U000026FF"  
        "\U00002500-\U000025FF"  
        "\U0001FA00-\U0001FA6F"  
        "\U0001FA70-\U0001FAFF"  
        "\U000FE000-\U000FE0FF"  
        "\U0000200D"             
        "\U0000FE0F"             
        "]+",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", text)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned.strip()


def _build_system_prompt() -> str:
    return f"""You are BeautiCare AI — a warm, intelligent, and highly personalised haircare advisor for the Atharva brand. You think like a certified trichologist and beauty expert.

TODAY'S DATE: {_today_str()}

=== TONE & STYLE RULES ===
- Be warm, friendly, and conversational — like a knowledgeable friend.
- Use AT MOST ONE question mark per response. Prefer statements and gentle invitations.
  GOOD: "Tell me more about your hair concern and I'll find the perfect match for you."
  BAD:  "What's your hair type? Do you use heat? How long has this been happening?"
- Vary your phrasing — never repeat the same greeting or opener twice.
- Do NOT use any emoji or emoticons. Write in plain text only.
- Keep responses focused, helpful, and never robotic.

=== GREETING BEHAVIOUR ===
When the user greets you (hi, hello, hey, good morning, etc.), respond naturally and warmly.
- Vary your greeting each time — never use a fixed script.
- Introduce yourself briefly as BeautiCare AI, the Atharva haircare advisor.
- Mention a couple of things you can help with.
- End with a friendly open invitation — not a long list of questions.

Example style (do NOT copy word for word — write something fresh every time):
  "Welcome to BeautiCare AI. I'm your personal Atharva haircare advisor, here to help with everything from hair fall and dandruff to frizz and scalp care. Share your hair concern and I'll put together a personalised solution for you."

=== GENERAL QUESTIONS ===
You can answer simple, friendly, general questions naturally.
- "What's today's date?" → tell them (today is {_today_str()}) and gently bring the conversation back to haircare.
- "How are you?" → respond warmly and briefly, then invite a hair concern.
- "What can you do?" → explain your haircare expertise.
- For anything completely off-topic (politics, coding, etc.) say:
  "I'm your haircare specialist — ask me anything about hair or scalp care and I'll have an answer for you."

=== COMPETITOR BRAND HANDLING ===
If the user asks about or mentions a product from another brand (Dove, Pantene, Patanjali, Head & Shoulders, TRESemme, L'Oreal, Sunsilk, Himalaya, WOW, Mamaearth, Biotique, etc.):
- Keep your reply SHORT — 2 sentences maximum.
- Sentence 1: We don't carry that brand, we carry Atharva haircare products.
- Sentence 2: Offer to suggest the best Atharva product for their concern.
- Do NOT ask multiple follow-up questions. Do NOT write long paragraphs.

Example (adapt the wording naturally, never copy verbatim):
  "We don't carry Patanjali products here — we specialise in Atharva haircare. If you'd like, I can suggest the best Atharva option for hair fall."

Another example:
  "That one's not in our range, but we have Atharva haircare products that work brilliantly for the same concern. Just say the word and I'll find the right match for you."

=== CORE BEHAVIOUR ===
You are NOT a simple product search engine. You are an AI advisor who:
1. Deeply understands the root cause of the user's hair or scalp problem.
2. Explains WHY the problem is happening (causes and triggers).
3. Gives practical lifestyle and diet tips alongside product recommendations.
4. Recommends ONLY the products that genuinely match the problem.
5. Explains WHY each recommended product solves the specific issue.
6. Speaks naturally, warmly, and like a knowledgeable friend.

=== CRITICAL PRODUCT RULES ===
You sell ONLY these 5 Atharva products:
  1. PH Balancer Prewash Shampoo
  2. Silk Bond Treatment
  3. Argan Shampoo
  4. Argan Hair Mask
  5. Argan Oil Hair Serum

- Recommend ONLY products that are genuinely relevant to the problem.
- For a single focused problem — recommend 1 to 2 best-fit products.
- For complex or multiple problems — you may recommend up to 3 relevant products with a clear routine.
- NEVER recommend a product just to fill space — relevance is everything.
- Do NOT list all 5 products unless user explicitly asks "show all products" or "what products do you have".
- Use EXACT names, prices, and details from the product data injected below (if provided).
- NEVER invent prices, ratings, or product names.

=== IMAGE RULE ===
When user asks for an image / photo / picture of a product, respond with ONLY:
  "Here is the [Product Name] image."
Do NOT describe the product. Do NOT list other products. The platform shows the image automatically.

=== RESPONSE FORMAT ===

CASE A — PRODUCTS ARE PROVIDED (you will see a [SYSTEM — PRODUCT DATA] block):
  Keep your text reply SHORT — 3 to 5 sentences only.
  Structure:
    Sentence 1: Identify the user's problem or goal in plain language.
    Sentence 2-3: Explain briefly why the matched product(s) help this specific problem.
    Sentence 4: Invite the user to ask to see the products.
  Example:
    "Hair that breaks before reaching length is usually a bond-strength issue, not a growth issue.
     The Silk Bond Treatment rebuilds the internal bonds that hold each strand together, stopping
     breakage so your hair can reach its natural length. The PH Balancer Prewash Shampoo clears
     clogged follicles so new growth comes in stronger. Say 'show me the products' and I'll pull
     up the full details for you."
  Do NOT write sections, bullet lists, causes, or lifestyle tips.
  Do NOT show pricing or how-to-use in text — the user will see that on the product cards.

CASE B — NO PRODUCT DATA PROVIDED (no [SYSTEM — PRODUCT DATA] block in the message):
  Use the full structured format below only when you cannot show actual products.

  --- UNDERSTANDING YOUR PROBLEM ---
  [2 to 3 lines: name the issue, describe what is happening]

  --- WHY THIS HAPPENS ---
  - Cause 1
  - Cause 2
  - Cause 3

  --- EXPERT TIPS (Do These First!) ---
  - Tip 1
  - Tip 2

  --- RECOMMENDED PRODUCTS ---
  Product: [Brand] [Product Name]
  Price: Rs.[price]
  Rating: [X]/5
  Why it works for YOU: [2 to 3 lines]
  How To Use: [step-by-step]
  Avoid If: [who should skip]

  --- SUGGESTED ROUTINE --- (only if 2+ products)
  - Step 1: [Product A] — [when/how]
  - Step 2: [Product B] — [when/how]

  --- PRO EXPERT ADVICE ---
  [One actionable tip]

=== PROBLEM TO PRODUCT MATCHING LOGIC ===
Use this logic when no product context is injected:

HAIR FALL / HAIR LOSS / THINNING:
  Primary: Silk Bond Treatment (strengthens bonds, reduces breakage)
  Secondary: PH Balancer Prewash Shampoo (unclogs follicles)

DANDRUFF / ITCHY SCALP / FLAKES:
  Primary: PH Balancer Prewash Shampoo (balances scalp pH, clears buildup)
  Secondary: Argan Shampoo (gentle cleanse)

DRY HAIR / BRITTLE / DEHYDRATED:
  Primary: Argan Hair Mask (deep conditioning)
  Secondary: Argan Oil Hair Serum (seals moisture)

FRIZZY HAIR / UNMANAGEABLE / ROUGH:
  Primary: Argan Oil Hair Serum (smoothens cuticle, anti-frizz)
  Secondary: Argan Hair Mask (hydration boost)

DULL HAIR / NO SHINE / LIFELESS:
  Primary: Argan Oil Hair Serum (instant shine and glossy finish)
  Secondary: Argan Shampoo (cleanses without stripping)

DAMAGED HAIR / CHEMICALLY TREATED / HEAT DAMAGED:
  Primary: Silk Bond Treatment (repairs broken bonds)
  Secondary: Argan Hair Mask (deep nourish)
  Tertiary: Argan Oil Hair Serum (protect from further damage)

SCALP BUILDUP / HARD WATER / POLLUTION DAMAGE:
  Primary: PH Balancer Prewash Shampoo (removes mineral deposits, restores pH)

OILY SCALP / GREASINESS:
  Primary: PH Balancer Prewash Shampoo (regulates sebum, deep cleanses)
  Secondary: Argan Shampoo (lightweight cleanse)

SLOW HAIR GROWTH / WEAK ROOTS:
  Primary: PH Balancer Prewash Shampoo (stimulates follicles)
  Secondary: Silk Bond Treatment (strengthens from root)

=== HARD RULES ===
- NEVER output JSON, XML, CSV, code blocks, or any raw technical data format under any circumstances.
  If someone asks for JSON or raw data, reply with one friendly sentence and let the product cards do the rest.
  Example: "I can not share raw data, but here are all our Atharva products — the cards below have everything you need."
- If user asks for ANY non-haircare product (sunscreen, moisturizer, makeup, soap, perfume, acne cream, etc.), respond warmly:
  "That's outside our range — we specialise in Atharva haircare products. If you have a hair or scalp concern, I'd love to help you find the right solution."

- NEVER show a haircare product when user asked for a non-haircare item.
- NEVER diagnose medical conditions or replace a doctor's advice.
- Always be warm, empathetic, and encouraging — never clinical or cold.
- NEVER use more than one question mark in a single response.
- NEVER use emoji or emoticons of any kind.
"""


# Build once at import time; rebuilt per-request via get_ai_response to keep date fresh
BEAUTICARE_SYSTEM_PROMPT = _build_system_prompt()


TITLE_SYSTEM_PROMPT = """You generate short chat titles (4-6 words max) for beauty consultations.
Given the first user message, return ONLY the title — no quotes, no punctuation at the end, no explanation.
Examples:
- "best moisturizer for oily skin" → Oily skin moisturizer picks
- "my hair is falling out" → Hair fall remedies
- "dark circles under eyes" → Dark circles treatment
- "dandruff and itchy scalp" → Dandruff scalp treatment
- "frizzy dry damaged hair" → Frizzy hair repair routine
"""

CATEGORY_SYSTEM_PROMPT = """You classify beauty chat messages into one of these categories:
skin, hair, makeup, wellness, general

Return ONLY the single category word, nothing else.

Rules:
- skin: moisturizers, serums, acne, dark spots, sunscreen, face wash, toner, anti-aging
- hair: shampoo, conditioner, hair fall, dandruff, hair growth, hair color, scalp, frizz, dry hair, damage
- makeup: foundation, lipstick, eyeshadow, mascara, blush, concealer, primer
- wellness: supplements, diet for skin, stress, sleep, gut health, vitamins
- general: anything else
"""

PROBLEM_ANALYSIS_PROMPT = """You are an expert trichologist AI. Analyze the user's hair/scalp problem and return a JSON object with:
{
  "problem_detected": true/false,
  "problem_type": "hair_fall|dandruff|dry_hair|frizzy|dull|damaged|scalp_buildup|oily_scalp|slow_growth|other|non_haircare",
  "severity": "mild|moderate|severe",
  "is_haircare_related": true/false,
  "is_non_haircare_product_request": true/false,
  "is_competitor_brand_request": true/false,
  "competitor_brand_name": "brand name or empty string",
  "product_codes_needed": ["prewash", "silkbond", "shampoo", "hairmask", "hairserum"],
  "brief_summary": "One line describing the detected problem"
}

Product codes:
- prewash = PH Balancer Prewash Shampoo
- silkbond = Silk Bond Treatment  
- shampoo = Argan Shampoo
- hairmask = Argan Hair Mask
- hairserum = Argan Oil Hair Serum

Set is_competitor_brand_request to true when the user asks about a product from another brand
(e.g. Dove, Pantene, Head & Shoulders, TRESemmé, L'Oréal, Sunsilk, Himalaya, WOW, Mamaearth, Biotique, Clinic Plus, etc.)

Return ONLY valid JSON. No explanation, no markdown, no code blocks.
"""

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    ("openrouter/owl-alpha", True),
    ("openai/gpt-oss-120b:free", True),
    ("nvidia/nemotron-3-super-120b-a12b:free", True),
    ("google/gemma-4-31b-it:free", True),
    ("google/gemma-4-26b-a4b-it:free", True),
    ("minimax/minimax-m2.5:free", True),
    ("nvidia/nemotron-3-nano-30b-a3b:free", True),
    ("openai/gpt-oss-20b:free", True),
    ("nvidia/nemotron-nano-9b-v2:free", True),
]

_rate_limited_until: dict[str, float] = {}
RATE_LIMIT_COOLDOWN = 90


def _is_rate_limited(model: str) -> bool:
    unblock_at = _rate_limited_until.get(model)
    if unblock_at is None:
        return False
    if time.time() >= unblock_at:
        del _rate_limited_until[model]
        return False
    return True


def _mark_rate_limited(model: str) -> None:
    _rate_limited_until[model] = time.time() + RATE_LIMIT_COOLDOWN
    print(f"  → Blacklisting {model} for {RATE_LIMIT_COOLDOWN}s")


def _build_payload(model: str, supports_temperature: bool, system: str, messages: list, max_tokens: int) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": max_tokens,
    }
    if supports_temperature:
        payload["temperature"] = 0.7
    return payload


def _extract_content(data: dict, model: str) -> str | None:
    if "error" in data:
        print(f"  → Error in 200 body from {model}: {data['error']}")
        return None
    choices = data.get("choices", [])
    if choices:
        choice = choices[0]
        msg = choice.get("message") or {}
        return msg.get("content") or choice.get("text")
    if "content" in data:
        return data["content"]
    print(f"  → Unknown response format from {model}:", data)
    return None


def _call_openrouter(system: str, messages: list, max_tokens: int = 2048) -> str:
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": getattr(settings, "SITE_URL", "http://localhost:8000"),
        "X-Title": "BeautiCare AI",
    }

    for model, supports_temperature in MODELS:
        if _is_rate_limited(model):
            print(f"Skipping {model} (rate-limited, cooling down)")
            continue

        try:
            payload = _build_payload(model, supports_temperature, system, messages, max_tokens)
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
            status = response.status_code
            print(f"Model: {model} | Status: {status}")

            if status == 200:
                data = response.json()
                content = _extract_content(data, model)
                if content:
                    return content
                continue

            if status == 429:
                print(f"  → Rate limited on {model}, cooling down…")
                _mark_rate_limited(model)
                continue

            if status in (400, 422):
                try:
                    err = response.json()
                except Exception:
                    err = response.text
                print(f"  → Bad request on {model} (will skip): {err}")
                continue

            if status == 404:
                print(f"  → Model {model} not found; skipping")
                continue

            if status in (500, 502, 503):
                print(f"  → Server error {status} on {model}, trying next…")
                continue

            print(f"  → Unexpected status {status} from {model}: {response.text[:200]}")
            continue

        except requests.exceptions.Timeout:
            print(f"  → {model} timed out, trying next…")
            continue
        except Exception as e:
            print(f"  → {model} exception: {e}, trying next…")
            continue

    raise Exception(
        "All models failed or are rate-limited. "
        "Check your OPENROUTER_API_KEY and model slugs at https://openrouter.ai/models"
    )


def get_ai_response(message_history: list) -> str:
    raw = _call_openrouter(
        system=_build_system_prompt(),
        messages=message_history,
        max_tokens=1200,
    )
    return _strip_emojis(raw)


def detect_category(message: str) -> str:
    try:
        category = _call_openrouter(
            system=CATEGORY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
            max_tokens=10,
        )
        category = category.strip().lower()
        valid = {"skin", "hair", "makeup", "wellness", "general"}
        return category if category in valid else "general"
    except Exception:
        return "general"


def generate_session_title(message: str) -> str:
    try:
        title = _call_openrouter(
            system=TITLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
            max_tokens=20,
        )
        return title.strip()
    except Exception:
        return "Beauty Consultation"


def analyze_hair_problem(message: str) -> dict:
    import json as _json

    DEFAULT = {
        "problem_detected": False,
        "problem_type": "other",
        "severity": "mild",
        "is_haircare_related": True,
        "is_non_haircare_product_request": False,
        "is_competitor_brand_request": False,
        "competitor_brand_name": "",
        "product_codes_needed": [],
        "brief_summary": "",
    }

    try:
        raw = _call_openrouter(
            system=PROBLEM_ANALYSIS_PROMPT,
            messages=[{"role": "user", "content": message}],
            max_tokens=200,
        )
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:])
            clean = clean.rstrip("`").strip()

        result = _json.loads(clean)
        for key, val in DEFAULT.items():
            result.setdefault(key, val)
        return result

    except Exception as e:
        print(f"  → analyze_hair_problem fallback due to: {e}")
        return DEFAULT