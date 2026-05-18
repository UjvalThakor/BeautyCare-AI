import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta
from .models import Chat, Messages, Product
from .openrouter_service import (
    get_ai_response,
    generate_session_title,
    detect_category,
    analyze_hair_problem,
)

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
    t = text.lower()
    return any(w in t for w in image_words)


GREETINGS = {
    'hi', 'hello', 'hey', 'hii', 'helo', 'helloo',
    'sup', 'namaste', 'hola', 'good morning', 'good evening',
    'good afternoon', 'good night', 'howdy', 'what\'s up', 'whats up',
}

GENERAL_QUERIES = {
    'date', 'today', 'what day', 'what is today', 'todays date',
    "today's date", 'what time', 'how are you', 'who are you',
    'what can you do', 'what do you do', 'help',
}

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

SHOW_ALL_KEYWORDS = [
    'show all', 'all product', 'all products', 'show products',
    'show me all', 'list all', 'what products', 'available products',
    'what do you have', 'what do you sell', 'your products',
    'show everything', 'display all', 'all images', 'show images',
    'all photos', 'show photos', 'product images', 'give me images',
    'give me photos', 'images dikhao', 'photos dikhao', 'sab dikhao',
    'sabhi product', 'full list',
]


DATA_DUMP_KEYWORDS = [
    'json', 'xml', 'csv', 'api', 'raw data', 'database', 'dump',
    'export', 'give me data', 'product data', 'all data', 'fetch',
    'endpoint', 'schema', 'object', 'array', 'dict', 'payload',
]

PROBLEM_TYPE_TO_CODES = {
    'hair_fall':       ['silkbond', 'prewash'],
    'dandruff':        ['prewash', 'shampoo'],
    'dry_hair':        ['hairmask', 'hairserum'],
    'frizzy':          ['hairserum', 'hairmask'],
    'dull':            ['hairserum', 'shampoo'],
    'damaged':         ['silkbond', 'hairmask', 'hairserum'],
    'scalp_buildup':   ['prewash'],
    'oily_scalp':      ['prewash', 'shampoo'],
    'slow_growth':     ['prewash', 'silkbond'],
    'other':           [],
    'non_haircare':    [],
}


def _is_general_query(text: str) -> bool:
    t = text.lower().strip()
    if t in GREETINGS:
        return True
    return any(phrase in t for phrase in GENERAL_QUERIES)


def _is_competitor_query(text: str) -> bool:
    t = text.lower()
    return any(brand in t for brand in COMPETITOR_BRAND_KEYWORDS)


def _is_data_dump_request(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in DATA_DUMP_KEYWORDS)


