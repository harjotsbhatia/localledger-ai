"""Deterministic rule-based categorization. No model involvement, so totals are reproducible."""

from __future__ import annotations

CATEGORIES: tuple[str, ...] = (
    "Restaurants",
    "Groceries",
    "Housing",
    "Utilities",
    "Subscriptions",
    "Transport",
    "Shopping",
    "Health",
    "Entertainment",
    "Travel",
    "Fees",
    "Income",
    "Transfer",
    "Other",
)

# Ordered: first match wins. Keywords are matched against the upper-cased description.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Transfer", ("TRANSFER", "PAYMENT THANK YOU", "CREDIT CARD PAYMENT", "CARD PAYMENT",
                  "ZELLE", "VENMO", "TO SAVINGS", "FROM CHECKING", "AUTOPAY PAYMENT")),
    ("Income", ("PAYROLL", "DIRECT DEP", "SALARY", "INTEREST PAID", "TAX REFUND", "DIVIDEND")),
    ("Housing", (" RENT ", "MORTGAGE", "PROPERTY MGMT", "HOA ")),
    ("Utilities", ("ELECTRIC", "WATER DEPT", "GAS CO", "COMCAST", "XFINITY", "VERIZON", "AT&T",
                   "T-MOBILE", "INTERNET", "UTILITY")),
    ("Subscriptions", ("NETFLIX", "SPOTIFY", "HULU", "DISNEY+", "ICLOUD", "APPLE.COM/BILL",
                       "YOUTUBE PREMIUM", "NYTIMES", "GYM", "FITNESS", "ADOBE", "DROPBOX")),
    ("Groceries", ("WHOLE FOODS", "TRADER JOE", "SAFEWAY", "KROGER", "ALDI", "COSTCO",
                   "GROCERY", "MARKET BASKET", "SPROUTS")),
    ("Restaurants", ("RESTAURANT", "CAFE", "COFFEE", "STARBUCKS", "CHIPOTLE", "MCDONALD",
                     "PIZZA", "TAQUERIA", "SUSHI", "DOORDASH", "UBER EATS", "GRUBHUB", "BISTRO",
                     "DINER", "BURGER", "THAI", "RAMEN", "BAKERY", "BAR & GRILL", "SWEETGREEN")),
    ("Transport", ("UBER", "LYFT", "SHELL", "CHEVRON", "EXXON", "GAS STATION", "PARKING",
                   "METRO", "TRANSIT", "TOLL")),
    ("Travel", ("AIRLINES", "AIRBNB", "HOTEL", "MARRIOTT", "DELTA AIR", "EXPEDIA")),
    ("Health", ("PHARMACY", "CVS", "WALGREENS", "DENTAL", "MEDICAL", "CLINIC", "DR ")),
    ("Entertainment", ("CINEMA", "AMC ", "TICKETMASTER", "STEAM", "PLAYSTATION", "BOOKSTORE",
                       "CONCERT", "MUSEUM")),
    ("Shopping", ("AMAZON", "AMZN", "TARGET", "WALMART", "BEST BUY", "IKEA", "APPLE STORE",
                  "NIKE", "ETSY", "HOME DEPOT")),
    ("Fees", (" FEE", "OVERDRAFT", "INTEREST CHARGE")),
)


def categorize(description: str, amount_minor: int) -> str:
    text = f" {description.upper()} "
    for category, keywords in _RULES:
        if any(keyword in text for keyword in keywords):
            if category == "Income" and amount_minor < 0:
                continue
            return category
    # Unrecognized deposits are treated as (other) income; unrecognized charges as Other.
    return "Income" if amount_minor > 0 else "Other"


def resolve_category(name: str) -> str | None:
    """Case-insensitive lookup with a few natural-language aliases."""
    wanted = name.strip().lower()
    aliases = {
        "restaurant": "Restaurants", "dining": "Restaurants", "dining out": "Restaurants",
        "eating out": "Restaurants", "food": "Restaurants", "grocery": "Groceries",
        "rent": "Housing", "subscription": "Subscriptions", "transportation": "Transport",
        "transfers": "Transfer", "fee": "Fees",
    }
    for category in CATEGORIES:
        if category.lower() == wanted:
            return category
    return aliases.get(wanted)
