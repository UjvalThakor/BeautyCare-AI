import os
import sys
import django

sys.path.append('c:\\Users\\admin\\Downloads\\BeautyCare-AI-main\\BeautyCare-AI-main\\agent')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agent.settings')
django.setup()

from chatbot.models import Product

products_data = [
    {
        "name": "PH Balancer Prewash Shampoo",
        "brand": "Atharva",
        "category": "hair",
        "problem": "prewash",
        "price": "Rs. 549",
        "rating": 4.6,
        "description": "Restores scalp pH balance, unclogs hair follicles, and purifies mineral buildup before washing.",
        "how_to_use": "Apply to dry scalp 30 minutes before shampooing. Massage gently in circular motions, then rinse thoroughly during your bath.",
        "key_benefits": "Balances scalp pH\nRemoves mineral deposits\nPrepares hair for deep cleansing",
        "avoid_if": "Avoid on open scalp wounds or active skin infections.",
        "image": "products/Screenshot_2026-05-14_102256.png",
        "in_stock": True,
    },
    {
        "name": "Silk Bond Treatment",
        "brand": "Atharva",
        "category": "hair",
        "problem": "silkbond",
        "price": "Rs. 899",
        "rating": 4.8,
        "description": "Advanced bond-repair treatment that restores broken keratin bonds and reinforces fragile hair roots against hair fall.",
        "how_to_use": "Apply generously to damp hair after cleansing. Leave on for 15-20 minutes, then rinse completely with cool water.",
        "key_benefits": "Repairs broken bonds\nReduces hair fall & breakage\nStrengthens root elasticity",
        "avoid_if": "Do not over-use; apply once or twice weekly.",
        "image": "products/Screenshot_2026-05-14_102308.png",
        "in_stock": True,
    },
    {
        "name": "Argan Shampoo",
        "brand": "Atharva",
        "category": "hair",
        "problem": "shampoo",
        "price": "Rs. 499",
        "rating": 4.5,
        "description": "Gentle, sulfate-free shampoo infused with pure Moroccan Argan oil for soft, clean, and hydrated hair.",
        "how_to_use": "Massage into wet scalp and hair until rich lather forms. Rinse thoroughly with water.",
        "key_benefits": "Sulfate-free cleansing\nInfused with organic Argan Oil\nMaintains natural hair oils",
        "avoid_if": "",
        "image": "products/Screenshot_2026-05-14_102321.png",
        "in_stock": True,
    },
    {
        "name": "Argan Hair Mask",
        "brand": "Atharva",
        "category": "hair",
        "problem": "hairmask",
        "price": "Rs. 699",
        "rating": 4.7,
        "description": "Deep conditioning mask that quenches dry, frizzy, and chemically damaged hair with long-lasting moisture.",
        "how_to_use": "After shampooing, apply from mid-lengths to hair tips. Leave for 5-10 minutes, then rinse out completely.",
        "key_benefits": "Deep hydration\nSmoothens frizzy strands\nAdds silky soft shine",
        "avoid_if": "Do not apply directly to greasy roots.",
        "image": "products/Screenshot_2026-05-14_102333.png",
        "in_stock": True,
    },
    {
        "name": "Argan Oil Hair Serum",
        "brand": "Atharva",
        "category": "hair",
        "problem": "hairserum",
        "price": "Rs. 599",
        "rating": 4.9,
        "description": "Lightweight elixir that tames stubborn frizz, protects against heat damage, and imparts intense mirror shine.",
        "how_to_use": "Rub 2-3 drops between palms and distribute evenly through towel-dried or dry hair ends.",
        "key_benefits": "Instant anti-frizz action\nHeat protection up to 230°C\nMirror-like shine",
        "avoid_if": "",
        "image": "products/Screenshot_2026-05-14_102422.png",
        "in_stock": True,
    },
]

created = 0
updated = 0
for p_data in products_data:
    obj, is_created = Product.objects.update_or_create(
        problem=p_data["problem"],
        defaults=p_data
    )
    if is_created:
        created += 1
    else:
        updated += 1

print(f"[OK] Seeding Complete! Created {created} products, updated {updated} products.")
print(f"[Products] Total products now in database: {Product.objects.count()}")
