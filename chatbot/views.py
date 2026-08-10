import json
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta
from .models import Chat, Messages, Product
from .openrouter_service import (
    get_ai_response,
    get_ai_response_with_products,
    generate_session_title,
    detect_category,
    analyze_hair_problem,
)
from .prompt_builder import (
    ChatPromptContext,
    append_context_to_user_message,
    conversation_emoji_flags,
    pick_dynamic_greeting_fallback,
)

GREETINGS = {
    'hi', 'hello', 'hey', 'hii', 'helo', 'helloo', 'sup',
    'namaste', 'hola', 'good morning', 'good evening',
    'good afternoon', 'good night', 'howdy', "what's up", 'whats up',
}

GENERAL_EXACT = {
    'date', 'today', 'help', 'help me', 'need help',
    'how are you', 'who are you', 'what can you do', 'what do you do',
    'thanks', 'thank you', 'bye', 'goodbye', 'ok', 'okay',
}

GENERAL_PHRASES = [
    'what day', 'what is today', 'todays date', "today's date",
    'what time', "what's the date", 'whats the date',
]

NON_HAIRCARE_KEYWORDS = [
    'sunscreen', 'sunblock', 'spf', 'moisturizer', 'moisturiser',
    'face wash', 'facewash', 'toner', 'serum face', 'face serum',
    'acne', 'pimple', 'foundation', 'lipstick', 'mascara',
    'concealer', 'blush', 'eyeshadow', 'primer', 'makeup',
    'perfume', 'deodorant', 'body lotion', 'body wash',
    'face cream', 'eye cream', 'night cream', 'bb cream',
    'cc cream', 'kajal', 'eyeliner', 'nail polish', 'nail',
    'soap', 'toothpaste', 'supplement', 'vitamin', 'tablet',
]

COMPETITOR_BRAND_KEYWORDS = [
    'dove', 'pantene', 'head & shoulders', 'head and shoulders',
    'tresemme', 'tresemmé', 'loreal', "l'oreal", "l'oréal",
    'sunsilk', 'himalaya', 'wow', 'mamaearth', 'biotique',
    'clinic plus', 'clinic all clear', 'all clear', 'clear shampoo',
    'garnier', 'schwarzkopf', 'matrix', 'kérastase', 'kerastase',
    'moroccanoil', 'ogx', 'herbal essences', 'vatika', 'dabur',
    'parachute', 'indulekha', 'forest essentials', 'plum',
    'mCaffeine', 'mcaffeine', 'nykaa', 'beardo', 'man matters',
]

AFFIRM_WORDS = [
    'yes', 'yeah', 'yep', 'yaa', 'ya', 'sure', 'ok', 'okay', 'please',
    'go ahead', 'show them', 'show it', 'show me', 'dikhao', 'haan', 'han',
    'theek', 'thik', 'done', 'alright', 'absolutely', 'definitely',
    'interested', 'i am interested', 'tell me', 'show atharva',
]

PRICE_WORDS = [
    'price', 'cost', 'how much', 'rate', 'rupee', 'rupees',
    'rs.', ' rs ', 'expensive', 'cheap', 'kitna', 'kitne',
    'kya price', 'what price',
]

CONTEXT_REF_WORDS = [
    'this', 'that', 'it', 'the same', 'same one', 'above', 'mentioned',
    'this one', 'that one', 'the product', 'this product', 'that product',
]

PRODUCT_ALIASES = {
    'prewash':   ['prewash', 'pre wash', 'ph balancer', 'pre shampoo', 'pre-wash'],
    'silkbond':  ['silk bond', 'silkbond', 'silk bond treatment'],
    'shampoo':   ['argan shampoo', 'hair wash'],
    'hairmask':  ['hair mask', 'hairmask', 'argan hair mask', 'argan mask'],
    'hairserum': ['hair serum', 'hairserum', 'argan serum', 'argan oil hair serum', 'oil serum'],
}

ROUTINE_KEYWORDS = [
    'routine', 'regimen', 'hair care plan', 'haircare plan', 'care plan',
    'step by step', 'step-by-step', 'in what order', 'which order first',
    'how to use together', 'weekly plan', 'daily plan', 'make a routine',
    'create a routine', 'build a routine', 'personalized routine',
    'personalised routine', 'custom routine',
]

