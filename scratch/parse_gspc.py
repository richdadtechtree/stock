import re

with open("/Users/leehyungjun/.gemini/antigravity-ide/brain/bf294b8c-1150-44df-af3a-96a7ea60ef3a/.system_generated/steps/539/content.md", "r") as f:
    text = f.read()

# Look for standard Yahoo Finance price elements or numbers near GSPC
# Often like "regularMarketPrice":{"raw":5432.12,"fmt":"5,432.12"}
matches = re.findall(r'"regularMarketPrice":\s*\{\s*"raw":\s*([0-9.]+)', text)
print("Market Price Raw Matches:", matches)

matches_fmt = re.findall(r'"regularMarketPrice":\s*\{\s*"raw":\s*[0-9.]+,\s*"fmt":\s*"([^"]+)"', text)
print("Market Price Fmt Matches:", matches_fmt)

# Let's search for standard regex for any price around 5000-8000
# like 5,432.12
price_matches = re.findall(r'>([5678],[0-9]{3}\.[0-9]{2})<', text)
print("Regex HTML tag matches:", price_matches[:10])
