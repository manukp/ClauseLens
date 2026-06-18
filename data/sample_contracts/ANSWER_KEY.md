# ANSWER_KEY.md - planted issues in the (upgraded, multi-page) sample contracts

Test oracle and demo cheat-sheet. Pass condition = issue detected + correctly cited
(exact severity is a soft check; the judge may shift one level).

The contracts are now multi-page and the hero is a three-document set, so several issues sit
on later pages or span documents - this is deliberate, to exercise scroll-into-view and
cross-document reconciliation.

---

## HERO: software_dev/ (upload all THREE files as ONE analysis)
Files: 01_master_services_agreement.md (MSA), 02_statement_of_work.md (SOW-01),
03_change_order.md (CO-01).

### Within-document planted issues
| # | Where | Issue | Type | Expected severity |
|---|-------|-------|------|-------------------|
| 1 | MSA 4.3 | Milestone 2 payment has no named approval authority (M1=Head of Procurement 4.2, M3=CFO 4.4, M2=none) | Gap | High |
| 2 | SOW 3.3 vs 5.1 | UAT due 30 Sep, but its prerequisite Data Migration completes 15 Oct - impossible sequence | Conflict | High |
| 3 | SOW 2.2 vs 4.1 | Data Migration has acceptance criteria but no named owner (4.1 assigns Vendor to 2.1 and 2.3, omits 2.2) | Gap | Medium |
| 4 | SOW 2.3 | Performance Tuning has no acceptance criteria (2.1, 2.2 do) | Gap | Medium |
| 5 | MSA cl.6 | IP clause covers Background IP only; silent on ownership of the newly developed platform/Deliverables | Gap | High |

### Cross-document planted issues (the multi-document differentiator)
| # | Where | Issue | Type | Expected severity |
|---|-------|-------|------|-------------------|
| C1 | SOW 2.5 vs MSA cl.4 | Hypercare Support is a Deliverable, but the MSA's three-milestone payment schedule does not fund it | Gap | High |
| C2 | CO 3.1/3.2 vs SOW 5.1/3.3 | Change Order brings go-live forward to 25 Sep while expressly leaving Data Migration (completes 15 Oct) and UAT (30 Sep) unchanged - acceleration is impossible against the unchanged prerequisite | Conflict | High |
| C3 | CO 4.1 vs MSA 4.2/4.4 | CO adds an INR 8,00,000 fee with no named payment approval authority (unlike the MSA milestones) | Gap | Medium |

### Expected legitimate "extras" (not required, do NOT penalise; judge may contextualise)
- Appendix A (Test Plan) referenced (SOW 2.1) but marked "[To be attached]" - reasonable Risk/Gap.
- Data Protection clause (MSA cl.10) is generic/thin given customer onboarding data - reasonable Gap.
- Single-point-of-contact dependency on Ms. R. Iyer with no succession - reasonable Risk.
Note: Limitation of Liability (MSA cl.8) and Warranty (MSA cl.7) are now PRESENT, so they should
NOT be flagged as missing (they were extras in the thin version).

---

## construction_fitout_agreement.md
| # | Where | Issue | Type | Expected severity |
|---|-------|-------|------|-------------------|
| 1 | 3.2 vs 7.1 | 12 weeks from 1 Aug ~ 24 Oct, but LDs trigger at 15 Oct - inconsistent completion dates | Conflict | High |
| 2 | 6.2 | Variations up to INR 5,00,000 approvable with no named approver | Gap | Medium |
| 3 | 4.4 | Snagging rectification has no acceptance criteria and no defined defects-liability/snagging period | Gap | Medium |
| 4 | 5.1 | Electrical fit-out depends on Client-supplied layout, but no responsible party or date | Dependency | Medium |
| 5 | (whole doc) | No health & safety / site safety compliance clause | Gap | Medium |

## marketing_services_agreement.md
| # | Where | Issue | Type | Expected severity |
|---|-------|-------|------|-------------------|
| 1 | 7.1 vs 7.2 | Fixed 6-month term ending 31 Dec contradicts automatic annual renewal | Conflict | Medium |
| 2 | 3.2 | Monthly campaign report has no acceptance criteria (3.1, 3.3 do) | Gap | Low |
| 3 | 4.1 | Media Spend up to INR 10,00,000/month with no named approval authority | Gap | High |
| 4 | 5.1 | Customer/PII data shared but no data-protection / processing clause | Gap | High |
| 5 | cl.8 | Ownership of newly created creative assets not assigned (clause covers pre-existing IP + licence only) | Gap | Medium |

## clinical_research_agreement.md
| # | Where | Issue | Type | Expected severity |
|---|-------|-------|------|-------------------|
| 1 | 4.2 vs 4.1 | Interim analysis due end Q2, but enrolment completes end Q3 - analysis precedes the data | Conflict | High |
| 2 | 3.2 | Interim analysis report has no owner and no acceptance criteria (3.1, 3.3 do) | Gap | Medium |
| 3 | 6.2 | Pass-Through Costs reimbursed "as incurred" with no cap or approval authority | Gap | High |
| 4 | 5.1 | Sponsor to supply Investigational Product, but no date or responsible contact | Dependency | Medium |
| 5 | (whole doc) | No patient-consent / data-privacy / regulatory-compliance clause for a clinical trial | Gap | High |

---

## Notes for testing
- Pass = issue detected AND correctly cited. Exact severity is a soft check.
- The hero's value is the cross-document set (C1-C3): these require reconciling MSA + SOW + CO and
  cannot be found in any single document. Verify the conflict/gap citations point across the
  correct documents and pages.
- Several hero issues (C1, C2, MSA cl.6) sit on later pages / different documents - use them to
  verify the scroll-into-view fix lands the highlight in view, not just paints it off-screen.
- Lead the demo with the hero. C2 (accelerated go-live vs unchanged 15 Oct prerequisite) is the
  strongest panel moment - a contradiction no single-document review would catch.