def get_products_for_query(query: str, ai_analysis: dict | None = None):
    query_lower = query.lower().strip()

    if _is_general_query(query_lower):
        return Product.objects.none()

    if any(kw in query_lower for kw in NON_HAIRCARE_KEYWORDS):
        return Product.objects.none()

    if _is_competitor_query(query_lower):
        return Product.objects.none()
    if _is_data_dump_request(query_lower):
        return Product.objects.filter(in_stock=True)

    if any(kw in query_lower for kw in SHOW_ALL_KEYWORDS):
        return Product.objects.filter(in_stock=True)

    if ai_analysis and ai_analysis.get('problem_detected'):
        if ai_analysis.get('is_non_haircare_product_request'):
            return Product.objects.none()
        if ai_analysis.get('is_competitor_brand_request'):
            return Product.objects.none()

        problem_type = ai_analysis.get('problem_type', 'other')
        ai_product_codes = ai_analysis.get('product_codes_needed', [])

        codes = ai_product_codes or PROBLEM_TYPE_TO_CODES.get(problem_type, [])

        if codes:
            return _ordered_queryset_by_codes(codes)

    PRIORITY_MAP = [
        ('prewash',   ['prewash', 'pre wash', 'ph balancer', 'pre shampoo',
                       'hard water shampoo', 'scalp buildup', 'scalp clean',
                       'itchy scalp', 'dandruff', 'flakes', 'oily scalp',
                       'follicle', 'pollution damage']),
        ('silkbond',  ['silk bond', 'silkbond', 'hair fall', 'hairfall',
                       'hair loss', 'falling hair', 'chemically treated',
                       'damaged hair', 'repair hair', 'breakage', 'weak hair',
                       'hair thinning', 'thin hair']),
        ('hairmask',  ['hair mask', 'hairmask', 'deep condition', 'dry hair',
                       'brittle hair', 'strengthen hair', 'nourish hair',
                       'moisturise hair', 'dehydrated hair']),
        ('hairserum', ['hair serum', 'hairserum', 'argan serum', 'frizzy',
                       'frizz', 'heat protect', 'glossy hair', 'silky hair',
                       'dull hair', 'no shine', 'rough hair', 'smooth hair']),
        ('shampoo',   ['argan shampoo', 'argan hair wash', 'hair cleanse',
                       'gentle shampoo', 'sulphate free']),
    ]

    for problem_code, triggers in PRIORITY_MAP:
        if any(kw in query_lower for kw in triggers):
            return Product.objects.filter(problem=problem_code, in_stock=True)[:1]

    all_products = Product.objects.filter(in_stock=True)
    for p in all_products:
        if p.name.lower() in query_lower:
            return Product.objects.filter(id=p.id)

    keyword_map = {
        'prewash':   ['ph balancer', 'scalp', 'hard water', 'pollution', 'follicle'],
        'silkbond':  ['smooth', 'bond', 'cuticle', 'treatment', 'repair'],
        'shampoo':   ['shampoo', 'hair wash', 'wash hair', 'cleanse'],
        'hairmask':  ['mask', 'conditioning', 'moisture', 'nourish'],
        'hairserum': ['serum', 'shine', 'argan oil', 'hair oil', 'silky'],
    }
    best_problem = None
    best_score = 0
    for problem_code, keywords in keyword_map.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > best_score:
            best_score = score
            best_problem = problem_code

    if best_problem and best_score > 0:
        return Product.objects.filter(problem=best_problem, in_stock=True)[:1]

    return Product.objects.none()


def _product_from_ai_reply(ai_text: str):

    text_lower = ai_text.lower()
    if 'here is the' not in text_lower or 'image' not in text_lower:
        return None
    for p in Product.objects.filter(in_stock=True):
        if p.name.lower() in text_lower:
            return p
    return None


def _last_mentioned_product(session):
    all_products = list(Product.objects.filter(in_stock=True))
    recent_messages = session.messages.filter(role='assistant').order_by('-id')[:5]
    for msg in recent_messages:
        text_lower = msg.content.lower()
        for p in all_products:
            if p.name.lower() in text_lower:
                return p
    return None


def _ordered_queryset_by_codes(codes: list):
    if not codes:
        return Product.objects.none()

    products = []
    seen_ids = set()
    for code in codes:
        qs = Product.objects.filter(problem=code, in_stock=True)
        for p in qs:
            if p.id not in seen_ids:
                products.append(p)
                seen_ids.add(p.id)

    ids = [p.id for p in products]
    return _ordered_queryset(ids)


def _ordered_queryset(ids: list):
    if not ids:
        return Product.objects.none()
    from django.db.models import Case, When, IntegerField
    ordering = Case(
        *[When(pk=pk, then=pos) for pos, pk in enumerate(ids)],
        output_field=IntegerField(),
    )
    return Product.objects.filter(pk__in=ids, in_stock=True).annotate(
        _order=ordering
    ).order_by('_order')


def build_products_data(request, products, include_image=True):
    data = []
    for p in products:
        item = {
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
        }
        data.append(item)
    return data