ROUTINE_SHORT_PHRASES = [
    'make it', 'make one', 'create it', 'build it', 'do it', 'yes make',
    'please make', 'sure make', 'make the routine', 'make my routine',
]

EXPLICIT_CARD_KEYWORDS = [
    'show me', 'show product', 'show products', 'show image', 'show photo', 'show picture',
    'give me image', 'give me photo', 'image dikhao', 'photo dikhao',
    'product dikhao', 'all product', 'all products', 'show all', 'what product', 'what products',
    'your product', 'your products', 'available product', 'available products',
    'list product', 'list products', 'product list',
    'tell product', 'tell products', 'display product', 'display products',
    'our product', 'our products', 'what products do you have',
    'show me product', 'show me products', 'show your product', 'show your products',
]

INFO_ONLY_KEYWORDS = [
    'price', 'cost', 'how much', 'rate', 'rating', 'stars',
    'what is', 'tell me', 'describe', 'what are', 'benefits',
    'kitna', 'kitne', 'kya price', 'what price',
]

def get_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def get_user_sessions(request):
    if request.user.is_authenticated:
        return Chat.objects.filter(user=request.user, is_active=True)
    return Chat.objects.filter(session_key=get_session_key(request), is_active=True)


def group_sessions_by_time(sessions):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)
    groups = {'Today': [], 'Yesterday': [], 'This week': [], 'Older': []}
    for s in sessions:
        if s.updated_at >= today_start:
            groups['Today'].append(s)
        elif s.updated_at >= yesterday_start:
            groups['Yesterday'].append(s)
        elif s.updated_at >= week_start:
            groups['This week'].append(s)
        else:
            groups['Older'].append(s)
    return {k: v for k, v in groups.items() if v}


def user_wants_image(text: str) -> bool:
    image_words = [
        'show me', 'show image', 'show photo', 'show picture',
        'image', 'photo', 'picture', 'pic', 'see it', 'look like',
        'how does it look', 'what does it look',
    ]
    return any(w in text.lower() for w in image_words)


def _is_general_query(text: str) -> bool:
    t = text.lower().strip().rstrip('?!.')
    return t in GREETINGS or t in GENERAL_EXACT or any(p in t for p in GENERAL_PHRASES)


def _is_pure_greeting(text: str) -> bool:
    return text.lower().strip().rstrip('?!.') in GREETINGS


def _is_competitor_query(text: str) -> bool:
    t = text.lower()
    return any(brand in t for brand in COMPETITOR_BRAND_KEYWORDS)


def _is_data_dump_request(text: str) -> bool:
    DATA_DUMP = ['json', 'xml', 'csv', 'api', 'raw data', 'database', 'dump',
                 'export', 'give me data', 'product data', 'all data', 'fetch',
                 'endpoint', 'schema', 'object', 'array', 'dict', 'payload']
    t = text.lower()
    return any(kw in t for kw in DATA_DUMP)


def _is_price_query(text: str) -> bool:
    return any(w in text.lower() for w in PRICE_WORDS)


def _is_contextual_followup(text: str) -> bool:
    t = text.lower().strip()
    if any(w in t for w in CONTEXT_REF_WORDS):
        return True
    if any(w in t for w in PRICE_WORDS) and len(t.split()) <= 12:
        return True
    return False


def _user_affirms(text: str) -> bool:
    t = text.lower().strip().rstrip('?!.')
    if len(t.split()) > 5:
        return False
    return any(a in t for a in AFFIRM_WORDS)


def _competitor_brand_from_text(text: str) -> str:
    t = text.lower()
    for brand in COMPETITOR_BRAND_KEYWORDS:
        if brand in t:
            return brand.title()
    return ''


def _product_by_code(code: str):
    return Product.objects.filter(problem=code, in_stock=True).first()


def _match_product_aliases(text: str):
    t = text.lower()
    for code, triggers in PRODUCT_ALIASES.items():
        if any(tr in t for tr in triggers):
            p = _product_by_code(code)
            if p:
                return p
    for p in Product.objects.filter(in_stock=True):
        if p.name.lower() in t or p.brand.lower() in t:
            return p
    return None


