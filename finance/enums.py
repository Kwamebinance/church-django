from django.db import models


# Canonical supported currencies for the whole system. ESPEES is the LoveWorld
# digital currency (not an ISO code), so it must be defined here explicitly —
# it will never come from an external source. Free-text currency fields are
# validated against this set in the UI.
SUPPORTED_CURRENCIES = [
    ("GHS", "GHS — Ghana Cedi"),
    ("NGN", "NGN — Nigerian Naira"),
    ("USD", "USD — US Dollar"),
    ("EUR", "EUR — Euro"),
    ("ESPEES", "ESPEES"),
]
SUPPORTED_CURRENCY_CODES = [c for c, _ in SUPPORTED_CURRENCIES]


class FinanceStatus(models.TextChoices):
    PENDING = "pending", "Pending approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    VOIDED = "voided", "Voided"


# unit types where income can be collected
class CollectedAtUnitType(models.TextChoices):
    CHURCH = "church", "Whole church"
    DEPARTMENT = "department", "Department"
    FELLOWSHIP = "fellowship", "Fellowship"
    CELL = "cell", "Cell"
