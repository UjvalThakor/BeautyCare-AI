import sys
import re
import json
import time
import threading
import requests
from django.conf import settings
from .prompt_builder import ChatMode, ChatPromptContext, build_system_prompt, build_analysis_prompt

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

_http = requests.Session()


def _clean_response(text: str) -> str:
    text = re.sub(r'^\s*<assistant>\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*</assistant>\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*<user>\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*</user>\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<function.*?</function>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'/function=\w+>.*?</function>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\{\"products\".*?\}\}', '', text, flags=re.DOTALL)
    text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\[TOOL_CALL\].*?\[/TOOL_CALL\]', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    return text.strip()

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RATE_LIMIT_COOLDOWN = 10
_gemini_rate_limited_until: float = 0.0


OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"

_FALLBACK_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "moonshotai/kimi-k2.6:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
]
_model_cache: list = []
_model_cache_lock = threading.Lock()
_model_cache_time: float = 0.0
_MODEL_CACHE_TTL = 3600

GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]

def _groq_simple_call(system, messages, max_tokens, timeout, temperature) -> str:
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        raise Exception("GROQ_API_KEY not set")

    groq_messages = [{"role": "system", "content": system}]
    for m in messages:
        groq_messages.append({
            "role": m["role"],
            "content": m["content"]
        })

    for model in GROQ_MODELS:
        try:
            payload = {
                "model": model,
                "messages": groq_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            r = _http.post(
                GROQ_BASE,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            print(f"  [groq] {model} → {r.status_code}")
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"]
                if text.strip():
                    print(f"  [groq] success ({model})")
                    return _clean_response(text.strip())
            elif r.status_code == 429:
                print(f"  [groq] {model} rate limited — trying next")
                continue
            else:
                print(f"  [groq] {model} error: {r.status_code}")
        except Exception as e:
            print(f"  [groq] {model} exception: {e}")

    raise Exception("All Groq models failed")

def _groq_call_with_tools(system, messages, max_tokens, timeout, temperature) -> tuple[str, list]:
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        raise Exception("GROQ_API_KEY not set")

    groq_messages = [{"role": "system", "content": system}]
    for m in messages:
        groq_messages.append({
            "role": m["role"],
            "content": m["content"]
        })

    all_products = []

    for model in GROQ_MODELS:
        try:
            # ROUND 1 — with tools
            payload = {
                "model": model,
                "messages": groq_messages,
                "tools": OPENROUTER_TOOLS,
                "tool_choice": "auto",
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            r = _http.post(
                GROQ_BASE,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            print(f"  [groq] {model} → {r.status_code}")

            if r.status_code == 400:
                print(f"  [groq] {model} no tool support — trying next")
                continue

            if r.status_code == 429:
                print(f"  [groq] {model} rate limited — trying next")
                continue

            if r.status_code != 200:
                print(f"  [groq] {model} error: {r.status_code}")
                continue

            response_data = r.json()
            tool_calls = _or_extract_tool_calls(response_data)

            # No tool calls — direct reply
            if not tool_calls:
                text = _or_extract_text(response_data)
                if text.strip():
                    print(f"  [groq] direct reply ({model})")
                    return _clean_response(text.strip()), []
                continue

            print(f"  [groq] tool calls: {[tc['name'] for tc in tool_calls]}")
            groq_messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        },
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                result_text, products = execute_tool(tc["name"], tc["args"])
                all_products.extend(products)
                groq_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_text,
                })
            final_payload = {
                "model": model,
                "messages": groq_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            r2 = _http.post(
                GROQ_BASE,
                json=final_payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            if r2.status_code == 200:
                text = _or_extract_text(r2.json())
                if text.strip():
                    print(f"  [groq] tool-loop success ({model})")
                    return _clean_response(text.strip()), _dedupe_products(all_products)

            print(f"  [groq] {model} round 2 failed: {r2.status_code}")

        except Exception as e:
            print(f"  [groq] {model} exception: {e}")

    raise Exception("All Groq models failed (tool calling)")

def _fetch_free_models_from_api() -> list:
    try:
        api_key = getattr(settings, "OPENROUTER_API_KEY", "")
        r = _http.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"  [openrouter] model list fetch failed: {r.status_code}")
            return []

        data = r.json().get("data", [])
        free_models = []
        for m in data:
            mid = m.get("id", "")
            if not mid.endswith(":free"):
                continue
            supported = m.get("supported_parameters") or []
            if "tools" in supported or "functions" in supported:
                free_models.append(mid)

        print(f"  [openrouter] fetched {len(free_models)} free tool-capable models live")
        return free_models

    except Exception as e:
        print(f"  [openrouter] model list fetch exception: {e}")
        return []


def get_openrouter_models() -> list:
    global _model_cache, _model_cache_time

    with _model_cache_lock:
        if _model_cache and (time.time() - _model_cache_time) < _MODEL_CACHE_TTL:
            return _model_cache

        models = _fetch_free_models_from_api()
        if models:
            _model_cache = models
            _model_cache_time = time.time()
            return _model_cache

        print("  [openrouter] using fallback model list")
        return _FALLBACK_MODELS

GEMINI_TOOLS = [
    {
        "function_declarations": [
            {
                "name": "get_products_by_problem",
                "description": (
                    "Fetch Atharva products that match a hair or scalp problem. "
                    "Call this when user describes hair fall, dandruff, dry hair, "
                    "frizzy hair, dull hair, damaged hair, oily scalp, or slow growth."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "problem_type": {
                            "type": "string",
                            "enum": [
                                "hair_fall", "dandruff", "dry_hair", "frizzy",
                                "dull", "damaged", "scalp_buildup",
                                "oily_scalp", "slow_growth", "general",
                            ],
                            "description": "Detected hair or scalp problem type.",
                        }
                    },
                    "required": ["problem_type"],
                },
            },
            {
                "name": "get_product_by_name",
                "description": (
                    "Fetch a specific Atharva product by its code. "
                    "Call when user asks about a specific product by name, "
                    "asks for price, rating, how to use, or wants to see its image."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_code": {
                            "type": "string",
                            "enum": ["prewash", "silkbond", "shampoo", "hairmask", "hairserum"],
                            "description": (
                                "prewash=PH Balancer Prewash Shampoo | "
                                "silkbond=Silk Bond Treatment | "
                                "shampoo=Argan Shampoo | "
                                "hairmask=Argan Hair Mask | "
                                "hairserum=Argan Oil Hair Serum"
                            ),
                        }
                    },
                    "required": ["product_code"],
                },
            },
            {
                "name": "get_all_products",
                "description": (
                    "Fetch all available Atharva products. "
                    "Call when user asks to see all products, "
                    "what products are available, or wants to browse everything."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]
    }
]

OPENROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_products_by_problem",
            "description": (
                "Fetch Atharva products that match a hair or scalp problem. "
                "Call this when user describes hair fall, dandruff, dry hair, "
                "frizzy hair, dull hair, damaged hair, oily scalp, or slow growth."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_type": {
                        "type": "string",
                        "enum": [
                            "hair_fall", "dandruff", "dry_hair", "frizzy",
                            "dull", "damaged", "scalp_buildup",
                            "oily_scalp", "slow_growth", "general",
                        ],
                        "description": "Detected hair or scalp problem type.",
                    }
                },
                "required": ["problem_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_by_name",
            "description": (
                "Fetch a specific Atharva product by its code. "
                "Call when user asks about a specific product by name, price, rating, or image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_code": {
                        "type": "string",
                        "enum": ["prewash", "silkbond", "shampoo", "hairmask", "hairserum"],
                        "description": (
                            "prewash=PH Balancer Prewash Shampoo | "
                            "silkbond=Silk Bond Treatment | "
                            "shampoo=Argan Shampoo | "
                            "hairmask=Argan Hair Mask | "
                            "hairserum=Argan Oil Hair Serum"
                        ),
                    }
                },
                "required": ["product_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_products",
            "description": (
                "Fetch all available Atharva products. "
                "Call when user asks to see all products or wants to browse everything."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
PROBLEM_TO_CODES = {
    "hair_fall":     ["silkbond", "prewash"],
    "dandruff":      ["prewash", "shampoo"],
    "dry_hair":      ["hairmask", "hairserum"],
    "frizzy":        ["hairserum", "hairmask"],
    "dull":          ["hairserum", "shampoo"],
    "damaged":       ["silkbond", "hairmask", "hairserum"],
    "scalp_buildup": ["prewash"],
    "oily_scalp":    ["prewash", "shampoo"],
    "slow_growth":   ["prewash", "silkbond"],
    "general":       ["prewash", "shampoo", "hairmask", "hairserum"],
}

def _serialize_products(products) -> list:
    result = []
    for p in products:
        result.append({
            "name":         p.name,
            "brand":        p.brand,
            "price":        str(p.price),
            "rating":       str(p.rating),
            "description":  p.description,
            "how_to_use":   p.how_to_use,
            "key_benefits": [b.strip() for b in p.key_benefits.split("\n") if b.strip()],
            "avoid_if":     p.avoid_if,
            "problem_code": p.problem,
        })
    return result


def execute_tool(tool_name: str, tool_args: dict) -> tuple[str, list]:
    from .models import Product

    try:
        if tool_name == "get_all_products":
            products = list(Product.objects.filter(in_stock=True))
            print(f"  [tool] get_all_products → {len(products)} products")
            return (
                json.dumps({"products": _serialize_products(products), "count": len(products)}),
                products,
            )

        elif tool_name == "get_product_by_name":
            code = tool_args.get("product_code", "")
            products = list(Product.objects.filter(problem=code, in_stock=True))
            print(f"  [tool] get_product_by_name({code}) → {len(products)} products")
            if not products:
                return json.dumps({"error": f"No product found for code: {code}"}), []
            return json.dumps({"products": _serialize_products(products)}), products

        elif tool_name == "get_products_by_problem":
            problem = tool_args.get("problem_type", "general")
            codes = PROBLEM_TO_CODES.get(problem, [])
            seen, products = set(), []
            for code in codes:
                for p in Product.objects.filter(problem=code, in_stock=True):
                    if p.id not in seen:
                        products.append(p)
                        seen.add(p.id)
            if not products:
                products = list(Product.objects.filter(in_stock=True)[:2])
            print(f"  [tool] get_products_by_problem({problem}) → {len(products)} products")
            return (
                json.dumps({"products": _serialize_products(products), "problem": problem}),
                products,
            )

        return json.dumps({"error": f"Unknown tool: {tool_name}"}), []

    except Exception as e:
        print(f"  [tool] ERROR in {tool_name}: {e}")
        return json.dumps({"error": str(e)}), []

def _gemini_build_payload(system, messages, max_tokens, temperature, use_tools=True):
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": 0.95,
        },
    }
    if use_tools:
        payload["tools"] = GEMINI_TOOLS
        payload["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}
    return payload


def _gemini_raw_call(system, messages, max_tokens, timeout, temperature, use_tools=True) -> dict:
    global _gemini_rate_limited_until

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise Exception("GEMINI_API_KEY not set")

    wait = _gemini_rate_limited_until - time.time()
    if wait > 0:
        raise Exception(f"Gemini cooling down — {wait:.0f}s remaining")

    payload = _gemini_build_payload(system, messages, max_tokens, temperature, use_tools)

    for model in GEMINI_MODELS:
        url = f"{GEMINI_BASE.format(model=model)}?key={api_key}"
        try:
            r = _http.post(url, json=payload, timeout=timeout)
            print(f"  [gemini] {model} → {r.status_code}")
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                print(f"  [gemini] Rate limited — cooling {RATE_LIMIT_COOLDOWN}s")
                _gemini_rate_limited_until = time.time() + RATE_LIMIT_COOLDOWN
                raise Exception("Gemini rate limited")
            print(f"  [gemini] {model} error {r.status_code}: {r.text[:120]}")
        except requests.exceptions.Timeout:
            print(f"  [gemini] {model} timed out")
        except Exception as e:
            if "rate limited" in str(e) or "cooling" in str(e):
                raise
            print(f"  [gemini] {model} exception: {e}")

    raise Exception("All Gemini models failed")


def _gemini_extract_text(data: dict) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        for part in parts:
            if "text" in part and part["text"].strip():
                return part["text"].strip()
    except (KeyError, IndexError):
        pass
    return ""


def _gemini_extract_tool_calls(data: dict) -> list:
    tool_calls = []
    try:
        parts = data["candidates"][0]["content"]["parts"]
        for part in parts:
            if "functionCall" in part:
                tool_calls.append({
                    "name": part["functionCall"]["name"],
                    "args": part["functionCall"].get("args", {}),
                })
    except (KeyError, IndexError):
        pass
    return tool_calls


def _gemini_call_with_tools(system, messages, max_tokens, timeout, temperature) -> tuple[str, list]:
    all_products = []

    data = _gemini_raw_call(system, messages, max_tokens, timeout, temperature, use_tools=True)
    tool_calls = _gemini_extract_tool_calls(data)

    if not tool_calls:
        text = _gemini_extract_text(data)
        if text:
            print("  [gemini] direct reply (no tools needed)")
            return text, []
        raise Exception("Gemini returned empty response")

    print(f"  [gemini] tool calls: {[t['name'] for t in tool_calls]}")

    assistant_parts = [
        {"functionCall": {"name": tc["name"], "args": tc["args"]}}
        for tc in tool_calls
    ]
    tool_result_parts = []
    for tc in tool_calls:
        result_text, products = execute_tool(tc["name"], tc["args"])
        all_products.extend(products)
        tool_result_parts.append({
            "functionResponse": {
                "name": tc["name"],
                "response": {"result": result_text},
            }
        })

    full_contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        full_contents.append({"role": role, "parts": [{"text": m["content"]}]})
    full_contents.append({"role": "model", "parts": assistant_parts})
    full_contents.append({"role": "user", "parts": tool_result_parts})

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    final_payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": full_contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": 0.95,
        },
    }

    for model in GEMINI_MODELS:
        url = f"{GEMINI_BASE.format(model=model)}?key={api_key}"
        try:
            r = _http.post(url, json=final_payload, timeout=timeout)
            if r.status_code == 200:
                text = _gemini_extract_text(r.json())
                if text:
                    print(f"  [gemini] tool-loop success ({model})")
                    return text, _dedupe_products(all_products)
        except Exception as e:
            print(f"  [gemini] final call {model} error: {e}")

    raise Exception("Gemini final call failed after tool execution")

