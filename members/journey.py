"""
Member journey timeline — derived at render time from existing data. No new
tables. Each milestone is tagged:
  - "confirmed": we have a dated record for it
  - "inferred":  implied by a later milestone but with no direct date of its own
  - "future":    an aspirational step not yet reached (shown greyed)
  - "pending":   depends on a domain not yet built (e.g. giving/partnership)

Mirrors the original's "solid check = confirmed, light check = inferred".
"""
from accounts.enums import AccessLevel

# leadership ladder for the aspirational/future milestones (low -> high)
_LADDER = [
    ("unit_leader", "Unit Leader"),
    ("admin", "Church Admin"),
    ("church_pastor", "Church Pastor"),
    ("group_pastor", "Group Pastor"),
    ("zonal_pastor", "Zonal Pastor"),
]


def build_journey(member, assignments, profile=None):
    """Return an ordered list of milestone dicts:
        {key, label, sub, date, status}  status in confirmed|inferred|future|pending
    `assignments` should be all of the member's assignments (active + past)."""
    milestones = []

    # --- born again (confirmed if dated) ---
    if member.born_again_date:
        milestones.append(dict(key="born_again", label="Born Again", sub=None,
                               date=member.born_again_date, status="confirmed"))

    # --- member registration (date_joined) ---
    if member.date_joined:
        milestones.append(dict(key="registration", label="Member Registration", sub=None,
                               date=member.date_joined, status="confirmed"))

    # --- foundation school ---
    fs = member.foundation_school_status
    if fs == "completed":
        milestones.append(dict(key="fs", label="Foundation School", sub="Completed",
                               date=member.foundation_school_completion_date, status="confirmed"))
    elif fs == "enrolled":
        milestones.append(dict(key="fs", label="Foundation School", sub="Enrolled",
                               date=None, status="inferred"))

    # --- placement + leadership from assignments ---
    # group assignments by unit kind; earliest start_date wins for "assigned to X"
    has_cell = has_fellowship = has_church_role = False
    for a in sorted(assignments, key=lambda x: (x.start_date or member.date_joined or x.created_at.date())):
        unit_name = (a.cell.name if a.cell else a.fellowship.name if a.fellowship
                     else a.department.name if a.department else "—")
        unit_kind = ("Cell" if a.cell else "Fellowship" if a.fellowship
                     else "Department" if a.department else "")
        leader = a.role.is_leader
        if a.cell and not has_cell:
            milestones.append(dict(key=f"cell_{a.id}", label="Assigned to Cell",
                                   sub=unit_name, date=a.start_date, status="confirmed"))
            has_cell = True
        if a.fellowship and not has_fellowship:
            milestones.append(dict(key=f"fel_{a.id}", label="Assigned to PCF",
                                   sub=unit_name, date=a.start_date, status="confirmed"))
            has_fellowship = True
        if leader:
            milestones.append(dict(key=f"lead_{a.id}",
                                   label=f"{a.role.name}",
                                   sub=f"{unit_kind} · {unit_name}".strip(" ·"),
                                   date=a.start_date,
                                   status="confirmed" if a.end_date is None else "past"))

    # --- "Assigned to Church" inferred (everyone has a church, rarely dated) ---
    if member.church_id:
        milestones.insert(
            _insert_after_registration(milestones),
            dict(key="church", label="Assigned to Church", sub=member.church.name,
                 date=None, status="inferred"))

    # --- pending (needs Finance) ---
    milestones.append(dict(key="partnership", label="Partnership Participation",
                           sub="Not yet tracked (requires Finance)", date=None, status="pending"))

    # sort: dated milestones chronologically, undated ones kept near their context
    milestones = _chronological(milestones)

    # --- future leadership ladder (aspirational, greyed) ---
    current_rank = _member_access_rank(member, profile)
    for level_key, level_label in _LADDER:
        from accounts.enums import ACCESS_RANK
        if ACCESS_RANK.get(level_key, 0) > current_rank:
            milestones.append(dict(key=f"future_{level_key}", label=level_label,
                                   sub=None, date=None, status="future"))

    return milestones


def _insert_after_registration(milestones):
    for i, m in enumerate(milestones):
        if m["key"] == "registration":
            return i + 1
    return len(milestones)


def _chronological(milestones):
    """Stable sort: dated items by date; undated items hold their relative spot."""
    dated = [m for m in milestones if m["date"]]
    undated = [m for m in milestones if not m["date"]]
    dated.sort(key=lambda m: m["date"])
    # weave: keep undated 'pending' at the end; other undated stay in original order
    pending = [m for m in undated if m["status"] == "pending"]
    other_undated = [m for m in undated if m["status"] != "pending"]
    return other_undated[:1] + dated + other_undated[1:] + pending if other_undated else dated + pending


def _member_access_rank(member, profile):
    """Best-effort current leadership rank of the member (for future milestones)."""
    from accounts.enums import ACCESS_RANK
    prof = member.profiles.first() if hasattr(member, "profiles") else None
    if prof and getattr(prof, "access_level", None):
        return ACCESS_RANK.get(prof.access_level, 1)
    return ACCESS_RANK.get("member", 1)