def build_product_context(products, ai_analysis: dict | None = None) -> str:
    if not products:
        return ""

    problem_summary = ""
    if ai_analysis and ai_analysis.get('problem_detected'):
        problem_summary = (
            f"\nDetected problem : {ai_analysis.get('problem_type', 'unknown').replace('_', ' ').title()}"
            f"\nSeverity         : {ai_analysis.get('severity', 'mild').title()}"
            f"\nSummary          : {ai_analysis.get('brief_summary', '')}"
        )

    product_lines = []
    for p in products:
        product_lines.append(
            f"- {p.brand} {p.name} | Rs.{p.price} | {p.rating}/5 stars"
        )

    products_block = "\n".join(product_lines)

    return (
        f"\n\n[SYSTEM — PRODUCT DATA]\n"
        f"{problem_summary}\n"
        f"Matched products:\n{products_block}\n\n"
        f"RESPONSE INSTRUCTIONS — READ CAREFULLY:\n"
        f"The frontend will display full product cards (image, price, rating, how-to-use, avoid-if).\n"
        f"You must NOT repeat those details in your text reply.\n"
        f"Your text reply must be SHORT — 3 to 5 sentences maximum:\n"
        f"  1. One sentence identifying the user's problem.\n"
        f"  2. One or two sentences explaining why the matched product(s) help.\n"
        f"  3. One friendly closing line (e.g. 'The product cards below have all the details.').\n"
        f"Do NOT write long sections, bullet lists of causes, or lifestyle tips.\n"
        f"Do NOT restate price, rating, or how-to-use — the cards already show all of that.\n"
        f"Use ONLY the product names listed above — no others."
    )


def index(request):
    sessions = get_user_sessions(request)
    grouped = group_sessions_by_time(sessions)
    return render(request, 'index.html', {
        'grouped_sessions': grouped,
        'active_session':   None,
        'messages':         [],
    })