def _or_headers() -> dict:
    api_key = getattr(settings, "OPENROUTER_API_KEY", "")
    if not api_key:
        raise Exception("OPENROUTER_API_KEY not set")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://beauticare.ai",
        "X-Title": "BeautiCare AI",
    }


def _or_build_messages(system: str, messages: list) -> list:
    result = [{"role": "system", "content": system}]
    for m in messages:
        result.append({"role": m["role"], "content": m["content"]})
    return result


def _or_extract_text(data: dict) -> str:
    try:
        text = data["choices"][0]["message"]["content"] or ""
        return _clean_response(text)
    except (KeyError, IndexError):
        return ""

def _or_extract_tool_calls(data: dict) -> list:
    calls = []
    try:
        tool_calls = data["choices"][0]["message"].get("tool_calls") or []
        for tc in tool_calls:
            calls.append({
                "id":   tc["id"],
                "name": tc["function"]["name"],
                "args": json.loads(tc["function"]["arguments"] or "{}"),
            })
    except (KeyError, IndexError, json.JSONDecodeError):
        pass
    return calls


def _or_simple_call(system, messages, max_tokens, timeout, temperature) -> str:
    or_messages = _or_build_messages(system, messages)
    headers = _or_headers()

    for model in get_openrouter_models():
        payload = {
            "model": model,
            "messages": or_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            r = _http.post(OPENROUTER_BASE, json=payload, headers=headers, timeout=timeout)
            print(f"  [openrouter] {model} → {r.status_code}")
            if r.status_code == 200:
                text = _or_extract_text(r.json())
                if text.strip():
                    print(f"  [openrouter] simple reply success ({model})")
                    return text.strip()
            elif r.status_code == 429:
                print(f"  [openrouter] {model} rate limited — trying next")
                continue
            elif r.status_code == 404:
                print(f"  [openrouter] {model} not found — removing from cache")
                with _model_cache_lock:
                    if model in _model_cache:
                        _model_cache.remove(model)
            else:
                print(f"  [openrouter] {model} error: {r.status_code} {r.text[:100]}")
        except requests.exceptions.Timeout:
            print(f"  [openrouter] {model} timed out")
        except Exception as e:
            print(f"  [openrouter] {model} exception: {e}")

    raise Exception("All OpenRouter models failed (simple)")


def _or_call_with_tools(system, messages, max_tokens, timeout, temperature) -> tuple[str, list]:
    or_messages = _or_build_messages(system, messages)
    headers = _or_headers()
    all_products = []

    for model in get_openrouter_models():
        try:
            payload = {
                "model": model,
                "messages": or_messages,
                "tools": OPENROUTER_TOOLS,
                "tool_choice": "auto",
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            r = _http.post(OPENROUTER_BASE, json=payload, headers=headers, timeout=timeout)
            print(f"  [openrouter] {model} → {r.status_code}")

            if r.status_code == 404:
                print(f"  [openrouter] {model} not found — removing from cache")
                with _model_cache_lock:
                    if model in _model_cache:
                        _model_cache.remove(model)
                continue

            if r.status_code != 200:
                print(f"  [openrouter] {model} failed: {r.text[:100]}")
                continue

            response_data = r.json()
            tool_calls = _or_extract_tool_calls(response_data)

            if not tool_calls:
                text = _or_extract_text(response_data)
                if text.strip():
                    print(f"  [openrouter] direct reply ({model})")
                    return text.strip(), []
                continue

            print(f"  [openrouter] tool calls: {[tc['name'] for tc in tool_calls]}")

            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        },
                    }
                    for tc in tool_calls
                ],
            }
            or_messages.append(assistant_msg)

            for tc in tool_calls:
                result_text, products = execute_tool(tc["name"], tc["args"])
                all_products.extend(products)
                or_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_text,
                })

            final_payload = {
                "model": model,
                "messages": or_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            r2 = _http.post(OPENROUTER_BASE, json=final_payload, headers=headers, timeout=timeout)
            if r2.status_code == 200:
                text = _or_extract_text(r2.json())
                if text.strip():
                    print(f"  [openrouter] tool-loop success ({model})")
                    return text.strip(), _dedupe_products(all_products)

            print(f"  [openrouter] {model} final call failed: {r2.status_code}")

        except requests.exceptions.Timeout:
            print(f"  [openrouter] {model} timed out")
        except Exception as e:
            print(f"  [openrouter] {model} exception: {e}")

    raise Exception("All OpenRouter models failed (tool calling)")

def _dedupe_products(products: list) -> list:
    seen, unique = set(), []
    for p in products:
        if p.id not in seen:
            unique.append(p)
            seen.add(p.id)
    return unique


def _get_timeout(ctx: ChatPromptContext) -> int:
    if ctx.mode in {ChatMode.CASUAL, ChatMode.COMPETITOR, ChatMode.DATA_DUMP, ChatMode.NON_HAIRCARE}:
        return 20
    if ctx.mode in {ChatMode.ROUTINE, ChatMode.PRODUCT_MATCH}:
        return 35
    return 30

# REPLACE WITH:
def _offline_ai_response(message_history: list, prompt_ctx: "ChatPromptContext | None" = None) -> str:
    import random
    from .models import Product

    user_msg = ""
    for msg in reversed(message_history):
        if msg.get('role') == 'user':
            user_msg = msg.get('content', '')
            break

    msg_lower = user_msg.lower()
    mode = getattr(prompt_ctx, 'mode', None)
    comp_brand = getattr(prompt_ctx, 'competitor_brand', '')
    all_prods = list(Product.objects.filter(in_stock=True))

    # 1. Price queries
    if any(w in msg_lower for w in ['price', 'cost', 'how much', 'rate', 'rupee', 'rs', 'expensive', 'cheap', 'kitna']):
        matched = [p for p in all_prods if p.name.lower() in msg_lower or p.problem in msg_lower]
        if not matched:
            for msg in reversed(message_history):
                content = msg.get('content', '').lower()
                for p in all_prods:
                    if p.name.lower() in content:
                        matched.append(p)
                if matched:
                    break
        if matched:
            p = matched[0]
            return f"The {p.brand} {p.name} is priced at Rs. {p.price}. It has a rating of {p.rating}/5 stars. Description: {p.description}"
        return "Our Atharva haircare pricing: PH Balancer Prewash Shampoo is Rs. 549, Silk Bond Treatment is Rs. 899, Argan Shampoo is Rs. 499, Argan Hair Mask is Rs. 699, and Argan Hair Serum is Rs. 599."

    # 2. How to use / Usage queries
    if any(w in msg_lower for w in ['how to use', 'apply', 'direction', 'how do i use', 'how to apply', 'usage', 'step']):
        matched = [p for p in all_prods if p.name.lower() in msg_lower]
        if not matched:
            for msg in reversed(message_history):
                content = msg.get('content', '').lower()
                for p in all_prods:
                    if p.name.lower() in content:
                        matched.append(p)
                if matched:
                    break
        if matched:
            p = matched[0]
            return f"How to use {p.name}:\n\n{p.how_to_use}"
        return ("Atharva 4-Step Haircare Application Guide:\n"
                "1. Pre-Wash Scalp Balancer: Apply 30 mins before washing to unclog follicles and balance pH.\n"
                "2. Argan Shampoo: Lather softly on scalp & roots, rinse with lukewarm water.\n"
                "3. Argan Hair Mask: Apply from mid-lengths to ends, leave for 5-10 mins, then rinse.\n"
                "4. Argan Hair Serum: Work 2-3 drops through damp ends for all-day shine and heat protection.")

    # 3. Catalog / All Products
    clean_msg = re.sub(r'[^\w\s]', ' ', user_msg).strip().lower()
    if any(k in clean_msg for k in ['your product', 'your products', 'all product', 'all products', 'what product', 'what products', 'show product', 'show products', 'product list', 'catalog', 'our product', 'our products', 'show me product', 'show me products', 'show your product', 'show your products', 'available product', 'available products']) or clean_msg in ['product', 'products']:
        return "Here is our full collection of Atharva premium botanical haircare solutions, designed to target hair fall, scalp flakes, damage repair, and frizzy strands:"

    # 4. Greetings / Intro
    msg_words = set(clean_msg.split())
    greeting_words = {'hi', 'hello', 'hey', 'hii', 'helo', 'namaste', 'sup', 'hola'}
    greeting_phrases = ['good morning', 'good evening', 'good afternoon', 'who are you', 'what can you do']

    if (any(w in msg_words for w in greeting_words) or any(p in clean_msg for p in greeting_phrases)) and len(msg_words) <= 4:
        greetings = [
            "Hello! 🌸 I am your Atharva BeautyCare AI Hair Advisor. What hair or scalp concern can I help you target today?",
            "Hey there! Welcome to Atharva BeautyCare AI. How can I help you achieve healthy, lustrous hair today?",
            "Hi! Ready to customize your haircare routine? Tell me about your hair type or any current concerns!",
        ]
        return random.choice(greetings)

    # 5. Competitor brand comparison
    if (mode and mode.startswith('competitor')) or comp_brand:
        brand = (comp_brand or 'that brand').title()
        return f"We focus exclusively on Atharva's high-performance, botanical, sulfate-free haircare rather than {brand}. Would you like me to suggest an Atharva formula tailored to your specific hair goals?"

    # 6. Specific Hair Concerns
    if any(k in clean_msg for k in ['hair fall', 'hairfall', 'hair loss', 'thinning', 'breakage']):
        return "For hair fall and weak roots, we recommend nourishing your scalp and reinforcing strands with Atharva Silk Bond Treatment and Pre-Wash Scalp Balancer. They restore scalp moisture balance, strengthen keratin bonds, and reduce hair breakage."
    elif any(k in clean_msg for k in ['dandruff', 'flake', 'itchy', 'scalp']):
        return "To clear scalp flakes and relieve itchiness, our Atharva Pre-Wash Scalp Balancer paired with Argan Shampoo purifies excess sebum while maintaining your natural moisture balance."
    elif any(k in clean_msg for k in ['dry', 'frizz', 'frizzy', 'damaged', 'brittle']):
        return "For dry or frizzy locks, intense hydration is essential! Atharva Argan Hair Mask and Hair Serum deeply nourish dehydrated strands, seal moisture into the cuticle, and eliminate frizz for soft, glossy hair."
    elif any(k in clean_msg for k in ['routine', 'regimen', 'plan', 'step']) or mode == ChatMode.ROUTINE:
        return ("Here is your recommended Atharva Haircare Regimen:\n\n"
                "1. **Pre-Wash**: Apply Pre-Wash Scalp Balancer 30 mins before washing to cleanse scalp buildup.\n"
                "2. **Wash**: Cleanse gently with Atharva Argan Shampoo.\n"
                "3. **Treat & Hydrate**: Use Atharva Argan Hair Mask twice weekly for deep conditioning.\n"
                "4. **Seal & Protect**: Apply 2-3 drops of Atharva Argan Hair Serum on damp ends to tame frizz and lock in shine.")

    # 7. Unrecognized / Gibberish or General Clarification
    return "I didn't quite catch that! Please let me know your specific hair concern (such as hair fall, dandruff, dryness, frizz, or routine recommendations) so I can assist you."


def _offline_ai_response_with_products(message_history: list, prompt_ctx: "ChatPromptContext | None" = None) -> tuple[str, list]:
    try:
        from .models import Product
        user_msg = ""
        for msg in reversed(message_history):
            if msg.get('role') == 'user':
                user_msg = msg.get('content', '')
                break

        msg_lower = user_msg.lower()
        clean_msg = re.sub(r'[^\w\s]', ' ', user_msg).strip().lower()
        all_prods = list(Product.objects.filter(in_stock=True))
        matched_products = []

        is_catalog = any(k in clean_msg for k in ['your product', 'your products', 'all product', 'all products', 'what product', 'what products', 'show product', 'show products', 'product list', 'catalog', 'our product', 'our products', 'show me product', 'show me products', 'show your product', 'show your products', 'available product', 'available products']) or clean_msg in ['product', 'products']

        if is_catalog:
            matched_products = all_prods
        elif any(k in msg_lower for k in ['hair fall', 'fall', 'loss', 'thinning', 'breakage']):
            matched_products = list(Product.objects.filter(problem__in=['silkbond', 'prewash'], in_stock=True))
        elif any(k in msg_lower for k in ['dandruff', 'flake', 'scalp', 'itchy']):
            matched_products = list(Product.objects.filter(problem__in=['prewash', 'shampoo'], in_stock=True))
        elif any(k in msg_lower for k in ['dry', 'frizz', 'frizzy', 'damaged', 'brittle']):
            matched_products = list(Product.objects.filter(problem__in=['hairmask', 'hairserum'], in_stock=True))
        elif 'shampoo' in msg_lower or 'wash' in msg_lower:
            matched_products = list(Product.objects.filter(problem='shampoo', in_stock=True))
        elif 'mask' in msg_lower:
            matched_products = list(Product.objects.filter(problem='hairmask', in_stock=True))
        elif 'serum' in msg_lower:
            matched_products = list(Product.objects.filter(problem='hairserum', in_stock=True))
        elif any(w in msg_lower for w in ['price', 'cost', 'how much', 'rate', 'how to use', 'apply', 'usage', 'routine', 'regimen', 'step']):
            # Contextual product check for price/usage/routine follow-ups
            for msg in reversed(message_history[:-1]):
                content = msg.get('content', '').lower()
                for p in all_prods:
                    if p.name.lower() in content:
                        matched_products.append(p)
                if matched_products:
                    break
            if not matched_products:
                matched_products = all_prods[:2]

        text = _offline_ai_response(message_history, prompt_ctx)
        return text, matched_products
    except Exception as err:
        print(f"  [offline-ai] product lookup fallback error: {err}")
        text = _offline_ai_response(message_history, prompt_ctx)
        return text, []


def get_ai_response(
    message_history: list,
    prompt_ctx: "ChatPromptContext | None" = None,
) -> str:
    ctx = prompt_ctx or ChatPromptContext()
    system = build_system_prompt(ctx)
    max_tokens = max(ctx.max_tokens, 150 if ctx.mode == ChatMode.CASUAL else ctx.max_tokens)
    timeout = _get_timeout(ctx)

    # 1. Try Gemini
    try:
        data = _gemini_raw_call(
            system=system,
            messages=message_history,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=ctx.temperature,
            use_tools=False,
        )
        text = _gemini_extract_text(data).strip()
        if text:
            print("  [provider] Gemini simple ✓")
            return text
    except Exception as e:
        print(f"  [provider] Gemini failed: {e}")

    # 2. Try OpenRouter
    try:
        print("  [provider] Using OpenRouter simple fallback")
        return _or_simple_call(
            system=system,
            messages=message_history,
            max_tokens=max_tokens,
            timeout=timeout + 10,
            temperature=ctx.temperature,
        )
    except Exception as e:
        print(f"  [provider] OpenRouter failed: {e}")

    # 3. Try Groq
    try:
        print("  [provider] Using Groq fallback")
        return _groq_simple_call(
            system=system,
            messages=message_history,
            max_tokens=max_tokens,
            timeout=timeout + 10,
            temperature=ctx.temperature,
        )
    except Exception as e:
        print(f"  [provider] Groq failed: {e} — engaging built-in Atharva AI Engine")

    # 4. Ultimate Guaranteed Fallback: Built-in Atharva AI Engine
    return _offline_ai_response(message_history, prompt_ctx)


def get_ai_response_with_products(
    message_history: list,
    prompt_ctx: "ChatPromptContext | None" = None,
) -> tuple[str, list]:
    ctx = prompt_ctx or ChatPromptContext()
    system = build_system_prompt(ctx)
    max_tokens = ctx.max_tokens
    timeout = _get_timeout(ctx)

    # 1. Try Gemini
    try:
        text, products = _gemini_call_with_tools(
            system=system,
            messages=message_history,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=ctx.temperature,
        )
        print("  [provider] Gemini tools ✓")
        return text, products
    except Exception as e:
        print(f"  [provider] Gemini tools failed: {e} — falling back to OpenRouter")

    # 2. Try OpenRouter
    try:
        print("  [provider] Using OpenRouter tool-calling fallback")
        return _or_call_with_tools(
            system=system,
            messages=message_history,
            max_tokens=max_tokens,
            timeout=timeout + 10,
            temperature=ctx.temperature,
        )
    except Exception as e:
        print(f"  [provider] OpenRouter tools failed: {e} — falling back to Groq")

    # 3. Try Groq
    try:
        print("  [provider] Using Groq tool-calling fallback")
        return _groq_call_with_tools(
            system=system,
            messages=message_history,
            max_tokens=max_tokens,
            timeout=timeout + 10,
            temperature=ctx.temperature,
        )
    except Exception as e:
        print(f"  [provider] Groq tools failed: {e} — engaging built-in Atharva AI Engine")

    # 4. Ultimate Guaranteed Fallback: Built-in Atharva AI Engine with Products
    return _offline_ai_response_with_products(message_history, prompt_ctx)


def detect_category(message: str) -> str:
    t = message.lower()
    if any(w in t for w in ["hair", "shampoo", "dandruff", "scalp", "fall", "frizz", "mask", "serum"]):
        return "hair"
    if any(w in t for w in ["skin", "acne", "moistur", "sunscreen", "face"]):
        return "skin"
    if any(w in t for w in ["makeup", "lipstick", "foundation", "mascara"]):
        return "makeup"
    if any(w in t for w in ["vitamin", "supplement", "diet", "wellness"]):
        return "wellness"
    return "general"


def generate_session_title(message: str) -> str:
    words = message.strip().split()
    if not words:
        return "New consultation"
    title = " ".join(words[:6])
    if len(title) > 40:
        title = title[:40].rsplit(" ", 1)[0]
    return title.title() if title else "New consultation"


def analyze_hair_problem(message: str) -> dict:
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
        data = _gemini_raw_call(
            system=build_analysis_prompt(message),
            messages=[{"role": "user", "content": message}],
            max_tokens=200,
            timeout=20,
            temperature=0.1,
            use_tools=False,
        )
        raw = _gemini_extract_text(data)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:]).rstrip("`").strip()
        result = json.loads(clean)
        for key, val in DEFAULT.items():
            result.setdefault(key, val)
        return result
    except Exception as e:
        print(f"  [analyze] fallback: {e}")
        return DEFAULT
