# Church Management System — Build Roadmap

Django + PostgreSQL rebuild of the Supabase system. This maps every feature in
the original (from the full sidebar) against what's built, and sequences the rest
in logical dependency order.

Status legend: ✅ Done · 🟡 Partial · 🔲 Not started · ⬛ Infra/cross-cutting

---

## 1. What's BUILT (foundation + people + gatherings)

| Area | Status | Notes |
|---|---|---|
| Org structure (zone→group→church→fellowship→cell, departments, ministry groups) | ✅ | `ecclesiastical_units`, `churches`, `fellowships`, `cells`, `departments`, `ministry_groups` |
| Auth (email/password, phone OTP) | ✅ | server-rendered, dev-mode OTP to console |
| Registration + approval | ✅ | self-reg → approval queue → member_code at approval |
| Access / scope layer | ✅ | corrected ranking; reach (church/group/zone walk); Layer-2 assignment narrowing |
| Members directory + rich tabbed profile | ✅ | Profile/Assignments/Attendance tabs live; Family/Finance/Journey/History stubbed |
| Member QR (generate + print) | ✅ | encodes member_code |
| Events + month calendar | ✅ | scoped by unit_type |
| Recurrence (templates, generate-ahead, exceptions) | ✅ | weekly / monthly |
| Attendance register (expected-list, turnout %, default-absent, mark-all, search) | ✅ | snapshot at event creation |
| Head counts | ✅ | summed contributions |
| Register close/reopen lifecycle | ✅ | separate from event status; who-closed tracked |
| QR scan-to-mark (+ manual fallback) | ✅* | *camera needs HTTPS + real-device verification |
| Visitor capture (inline on register) | ✅ | lands at first_timer stage |
| First-timers follow-up pipeline | ✅ | queue, stages, assign, contact log, convert-to-member |

Test count: ~82, all passing.

---

## 2. NOT YET BUILT (remaining sidebar features → real tables)

| Sidebar item | Tables | Size | Depends on |
|---|---|---|---|
| **Assignments actions** (finish profile) | `assignments`, `roles` | S | — (models exist) |
| **Audit log** | `audit_log` | M | — (cross-cutting; back-fills History tab) |
| **Family / Households** | `households`, `household_members`, `family_relationships`, `member_spouse_links` | M | — |
| **Finance** (income/expense/pledges, multi-currency) | `income_records`, `expense_records`, `income_currency_amounts`, `expense_currency_amounts`, `currency_snapshots`, `pledges`, `finance_accounts`, `finance_categories` | L | audit log (strongly) |
| **Foundation School** | `fs_classes`, `fs_sessions`, `fs_enrollments`, `fs_attendance` | M | (reuses attendance patterns) |
| **Announcements** | `announcements`, `announcement_views` | M | scope layer (have it) |
| **Comms** (SMS/email/segments) | `comms_messages`, `comms_recipients`, `comms_segments`, `sms_broadcasts`, `email_broadcasts`, `telegram_group_links` | L | external providers (SMS/email gateways) |
| **Birthdays** | (derived from members.date_of_birth) + `birthday_card_templates` | S | — |
| **Leaders Forum** | `forum_posts`, `forum_replies`, `forum_reactions`, `forum_attachments` | M | — |
| **Visitation** | `visitations` | S | — |
| **Welfare** | `welfare_cases`, `welfare_case_notes` | M | — |
| **Recognition** | (likely derived / milestones) | S | — |
| **Requests** | `member_change_requests`, `cell_creation_requests`, `member_transfers` | M | (transfers partly done) |
| **Reports** | (cross-domain queries) | M–L | the domains it reports on |
| **Dashboard** (unit drill-down metrics) | (aggregates across domains) | M | the domains it summarizes |
| **Member Journey tab** | (derived from existing data) | S | — |
| **Settings** (`church_settings`) | `church_settings`, `currency_snapshots` | S–M | — |

---

## 3. PROPOSED SEQUENCE (logical dependency order)

### Phase A — Finish what's open (small, high-value)
1. **Assignments actions** — add/change/end + change placement. Finishes the member profile. (S)
2. **Member Journey tab** — derive the timeline from data we already have (registration, assignments, roles). Fills a stubbed tab cheaply. (S)
3. **Birthdays** — derived from DOB; quick win, visible value. (S)

### Phase B — Cross-cutting backbone (do before Finance)
4. **Audit log** — captures all writes (member edits, assignments, close/reopen, and later finance). Back-fills the History tab. Should exist before money. (M)

### Phase C — Core pastoral domains (self-contained, high pastoral value)
5. **Family / Households** — fills the Family tab; marriages, children, parents. (M)
6. **Visitation** — simple, pairs with pastoral care. (S)
7. **Welfare** — cases + notes; pairs with visitation. (M)

### Phase D — Finance (large, sensitive — after audit log)
8. **Finance** — accounts/categories, income/expense with multi-currency (base_amount + rate + currency_snapshots), pledges, submit→approve→void workflow. Fills the Finance tab. (L)

### Phase E — Education & engagement
9. **Foundation School** — classes/sessions/enrollments/attendance (reuses attendance patterns). (M)
10. **Announcements** — targeted posts + read tracking. (M)
11. **Leaders Forum** — posts/replies/reactions. (M)
12. **Recognition** — milestones/awards. (S)

### Phase F — Communications & requests
13. **Requests** — change requests, cell-creation requests, transfers (partly done). (M)
14. **Comms** — SMS/email/segments. NOTE: needs external gateway decisions + likely internet egress; revisit at/after deployment. (L)

### Phase G — Synthesis (after the domains exist)
15. **Reports** — cross-domain reporting. (M–L)
16. **Dashboard** — unit drill-down metrics (the zone/group/church/PCF/cell cards). (M)
17. **Settings** — church_settings, currency config, etc. (S–M)

### Phase H — Deployment & hardening (the infra track, parallel/after)
- TLS / firewall / VPN (unblocks QR camera scanning on phones)
- Static files done properly (ManifestStaticFilesStorage / cache-busting)
- Backups, on-prem Postgres at head office
- Data migration from Supabase (preserve UUIDs, map profiles→Users, reset passwords)

---

## 4. KEY PRINCIPLES (carried forward)
- Read ACTUAL schema columns/enums before modelling — never infer.
- Render pages (not just green tests) before shipping.
- Pull real RLS/function bodies for security-critical logic.
- Net-new tables/columns beyond Supabase are OK when deliberate — flag for data-migration.
- Each slice: build → validate (check + tests) → render → zip → deploy notes → honest caveats.
- Confirm large builds via structured questions first.

---

## 5. NOTES ON SEQUENCING CHOICES
- **Audit log before Finance** is the one hard ordering constraint — money without an
  audit trail is the combination to avoid.
- **Comms is gated on external decisions** (which SMS/email provider; internet egress
  from an on-prem server) — likely a post-deployment item, not a pure-code slice.
- **Reports & Dashboard come late** by necessity — they aggregate domains that must
  exist first. Building them early means rework as each new domain lands.
- **Foundation School reuses attendance patterns** — lower risk than its size suggests.