def _resolve_context_product(session, query: str = ''):
    if query:
        hit = _match_product_aliases(query)
        if hit:
            return hit
    all_products = list(Product.objects.filter(in_stock=True))
    for msg in session.messages.order_by('-id')[:14]:
        if msg.products_json and isinstance(msg.products_json, list):
            for item in msg.products_json:
                name = (item.get('name') or '').lower()
                for p in all_products:
                    if p.name.lower() in name or name in p.name.lower():
                        return p
        t = msg.content.lower()
        for p in all_products:
            if p.name.lower() in t:
                return p
        hit = _match_product_aliases(t)
        if hit:
            return hit
    return None


def _last_mentioned_product(session):
    all_products = list(Product.objects.filter(in_stock=True))
    for msg in session.messages.filter(role='assistant').order_by('-id')[:5]:
        if msg.products_json and isinstance(msg.products_json, list):
            for item in msg.products_json:
                name = (item.get('name') or '').lower()
                for p in all_products:
                    if p.name.lower() in name or name in p.name.lower():
                        return p
        t = msg.content.lower()
        for p in all_products:
            if p.name.lower() in t:
                return p
    return None


def _bot_invited_show_products(session) -> bool:
    last = session.messages.filter(role='assistant').order_by('-id').first()
    if not last:
        return False
    t = last.content.lower()
    return any(p in t for p in [
        'show me the product', 'show me the products', 'product cards',
        'pull up the full', 'cards below', 'show all', 'see the product',
    ])


def _bot_offered_atharva_alternative(session) -> bool:
    last = session.messages.filter(role='assistant').order_by('-id').first()
    if not last:
        return False
    t = last.content.lower()
    declined = any(x in t for x in [
        "don't carry", "do not carry", "we don't have", "we do not have",
        'not in our range', 'outside our range', 'we specialise', 'we specialize',
    ])
    offered = any(x in t for x in [
        'if you', "if you'd", 'interested', 'would you like',
        'can suggest', 'happy to suggest', 'atharva alternative', 'atharva product',
    ])
    return declined and offered


def _bot_offered_routine(session) -> bool:
    last = session.messages.filter(role='assistant').order_by('-id').first()
    if not last:
        return False
    t = last.content.lower()
    return any(x in t for x in [
        'personalized routine', 'personalised routine', 'hair routine',
        'make a routine', 'create a routine', 'build a routine',
        'routine for you', 'custom routine', 'step-by-step routine',
    ])


def _user_wants_routine(text: str, session) -> bool:
    t = text.lower().strip().rstrip('?!.')
    if any(kw in t for kw in ROUTINE_KEYWORDS):
        return True
    if any(p in t for p in ROUTINE_SHORT_PHRASES) and len(t.split()) <= 5:
        return _bot_offered_routine(session)
    return False


def _recent_user_concern(session) -> str:
    msg = session.messages.filter(role='user').order_by('-id').first()
    return msg.content[:200] if msg else ''


def local_hair_analysis(text: str) -> dict:
    t = text.lower()
    result = {
        "problem_detected": False,
        "problem_type": "other",
        "severity": "mild",
        "is_haircare_related": True,
        "is_non_haircare_product_request": False,
        "is_competitor_brand_request": _is_competitor_query(t),
        "competitor_brand_name": _competitor_brand_from_text(text),
        "product_codes_needed": [],
        "brief_summary": "",
    }
    if result["is_competitor_brand_request"]:
        return result
    if any(kw in t for kw in NON_HAIRCARE_KEYWORDS):
        result["is_non_haircare_product_request"] = True
        result["is_haircare_related"] = False
        return result
    keyword_map = [
        (['hair fall', 'hairfall', 'hair loss', 'thinning', 'breakage'], 'hair_fall', ['silkbond', 'prewash']),
        (['dandruff', 'flakes', 'itchy scalp'], 'dandruff', ['prewash', 'shampoo']),
        (['dry hair', 'brittle', 'dehydrated'], 'dry_hair', ['hairmask', 'hairserum']),
        (['frizz', 'frizzy', 'unmanageable'], 'frizzy', ['hairserum', 'hairmask']),
        (['dull', 'no shine', 'lifeless'], 'dull', ['hairserum', 'shampoo']),
        (['damaged', 'chemically treated', 'heat damage'], 'damaged', ['silkbond', 'hairmask', 'hairserum']),
        (['buildup', 'hard water', 'pollution'], 'scalp_buildup', ['prewash']),
        (['oily scalp', 'greasy'], 'oily_scalp', ['prewash', 'shampoo']),
        (['slow growth', 'weak roots'], 'slow_growth', ['prewash', 'silkbond']),
    ]
    for triggers, problem_type, codes in keyword_map:
        if any(tr in t for tr in triggers):
            result.update({
                "problem_detected": True,
                "problem_type": problem_type,
                "product_codes_needed": codes,
                "brief_summary": problem_type.replace('_', ' '),
            })
            return result
    if _match_product_aliases(text):
        result["problem_detected"] = True
        result["brief_summary"] = "product inquiry"
    return result