def pick_dynamic_greeting_fallback(
    user_message: str,
    *,
    greeting_repeat_count: int = 0,
    last_assistant_reply: str = "",
) -> str:
    import random

    t = user_message.lower().strip().rstrip("?!.")
    if "good morning" in t:
        variants = [
            "Good morning! I'm BeautiCare AI — your Atharva haircare advisor. What hair concern can I help with?",
            "Morning! Tell me your hair concern and I'll guide you to the right Atharva care.",
        ]
    elif "good evening" in t or "good afternoon" in t:
        variants = ["Good evening! I'm BeautiCare AI — here for all things Atharva haircare. What can I help with?"]
    elif "good night" in t:
        variants = ["Good night! If you have a quick hair question before you rest, I'm here."]
    else:
        variants = [
            "Hi! I'm BeautiCare AI — your Atharva hair advisor. What hair or scalp concern can I help with?",
            "Hello! Tell me what's going on with your hair and I'll point you to the right Atharva care.",
            "Hey! I'm here for hair fall, dandruff, frizz, dryness, and more. What's on your mind?",
        ]
    pool = [v for v in variants if v[:40] not in (last_assistant_reply or "")]
    if not pool:
        pool = variants
    idx = (greeting_repeat_count + random.randint(0, len(pool) - 1)) % len(pool)
    return pool[idx]


def _call_openrouter(system, messages, max_tokens=512, **kwargs):
    return _or_simple_call(
        system=system,
        messages=messages,
        max_tokens=max_tokens,
        timeout=kwargs.get("timeout", 30),
        temperature=kwargs.get("temperature", 0.75),
    )