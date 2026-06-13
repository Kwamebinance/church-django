"""
One-time backfill: fill espees_amount on income records where it's null but an
ESPEES rate now exists for the church. Uses the CURRENT rate (the historical
rate at entry-time never existed, so current is the honest best estimate).

Run:  python manage.py backfill_espees          (dry run, shows what would change)
      python manage.py backfill_espees --apply  (actually writes)
"""
from django.core.management.base import BaseCommand

from finance.models import IncomeRecord
from finance.services import convert_to_espees


class Command(BaseCommand):
    help = "Backfill missing espees_amount on income records using current rates."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually write changes (default is a dry run).")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        qs = IncomeRecord.objects.select_related("church").filter(espees_amount__isnull=True)
        total = qs.count()
        filled = 0
        skipped = 0
        for r in qs:
            val = convert_to_espees(r.base_amount, r.church)
            if val is None:
                skipped += 1
                continue
            self.stdout.write(f"  {r.base_amount} {r.church.default_currency} -> {val} ESPEES"
                              + ("" if apply else "  (dry run)"))
            if apply:
                r.espees_amount = val
                r.save(update_fields=["espees_amount", "updated_at"])
            filled += 1
        self.stdout.write(self.style.SUCCESS(
            f"\n{total} record(s) missing ESPEES. "
            f"{filled} can be filled (rate exists), {skipped} skipped (no rate yet)."
            + ("" if apply else "\nThis was a DRY RUN. Re-run with --apply to write.")))