def _get_preview(session):
    last_msg = session.messages.filter(role='assistant').last()
    if last_msg:
        text = last_msg.content
        for c in ['🔍','🏆','📦','💰','⭐','🛒','📝','✅','🎯','⚠️','💡','🌟','✨','💖','🌸','🧬','🗓️','━']:
            text = text.replace(c, '')
        text = text.replace('*', '').replace('#', '').replace('---', '').strip()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return lines[0][:80] if lines else 'BeautiCare response...'
    first_user = session.messages.filter(role='user').first()
    return first_user.content[:80] if first_user else 'New consultation'


def build_products_data(request, products, include_image=True):
    data = []
    for p in products:
        data.append({
            'name':         p.name,
            'brand':        p.brand,
            'price':        str(p.price),
            'rating':       str(p.rating),
            'description':  p.description,
            'how_to_use':   p.how_to_use,
            'key_benefits': [b.strip() for b in p.key_benefits.split('\n') if b.strip()],
            'avoid_if':     p.avoid_if,
            'category':     p.category,
            'image': request.build_absolute_uri(p.image.url) if (p.image and include_image) else '',
        })
    return data

def index(request):
    sessions = get_user_sessions(request)
    return render(request, 'index.html', {
        'grouped_sessions': group_sessions_by_time(sessions),
        'active_session':   None,
        'messages':         [],
    })


def chat_session(request, session_id):
    sessions = get_user_sessions(request)
    session = get_object_or_404(Chat, id=session_id)
    if request.user.is_authenticated:
        if session.user != request.user:
            return redirect('index')
    else:
        if session.session_key != get_session_key(request):
            return redirect('index')

    raw_messages = session.messages.all()
    messages_with_products = [
        {
            'role':     m.role,
            'content':  m.content,
            'products': m.products_json if m.role == 'assistant' else [],
        }
        for m in raw_messages
    ]
    return render(request, 'index.html', {
        'grouped_sessions':       group_sessions_by_time(sessions),
        'active_session':         session,
        'messages':               raw_messages,
        'messages_with_products': json.dumps(messages_with_products),
    })

@require_http_methods(["POST"])
def new_session(request):
    if not request.session.session_key:
        request.session.create()
    session = Chat.objects.create(
        user=request.user if request.user.is_authenticated else None,
        session_key=request.session.session_key,
        title='New consultation',
        category='general',
    )
    return JsonResponse({'session_id': str(session.id), 'redirect_url': f'/chat/{session.id}/'})