def chat_session(request, session_id):
    sessions = get_user_sessions(request)
    session  = get_object_or_404(Chat, id=session_id)
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

    grouped = group_sessions_by_time(sessions)
    return render(request, 'index.html', {
        'grouped_sessions':    grouped,
        'active_session':      session,
        'messages':            raw_messages,
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

    is_general = _is_general_query(user_text)
    is_competitor = _is_competitor_query(user_text)
    is_data_dump = _is_data_dump_request(user_text)
    wants_image = user_wants_image(user_text)

    EXPLICIT_PRODUCT_KEYWORDS = [
        'show me', 'show product', 'show image', 'show photo', 'show picture',
        'give me image', 'give me photo', 'give me the', 'image dikhao',
        'photo dikhao', 'product dikhao', 'all products', 'show all',
        'what products', 'your products', 'available products',
    ]
    user_lower = user_text.lower()
    wants_cards = wants_image or any(kw in user_lower for kw in EXPLICIT_PRODUCT_KEYWORDS)

    is_contextual_image_request = wants_cards and any(
        kw in user_lower
        for kw in ['that', 'it', 'this', 'the product', 'the image', 'the photo']
    )

    ai_analysis = None
    matching_products = Product.objects.none()
    product_context = ""

    if not is_general:
        if is_contextual_image_request:
            last_p = _last_mentioned_product(session)
            if last_p:
                matching_products = Product.objects.filter(pk=last_p.pk)
        else:
            try:
                ai_analysis = analyze_hair_problem(user_text)
                print(f"  → AI Analysis: {ai_analysis}")
            except Exception as e:
                print(f"  → AI analysis failed: {e}")
                ai_analysis = None

            matching_products = get_products_for_query(user_text, ai_analysis=ai_analysis)

        if matching_products.exists():
            product_context = build_product_context(list(matching_products), ai_analysis=ai_analysis)

    Messages.objects.create(session=session, role='user', content=user_text)

    history = [m.to_api_format() for m in session.messages.all()]

    if product_context:
        history[-1]['content'] = user_text + product_context

    elif is_data_dump:
        history[-1]['content'] = (
            user_text
            + "\n\n[SYSTEM NOTE: The user asked for JSON, raw data, or a technical format. "
            "You must NEVER output JSON, XML, code blocks, or any raw data. "
            "Instead, reply with one friendly sentence like: "
            "'I can not share raw data, but here are all our Atharva products — "
            "the cards below have everything you need.' "
            "Keep it to one sentence only.]"
        )

    elif is_competitor and not product_context:
        brand_name = ""
        if ai_analysis:
            brand_name = ai_analysis.get('competitor_brand_name', '')
        hint = brand_name if brand_name else "a competitor brand"
        history[-1]['content'] = (
            user_text
            + f"\n\n[SYSTEM NOTE: The user asked about {hint}, which we do not carry. "
            "Reply in 2 sentences ONLY: (1) we don't have that brand, we carry Atharva haircare products; "
            "(2) offer to suggest the best Atharva alternative for their concern. "
            "Do NOT ask multiple questions. Do NOT write long paragraphs. Keep it short and friendly.]"
        )

    elif ai_analysis and ai_analysis.get('is_non_haircare_product_request'):
        history[-1]['content'] = (
            user_text
            + "\n\n[SYSTEM NOTE: User is asking for a non-haircare product. "
            "Respond with the polite sorry message only.]"
        )

    try:
        ai_text = get_ai_response(history)
    except Exception as e:
        return JsonResponse({'error': f'AI service error: {str(e)}'}, status=503)

    ai_message = Messages.objects.create(
        session=session, role='assistant', content=ai_text
    )

    if is_first_message:
        try:
            title = generate_session_title(user_text)
            category = detect_category(user_text)
            session.title = title
            session.category = category
            session_title = session.title
            session.save(update_fields=['title', 'category', 'updated_at'])
        except Exception:
            session.save(update_fields=['updated_at'])
    else:
        session.save(update_fields=['updated_at'])

    products_data = []
    if wants_cards and matching_products.exists():
        for p in matching_products:
            products_data.append({
                'name':        p.name,
                'brand':       p.brand,
                'price':       str(p.price),
                'rating':      str(p.rating),
                'description': p.description,
                'how_to_use':  p.how_to_use,
                'image':       request.build_absolute_uri(p.image.url) if p.image else '',
            })
    if not products_data and wants_cards:
        resolved = _product_from_ai_reply(ai_text)
        if not resolved:
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

    analysis_meta = {}
    if ai_analysis:
        analysis_meta = {
            'problem_type':           ai_analysis.get('problem_type', ''),
            'severity':               ai_analysis.get('severity', ''),
            'summary':                ai_analysis.get('brief_summary', ''),
            'is_competitor_brand':    ai_analysis.get('is_competitor_brand_request', False),
            'competitor_brand_name':  ai_analysis.get('competitor_brand_name', ''),
        }

    return JsonResponse({
        'reply':            ai_text,
        'message_id':       str(ai_message.id),
        'session_id':       str(session.id),
        'session_title':    session_title,
        'session_category': session.category,
        'is_first_message': is_first_message,
        'products':         products_data,
        'ai_analysis':      analysis_meta,
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

    messages = []
    for m in session.messages.all():
        entry = {
            'role':     m.role,
            'content':  m.content,
            'products': m.products_json if m.role == 'assistant' else [],
        }
        messages.append(entry)

    return JsonResponse({'messages': messages})


def product_search_api(request):
    query = request.GET.get('q', '')
    products = get_products_for_query(query)
    show_img = user_wants_image(query)
    return JsonResponse({'products': build_products_data(request, list(products), include_image=show_img)})


def _get_preview(session):
    last_msg = session.messages.filter(role='assistant').last()
    if last_msg:
        text = last_msg.content
        for c in ['🔍', '🏆', '📦', '💰', '⭐', '🛒', '📝', '✅', '🎯', '⚠️',
                   '💡', '🌟', '✨', '💖', '🌸', '🧬', '🗓️', '━']:
            text = text.replace(c, '')
        text = text.replace('*', '').replace('#', '').replace('---', '').strip()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return lines[0][:80] if lines else 'BeautiCare response...'
    first_user = session.messages.filter(role='user').first()
    return first_user.content[:80] if first_user else 'New consultation'