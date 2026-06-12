"""
Demo data seeder. Builds a realistic full-zone structure plus generated members,
families, and leadership assignments for testing.

Usage:
    python manage.py seed_demo                 # default scale (~400 members)
    python manage.py seed_demo --scale full    # ~1500 members
    python manage.py seed_demo --scale small    # ~120 members
    python manage.py seed_demo --wipe          # clear demo data first, then seed
    python manage.py seed_demo --wipe-only      # just clear demo data

Idempotent: all demo objects are tagged via a known zone short_code; re-running
won't duplicate (it detects the existing demo zone and skips structure). Use
--wipe to rebuild from scratch.

NOTE: this is DEMO/TEST data, clearly named. Not for production.

Grows over time: as new domains are built, add a seed_<domain>() section and
call it from handle().
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

DEMO_ZONE_CODE = "DEMOZ"  # marker: all demo data hangs under this zone

# --- realistic name pools (Ghanaian / Nigerian) ---
SURNAMES = ["Addo", "Mensah", "Boateng", "Owusu", "Asante", "Adjei", "Annan", "Darko",
            "Osei", "Agyeman", "Okafor", "Okeke", "Eze", "Obi", "Nwosu", "Adeyemi",
            "Okonkwo", "Balogun", "Afolabi", "Chukwu", "Danso", "Frimpong", "Gyasi",
            "Acheampong", "Bediako", "Ofori", "Sarpong", "Tetteh", "Quartey", "Lartey"]
MALE_NAMES = ["Kwame", "Kofi", "Kojo", "Yaw", "Kwabena", "Kwaku", "Emeka", "Chidi",
              "Obinna", "Ikenna", "Tunde", "Femi", "Seyi", "Nnamdi", "Uche", "Ebuka",
              "Daniel", "Samuel", "Emmanuel", "Joshua", "David", "Michael", "Joseph"]
FEMALE_NAMES = ["Ama", "Akosua", "Adwoa", "Abena", "Akua", "Yaa", "Afua", "Esi",
                "Ngozi", "Chioma", "Amara", "Ifeoma", "Adaeze", "Funke", "Bisi",
                "Grace", "Mercy", "Faith", "Joy", "Esther", "Ruth", "Deborah", "Sarah"]
CITIES = ["Accra", "Kumasi", "Tema", "Abuja", "Lagos", "Asokoro", "Wuse", "Gwarimpa"]
GROUP_NAMES = ["Alpha", "Bethel", "Cornerstone"]
PCF_NAMES = ["Grace PCF", "Faith PCF", "Victory PCF", "Glory PCF", "Mercy PCF"]
DEPT_NAMES = ["Sound", "Ushering", "Media", "Choir", "Security / Traffic Control",
              "Sanctuary Keepers", "Children", "Protocol"]


class Command(BaseCommand):
    help = "Seed realistic demo data (structure, members, families, assignments)."

    def add_arguments(self, parser):
        parser.add_argument("--scale", choices=["small", "default", "full"], default="default")
        parser.add_argument("--wipe", action="store_true", help="Clear demo data then seed")
        parser.add_argument("--wipe-only", action="store_true", help="Only clear demo data")
        parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")

    def handle(self, *args, **opts):
        random.seed(opts["seed"])
        self.scale = opts["scale"]

        if opts["wipe"] or opts["wipe_only"]:
            self._wipe()
            if opts["wipe_only"]:
                self.stdout.write(self.style.SUCCESS("Demo data wiped."))
                return

        # tiers: (groups, churches_per_group, pcfs_per_church, cells_per_pcf, members_target)
        tiers = {
            "small":   (1, 2, 2, 2, 120),
            "default": (2, 3, 3, 3, 400),
            "full":    (3, 4, 4, 4, 1500),
        }
        self.groups_n, self.churches_per_group, self.pcfs_per_church, \
            self.cells_per_pcf, self.members_target = tiers[self.scale]

        with transaction.atomic():
            from org.models import EcclesiasticalUnit
            if EcclesiasticalUnit.objects.filter(short_code=DEMO_ZONE_CODE).exists():
                self.stdout.write(self.style.WARNING(
                    "Demo data already exists. Re-run with --wipe to rebuild from scratch, "
                    "or --wipe-only to just clear it. Nothing changed."))
                return
            zone = self._seed_structure()
            self._seed_roles_and_members(zone)
            self._seed_families()
            self._seed_assignments()

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete (scale={self.scale}). "
            f"Zone '{zone.name}' with structure + members + families + assignments."))

    # ------------------------------------------------------------------ wipe
    def _wipe(self):
        from org.models import EcclesiasticalUnit
        from accounts.models import Member
        z = EcclesiasticalUnit.objects.filter(short_code=DEMO_ZONE_CODE).first()
        if not z:
            return
        # churches under demo zone (via groups) -> cascade most things
        from org.models import Church
        group_ids = list(EcclesiasticalUnit.objects.filter(parent_unit=z).values_list("id", flat=True))
        church_ids = list(Church.objects.filter(parent_unit_id__in=group_ids).values_list("id", flat=True))
        # delete members (cascades family/assignments/etc.), then structure
        Member.objects.filter(church_id__in=church_ids).delete()
        Church.objects.filter(id__in=church_ids).delete()
        EcclesiasticalUnit.objects.filter(id__in=group_ids).delete()
        z.delete()
        self.stdout.write("Wiped existing demo data.")

    # -------------------------------------------------------------- structure
    def _seed_structure(self):
        from org.models import EcclesiasticalUnit, Church, Department, Fellowship, Cell

        zone = EcclesiasticalUnit.objects.create(
            unit_type="zone", name="DEMO Zone (Test Data)", short_code=DEMO_ZONE_CODE)

        self.cells_pool = []  # (church, fellowship, cell)
        self.depts_pool = []  # (church, dept)
        for gi in range(self.groups_n):
            group = EcclesiasticalUnit.objects.create(
                unit_type="group", name=f"DEMO {GROUP_NAMES[gi % len(GROUP_NAMES)]} Group",
                short_code=f"{DEMO_ZONE_CODE}-G{gi+1}", parent_unit=zone)
            for ci in range(self.churches_per_group):
                code = f"DCHX{gi+1}{ci+1}"
                church = Church.objects.create(
                    name=f"DEMO CE {GROUP_NAMES[gi % len(GROUP_NAMES)]} {ci+1}",
                    short_code=code, parent_unit=group, status="active",
                    city=random.choice(CITIES), default_currency="GHS")
                # departments
                for dn in random.sample(DEPT_NAMES, k=min(4, len(DEPT_NAMES))):
                    dept = Department.objects.create(
                        church=church, name=dn, short_code=dn[:3].upper())
                    self.depts_pool.append((church, dept))
                # fellowships (PCFs) under a default department
                host_dept = Department.objects.create(church=church, name="Adults", short_code="ADU")
                for pi in range(self.pcfs_per_church):
                    pcf = Fellowship.objects.create(
                        church=church, parent_department=host_dept,
                        name=PCF_NAMES[pi % len(PCF_NAMES)], short_code=f"PCF{pi+1}")
                    for celli in range(self.cells_per_pcf):
                        cell = Cell.objects.create(
                            fellowship=pcf, name=f"{PCF_NAMES[pi % len(PCF_NAMES)].split()[0]} Cell {celli+1}",
                            short_code=f"C{pi+1}{celli+1}")
                        self.cells_pool.append((church, pcf, cell))
        self.stdout.write(f"Structure: 1 zone, {self.groups_n} groups, "
                          f"{len(set(c.id for c,_,_ in self.cells_pool))} churches, "
                          f"{len(self.cells_pool)} cells.")
        return zone

    # ----------------------------------------------------------- members+roles
    def _seed_roles_and_members(self, zone):
        from accounts.models import Member, generate_member_code
        from access.models import Role

        # roles per church (with ranks: higher = more senior) + applicability
        from access.models import UnitRoleApplicability
        self.roles_by_church = {}
        churches = set(c for c, _, _ in self.cells_pool)
        for church in churches:
            r = {
                "cell_leader": Role.objects.create(church=church, name="Cell Leader", is_leader=True, rank=30),
                "asst_cell_leader": Role.objects.create(church=church, name="Assistant Cell Leader", is_leader=True, rank=20),
                "pcf_leader": Role.objects.create(church=church, name="PCF Leader", is_leader=True, rank=50),
                "dept_head": Role.objects.create(church=church, name="Department Head", is_leader=True, rank=40),
                "member": Role.objects.create(church=church, name="Member", is_leader=False, rank=10),
            }
            self.roles_by_church[church.id] = r
            # applicability: which roles apply to which unit type
            appl = [
                (r["cell_leader"], "cell"), (r["asst_cell_leader"], "cell"), (r["member"], "cell"),
                (r["pcf_leader"], "fellowship"), (r["member"], "fellowship"),
                (r["dept_head"], "department"), (r["member"], "department"),
            ]
            UnitRoleApplicability.objects.bulk_create(
                [UnitRoleApplicability(role=role, unit_type=ut) for role, ut in appl])

        # distribute members across cells
        self.members = []
        per_cell = max(3, self.members_target // max(1, len(self.cells_pool)))
        today = date.today()
        for church, pcf, cell in self.cells_pool:
            for _ in range(per_cell):
                gender = random.choice(["male", "female"])
                first = random.choice(MALE_NAMES if gender == "male" else FEMALE_NAMES)
                surname = random.choice(SURNAMES)
                age = random.randint(16, 75)
                dob = today - timedelta(days=age * 365 + random.randint(0, 364))
                marital = random.choice(["single", "single", "married", "married", "widowed"])
                m = Member(
                    church=church, cell=cell, surname=surname, other_names=first,
                    preferred_name=first, gender=gender, date_of_birth=dob,
                    marital_status=marital,
                    phone_primary=f"0{random.choice('235')}{random.randint(1000000,9999999)}",
                    city=random.choice(CITIES), country=random.choice(["Ghana", "Nigeria"]),
                    baptism_status=random.choice(["not_baptized", "water_baptized", "not_baptized"]),
                    foundation_school_status=random.choice(["not_enrolled", "enrolled", "completed"]),
                    date_joined=today - timedelta(days=random.randint(30, 2500)),
                    is_active=True, member_code="PENDING")
                self.members.append((m, church, pcf, cell))

        # bulk create members, then assign codes (code gen needs church + sequence)
        Member.objects.bulk_create([m for m, _, _, _ in self.members], batch_size=500)
        # assign member_codes (sequence-based; do per church)
        for m, church, pcf, cell in self.members:
            m.member_code = generate_member_code(church, pcf.short_code)
        Member.objects.bulk_update([m for m, _, _, _ in self.members], ["member_code"], batch_size=500)
        self.stdout.write(f"Members: {len(self.members)} created with codes.")

    # ----------------------------------------------------------------- families
    def _seed_families(self):
        from family.models import (Household, HouseholdMember, MemberSpouseLink,
                                    FamilyRelationship, HouseholdRole,
                                    FamilyRelationshipType, FamilyParentType)
        # group members by cell for plausible household formation
        by_church = {}
        for m, church, pcf, cell in self.members:
            by_church.setdefault(church.id, []).append(m)

        households, hh_members, spouse_links, relationships = [], [], [], []
        for church_id, mems in by_church.items():
            married = [m for m in mems if m.marital_status == "married"]
            random.shuffle(married)
            # pair married members into spouse links + households (~half of married)
            for i in range(0, len(married) - 1, 2):
                if random.random() > 0.7:
                    continue
                a, b = married[i], married[i+1]
                spouse_links.append(MemberSpouseLink(
                    member_a=a, member_b=b,
                    marriage_date=date.today() - timedelta(days=random.randint(365, 9000)),
                    is_current=True))
                relationships.append(FamilyRelationship(
                    type=FamilyRelationshipType.SPOUSE_OF, from_member=a, to_member=b))
                hh = Household(church_id=church_id, name=f"{a.surname} Household", head_member=a)
                households.append((hh, a, b))

        Household.objects.bulk_create([hh for hh, _, _ in households], batch_size=500)
        MemberSpouseLink.objects.bulk_create(spouse_links, batch_size=500)
        FamilyRelationship.objects.bulk_create(relationships, batch_size=500)
        # household members: head + spouse
        for hh, a, b in households:
            hh_members.append(HouseholdMember(household=hh, member=a,
                              relationship_to_head=HouseholdRole.HEAD, is_primary=True))
            hh_members.append(HouseholdMember(household=hh, member=b,
                              relationship_to_head=HouseholdRole.SPOUSE))
        HouseholdMember.objects.bulk_create(hh_members, batch_size=500)
        self.stdout.write(f"Families: {len(households)} households, "
                          f"{len(spouse_links)} spouse links.")

    # -------------------------------------------------------------- assignments
    def _seed_assignments(self):
        from access.models import Assignment
        # group members by cell to pick leaders
        cell_members = {}
        for m, church, pcf, cell in self.members:
            cell_members.setdefault((church.id, pcf.id, cell.id), []).append((m, church, pcf, cell))

        assignments = []
        seen_pcf_leaders, seen_dept_heads = set(), set()
        for (church_id, pcf_id, cell_id), grp in cell_members.items():
            roles = self.roles_by_church[church_id]
            # cell leader = first member of the cell
            if grp:
                leader_m, church, pcf, cell = grp[0]
                assignments.append(Assignment(member=leader_m, role=roles["cell_leader"], cell=cell))
                # one PCF leader per pcf
                if pcf_id not in seen_pcf_leaders:
                    assignments.append(Assignment(member=leader_m, role=roles["pcf_leader"], fellowship=pcf))
                    seen_pcf_leaders.add(pcf_id)
            # everyone gets a plain Member assignment to their cell
            for m, church, pcf, cell in grp:
                assignments.append(Assignment(member=m, role=roles["member"], cell=cell))

        # a few department heads
        for church, dept in self.depts_pool:
            grp = [m for m, c, p, cl in self.members if c.id == church.id]
            if grp and dept.church_id not in seen_dept_heads:
                roles = self.roles_by_church[church.id]
                assignments.append(Assignment(member=random.choice(grp),
                                               role=roles["dept_head"], department=dept))
        Assignment.objects.bulk_create(assignments, batch_size=500)
        self.stdout.write(f"Assignments: {len(assignments)} created.")
