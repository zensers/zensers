from PIL import Image
import sys

src = r"E:\market_report_systerm\Logo.png"
dst = r"E:\market_report_systerm\web\public\logo.png"

img = Image.open(src)
print(f"Original: {img.size[0]}x{img.size[1]} {img.mode}")

# Resize to max 64px keeping aspect ratio
img.thumbnail((64, 64), Image.LANCZOS)

# If has alpha, keep it; otherwise add white bg
if img.mode == 'RGBA':
    img.save(dst, 'PNG', optimize=True)
elif img.mode == 'P':
    img = img.convert('RGBA')
    img.save(dst, 'PNG', optimize=True)
else:
    img = img.convert('RGB')
    img.save(dst, 'PNG', optimize=True)

print(f"Resized to: {img.size[0]}x{img.size[1]}")
print(f"Output size: {__import__('os').path.getsize(dst)} bytes")
