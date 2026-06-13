from finance.models import CurrencySnapshot, IncomeRecord
from finance.services import convert_to_espees
print("--- RATES ---")
for s in CurrencySnapshot.objects.all():
    print("base=%s quote=%s rate=%s church=%s" % (s.base_currency, s.quote_currency, s.rate, s.church_id))
print("--- RECORDS ---")
for r in IncomeRecord.objects.select_related("church")[:5]:
    print("%s %s | frozen=%s | live=%s | base_ccy=%s" % (r.base_amount, r.currency, r.espees_amount, convert_to_espees(r.base_amount, r.church), r.church.default_currency))