@require_http_methods(["POST"])
def send_message(request, session_id):
    try:
        data = json.loads(request.body)
        user_text = data.get('message', '').strip()
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    if not user_text:
        return JsonResponse({'error': 'Message cannot be empty'}, status=400)

    session = get_object_or_404(Chat, id=session_id)
    if request.user.is_authenticated:
        if session.user != request.user:
            return JsonResponse({'error': 'Forbidden'}, status=403)
    else:
        if session.session_key != get_session_key(request):
            return JsonResponse({'error': 'Forbidden'}, status=403)

    is_first_message = not session.messages.exists()
    session_title = session.title
    user_lower = user_text.lower()
    is_general = _is_general_query(user_text)
    is_competitor = _is_competitor_query(user_text)
    is_data_dump = _is_data_dump_request(user_text)
    is_price_query = _is_price_query(user_text)
    is_contextual = _is_contextual_followup(user_text)
    wants_image = user_wants_image(user_text)
    is_routine = _user_wants_routine(user_text, session)
    is_affirm_atharva = _user_affirms(user_text) and _bot_offered_atharva_alternative(session)
    is_affirm_show = _user_affirms(user_text) and _bot_invited_show_products(session)
    context_product = _resolve_context_product(session, user_text)

    wants_cards = wants_image or any(kw in user_lower for kw in EXPLICIT_CARD_KEYWORDS)
    is_info_only = any(kw in user_lower for kw in INFO_ONLY_KEYWORDS)
    if is_info_only and not wants_image:
        wants_cards = False

    is_contextual_image = wants_cards and any(
        kw in user_lower for kw in ['that', 'it', 'this', 'the product', 'the image', 'the photo']
    )

    ai_analysis = local_hair_analysis(user_text)
    is_non_haircare = bool(ai_analysis.get('is_non_haircare_product_request'))

    emoji_flags = conversation_emoji_flags(session, user_text)
    prompt_ctx = ChatPromptContext.from_request(
        user_message=user_text,
        is_general=is_general,
        is_pure_greeting=_is_pure_greeting(user_text),
        is_routine=is_routine,
        is_competitor=is_competitor,
        is_affirm_atharva=is_affirm_atharva,
        is_affirm_show=is_affirm_show,
        is_data_dump=is_data_dump,
        is_non_haircare=is_non_haircare,
        products=[],
        ai_analysis=ai_analysis,
        price_focus=is_price_query,
        contextual=is_contextual,
        competitor_brand=_competitor_brand_from_text(user_text) or ai_analysis.get('competitor_brand_name', ''),
        concern_snippet=_recent_user_concern(session),
        **emoji_flags,
    )
    SECURITY_KEYWORDS = [
        'system prompt', 'your prompt', 'instructions',
        'sql', 'select', 'database', 'db ', 'table',
        'connection string', 'credentials', 'password',
        'api key', 'secret', 'config', 'settings',
        'source code', 'your code', 'how are you built',
    ]

    is_security_attack = any(
        kw in user_lower for kw in SECURITY_KEYWORDS
    )

    if is_security_attack:
        ai_text = "I can only help with Atharva haircare. What hair concern can I help you with?"
        Messages.objects.create(
            session=session,
            role='assistant',
            content=ai_text
        )
        return JsonResponse({
            'reply': ai_text,
            'products': [],
            'message_id': str(uuid.uuid4()),
            'session_id': str(session.id),
            'session_title': session_title,
            'session_category': session.category,
            'is_first_message': is_first_message,
            'ai_analysis': {},
        })
    Messages.objects.create(session=session, role='user', content=user_text)
    history = [m.to_api_format() for m in session.messages.all()]
    for msg in history:
        if msg.get('content') is None:
            msg['content'] = ''
    if is_general and len(history) > 8:
        history = history[-8:]
    history[-1]['content'] = append_context_to_user_message(user_text, prompt_ctx)

    tool_products = []
    try:
        if is_general or is_competitor or is_data_dump or is_non_haircare:
            print(f"  -> Simple mode: {prompt_ctx.mode}")
            if is_competitor and not is_affirm_atharva:
                brand = _competitor_brand_from_text(user_text) or "that brand"
                brand = brand.title()
                ai_text = (
                    f"No, we don't carry {brand} — we only have Atharva products. "
                    f"Would you like me to suggest a similar Atharva product?"
                )
            else:
                ai_text = get_ai_response(history, prompt_ctx=prompt_ctx)
        else:
            print(f"  -> Tool call mode: {prompt_ctx.mode}")
            ai_text, tool_products = get_ai_response_with_products(
                history, prompt_ctx=prompt_ctx
            )
            print(f"  -> Tool products: {len(tool_products)}")

    except Exception as e:
        print(f"  -> AI provider unavailable ({e}) — using smart local recommendation fallback")
        if is_general:
            ai_text = pick_dynamic_greeting_fallback(
                user_text,
                greeting_repeat_count=emoji_flags.get("greeting_repeat_count", 0),
                last_assistant_reply=emoji_flags.get("last_assistant_reply", ""),
            )
        else:
            codes = ai_analysis.get('product_codes_needed', [])
            found_prods = []
            if codes:
                found_prods = list(Product.objects.filter(code__in=codes, in_stock=True))
            if not found_prods:
                found_prods = list(Product.objects.filter(in_stock=True)[:2])

            prob_name = ai_analysis.get('brief_summary', '').replace('_', ' ')
            if prob_name and prob_name != 'other':
                ai_text = f"Here are our recommended Atharva products tailored for your {prob_name} concern:"
            else:
                ai_text = "Here are our top recommended Atharva products to help care for your hair:"
            tool_products = found_prods

    ai_message = Messages.objects.create(
        session=session, role='assistant', content=ai_text
    )
    if is_first_message:
        session.title = generate_session_title(user_text)
        session.category = detect_category(user_text)
        session_title = session.title
        session.save(update_fields=['title', 'category', 'updated_at'])
    else:
        session.save(update_fields=['updated_at'])

    import re
    clean_text = re.sub(r'[^\w\s]', ' ', user_text).strip().lower()
    is_catalog_request = any(
        kw in clean_text for kw in [
            'your product', 'your products', 'all product', 'all products',
            'what product', 'what products', 'show product', 'show products',
            'available product', 'available products', 'list product', 'list products',
            'product list', 'catalog', 'our product', 'our products',
            'show me your product', 'show me your products', 'what products do you have',
            'show me product', 'show me products', 'show your product', 'show your products',
        ]
    ) or clean_text in ['product', 'products', 'item', 'items']

    if tool_products:
        final_products = tool_products
        wants_cards = True
    elif is_catalog_request:
        final_products = list(Product.objects.filter(in_stock=True))
        wants_cards = True
    elif is_affirm_show:
        resolved = _resolve_context_product(session, user_text)
        if resolved:
            final_products = [resolved]
        else:
            last_msg = session.messages.filter(role='assistant').order_by('-id').first()
            mentioned = []
            if last_msg:
                all_prods = list(Product.objects.filter(in_stock=True))
                for p in all_prods:
                    if p.name.lower() in last_msg.content.lower():
                        mentioned.append(p)
            final_products = mentioned if mentioned else list(Product.objects.filter(in_stock=True)[:2])
        wants_cards = True
    elif is_affirm_atharva:
        final_products = list(Product.objects.filter(in_stock=True)[:2])
        wants_cards = True
    elif is_contextual and context_product and (wants_image or is_contextual_image):
        final_products = [context_product]
        wants_cards = True
    elif is_contextual_image:
        p = _resolve_context_product(session, user_text) or _last_mentioned_product(session)
        final_products = [p] if p else list(Product.objects.filter(in_stock=True)[:2])
        wants_cards = True
    elif wants_cards:
        p = _resolve_context_product(session, user_text) or _last_mentioned_product(session)
        final_products = [p] if p else list(Product.objects.filter(in_stock=True))
    else:
        final_products = []

    show_cards = (wants_cards and not is_competitor) or (is_competitor and is_affirm_atharva)

    products_data = []
    if show_cards and final_products:
        for p in final_products:
            products_data.append({
                'name':        p.name,
                'brand':       p.brand,
                'price':       str(p.price),
                'rating':      str(p.rating),
                'description': p.description,
                'how_to_use':  p.how_to_use,
                'image':       request.build_absolute_uri(p.image.url) if p.image else '',
            })
    if not products_data and show_cards:
        resolved = _last_mentioned_product(session)
        if resolved and resolved.image:
            products_data.append({
                'name':        resolved.name,
                'brand':       resolved.brand,
                'price':       str(resolved.price),
                'rating':      str(resolved.rating),
                'description': resolved.description,
                'how_to_use':  resolved.how_to_use,
                'image':       request.build_absolute_uri(resolved.image.url),
            })

    if products_data:
        ai_message.products_json = products_data
        ai_message.save(update_fields=['products_json'])

    return JsonResponse({
        'reply':            ai_text,
        'message_id':       str(ai_message.id),
        'session_id':       str(session.id),
        'session_title':    session_title,
        'session_category': session.category,
        'is_first_message': is_first_message,
        'products':         products_data,
        'ai_analysis': {
            'problem_type':          ai_analysis.get('problem_type', ''),
            'severity':              ai_analysis.get('severity', ''),
            'summary':               ai_analysis.get('brief_summary', ''),
            'is_competitor_brand':   ai_analysis.get('is_competitor_brand_request', False),
            'competitor_brand_name': ai_analysis.get('competitor_brand_name', ''),
        },
    })


