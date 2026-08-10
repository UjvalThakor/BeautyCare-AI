"""
FORCE FIX ALL PRODUCT IMAGES
==============================
Run from your project root:
    python fix_images.py
"""

import os
import sys
import django

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agent.settings')
django.setup()

from chatbot.models import Product
from django.conf import settings

print("🌸 Force Image Fixer")
print("=" * 40)

# ── List all products first ────────────────────────────────────
print("📦 Products in your database:")
for p in Product.objects.all():
    print(f"  ID:{p.id} | {p.name} | image='{p.image}'")
print()

# ── Your media/products/ folder path ──────────────────────────
PRODUCTS_DIR = os.path.join(settings.MEDIA_ROOT, 'products')
print(f"📁 Looking for images in: {PRODUCTS_DIR}")
print()

# ── List all image files found in media/products/ ─────────────
if not os.path.exists(PRODUCTS_DIR):
    print("❌ media/products/ folder does not exist!")
    print(f"   Create it at: {PRODUCTS_DIR}")
    print("   Then copy your 5 screenshots into it.")
    sys.exit(1)

files = os.listdir(PRODUCTS_DIR)
print(f"🖼️  Image files found in media/products/:")
for f in files:
    print(f"  {f}")
print()

if not files:
    print("❌ No image files found in media/products/!")
    print("   Copy your screenshots there first:")
    print(f"   {PRODUCTS_DIR}")
    sys.exit(1)

# ── Auto-match products to images ─────────────────────────────
IMAGE_MAP = {
    'prewash':   'Screenshot_2026-05-14_102256.png',
    'ph balanc': 'Screenshot_2026-05-14_102256.png',
    'silk bond': 'Screenshot_2026-05-14_102308.png',
    'smoothing treatment': 'Screenshot_2026-05-14_102308.png',
    'smoothing shampoo': 'Screenshot_2026-05-14_102321.png',
    'argan based shampoo': 'Screenshot_2026-05-14_102321.png',
    'hair mask': 'Screenshot_2026-05-14_102333.png',
    'hair serum': 'Screenshot_2026-05-14_102422.png',
    'kit guide': 'Screenshot_2026-05-14_103127.png',
}

updated = 0
for product in Product.objects.all():
    name_lower = product.name.lower()
    matched_file = None

    for keyword, filename in IMAGE_MAP.items():
        if keyword in name_lower:
            matched_file = filename
            break

    if not matched_file:
        # fallback: use first available image file
        matched_file = files[0]
        print(f"⚠️  No match for '{product.name}' — using first file: {matched_file}")

    full_path = os.path.join(PRODUCTS_DIR, matched_file)
    if os.path.exists(full_path):
        product.image = f"products/{matched_file}"
        product.save(update_fields=['image'])
        print(f"✅ {product.name}")
        print(f"   → products/{matched_file}")
        updated += 1
    else:
        print(f"❌ File not found on disk: {matched_file}")
        print(f"   Copy it to: {PRODUCTS_DIR}")

print()
print("=" * 40)
print(f"✅ Updated {updated} products")
print()
print("📦 Final status:")
for p in Product.objects.all():
    full = os.path.join(settings.MEDIA_ROOT, str(p.image)) if p.image else ''
    ok = "✅" if p.image and os.path.exists(full) else "❌"
    print(f"  {ok} {p.name} → {p.image}")

print()
print("🎉 Done! Now refresh your browser and test the chat.")
print("   All product images should appear now!")