@require_http_methods(["POST"])
def delete_session(request, session_id):
    session = get_object_or_404(Chat, id=session_id)
    if request.user.is_authenticated:
        if session.user != request.user:
            return JsonResponse({'error': 'Forbidden'}, status=403)
    else:
        if session.session_key != get_session_key(request):
            return JsonResponse({'error': 'Forbidden'}, status=403)
    session.is_active = False
    session.save(update_fields=['is_active'])
    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def rename_session(request, session_id):
    try:
        data = json.loads(request.body)
        new_title = data.get('title', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    if not new_title:
        return JsonResponse({'error': 'Title cannot be empty'}, status=400)
    session = get_object_or_404(Chat, id=session_id)
    if request.user.is_authenticated:
        if session.user != request.user:
            return JsonResponse({'error': 'Forbidden'}, status=403)
    else:
        if session.session_key != get_session_key(request):
            return JsonResponse({'error': 'Forbidden'}, status=403)
    session.title = new_title[:200]
    session.save(update_fields=['title'])
    return JsonResponse({'success': True, 'title': session.title})


def session_list_api(request):
    sessions = get_user_sessions(request)
    grouped = group_sessions_by_time(sessions)
    result = {}
    for group_name, group_sessions in grouped.items():
        result[group_name] = [
            {
                'id':         str(s.id),
                'title':      s.title,
                'category':   s.category,
                'preview':    _get_preview(s),
                'updated_at': s.updated_at.isoformat(),
            }
            for s in group_sessions
        ]
    return JsonResponse({'groups': result})


def session_messages_api(request, session_id):
    session = get_object_or_404(Chat, id=session_id)
    if request.user.is_authenticated:
        if session.user != request.user:
            return JsonResponse({'error': 'Forbidden'}, status=403)
    else:
        if session.session_key != get_session_key(request):
            return JsonResponse({'error': 'Forbidden'}, status=403)
    messages = [
        {
            'role':     m.role,
            'content':  m.content,
            'products': m.products_json if m.role == 'assistant' else [],
        }
        for m in session.messages.all()
    ]
    return JsonResponse({'messages': messages})


def product_search_api(request):
    query = request.GET.get('q', '')
    products = list(Product.objects.filter(in_stock=True)) if query else []
    show_img = user_wants_image(query)
    return JsonResponse({'products': build_products_data(request, products, include_image=show_img)})

def api_schema_json(request):
    from .api_schema import SCHEMA
    return JsonResponse(SCHEMA, json_dumps_params={'indent': 2})


def api_docs(request):
    html = """<!DOCTYPE html>
<html>
<head>
    <title>BeautiCare AI — API Docs</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body { margin: 0; background: #1a1a2e; }
        .swagger-ui .topbar { background: #16213e; }
        .swagger-ui .topbar .download-url-wrapper { display: none; }
        #swagger-ui { max-width: 1200px; margin: 0 auto; }
    </style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
window.onload = function() {
    SwaggerUIBundle({
        url: "/api/schema.json",
        dom_id: '#swagger-ui',
        deepLinking: true,
        tryItOutEnabled: true,
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
        layout: "BaseLayout",
        requestInterceptor: (req) => {
            const csrf = document.cookie.match(/csrftoken=([^;]+)/);
            if (csrf) req.headers['X-CSRFToken'] = csrf[1];
            return req;
        }
    });
}
</script>
</body>
</html>"""
    return HttpResponse(html)