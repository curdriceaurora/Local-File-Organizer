"""Gold-labelled extraction corpus.

Annotation guidelines (apply them when adding cases):

- ``document_type``: the words in the text that name what the document is
  ("INVOICE", "Lease Agreement"). Only label it when it is literally present.
- ``organization``: companies, institutions, agencies.
- ``person``: people's names as written (no titles such as "Dr.").
- ``date``: calendar dates as written. Not durations, not bare years.
- ``amount``: monetary amounts as written, including the currency marker.
- ``reference_id``: invoice/order/policy/case/account identifiers — the
  identifier token only (``INV-4821``, not ``Invoice #INV-4821``).

Every gold span must occur verbatim in its document's text; the unit tests
enforce this so grounding metrics stay meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass

ENTITY_CLASSES: tuple[str, ...] = (
    "document_type",
    "organization",
    "person",
    "date",
    "amount",
    "reference_id",
)

CLASS_DESCRIPTIONS: dict[str, str] = {
    "document_type": "the words in the text naming what kind of document this is",
    "organization": "companies, institutions and agencies",
    "person": "people's names, without titles",
    "date": "calendar dates exactly as written (not durations or bare years)",
    "amount": "monetary amounts exactly as written, including currency markers",
    "reference_id": "invoice, order, policy, case or account identifiers (the identifier only)",
}


@dataclass(frozen=True)
class GoldEntity:
    """One expected extraction."""

    entity_class: str
    text: str


@dataclass(frozen=True)
class EvalCase:
    """A document plus its gold extractions."""

    case_id: str
    source_format: str
    text: str
    gold: tuple[GoldEntity, ...]


def _g(entity_class: str, text: str) -> GoldEntity:
    """Create an expected extraction for a corpus case."""
    return GoldEntity(entity_class, text)


_LONG_REPORT = (
    "QUARTERLY VENDOR REVIEW\n"
    "Prepared by Priya Raman for the Northwind Traders procurement committee.\n\n"
    "Summary. Three vendors were reviewed this quarter. Overall spend was in line "
    "with forecast and no contracts were terminated. The committee met twice and "
    "agreed to consolidate office-supply purchasing under a single framework "
    "agreement beginning next fiscal year. The remainder of this report walks "
    "through each vendor in turn, with the relevant purchase orders listed so "
    "that finance can reconcile them against the ledger.\n\n"
    "1. Contoso Office Supply. Spend this quarter was $48,210.55 across 212 "
    "orders. Delivery performance was acceptable, although two late shipments in "
    "the second month caused a short stock-out of printer toner. Purchase order "
    "PO-77120 remains open pending a credit note. The account manager, Luis "
    "Ortega, has committed to a remediation plan.\n\n"
    "2. Fabrikam Logistics. Spend was $112,900.00, mostly freight. The rate card "
    "renegotiated in the prior quarter is now fully in effect and produced the "
    "expected savings. No open disputes. The committee recommends renewing the "
    "master services agreement, which expires on 30 June 2026.\n\n"
    "3. Litware Consulting. A fixed-fee engagement for the warehouse layout "
    "study, invoiced once at €18,500. The final deliverable was accepted on "
    "12 March 2026 by Hannah Becker in operations. This engagement is closed.\n\n"
    "Next review: the committee will reconvene on 9 July 2026. Questions about "
    "this report should go to the procurement mailbox rather than to individual "
    "committee members, so that responses can be tracked centrally.\n"
)

CORPUS: tuple[EvalCase, ...] = (
    EvalCase(
        "invoice_plain",
        "plain_text",
        "INVOICE\nInvoice #INV-4821\nFrom: Acme Corp\nBill to: Globex Industries\n"
        "Invoice date: 2024-02-01\nDue date: 2024-02-15\nAmount due: $8,500.00\n",
        (
            _g("document_type", "INVOICE"),
            _g("reference_id", "INV-4821"),
            _g("organization", "Acme Corp"),
            _g("organization", "Globex Industries"),
            _g("date", "2024-02-01"),
            _g("date", "2024-02-15"),
            _g("amount", "$8,500.00"),
        ),
    ),
    EvalCase(
        "receipt_ocr",
        "image_ocr",
        "WHOLE F00DS MARKET  #1042\n03/14/2024  18:22\nORGANIC BANANAS   2.49\n"
        "OAT MILK   4.99\nSUBTOTAL  7.48\nTAX  0.00\nTOTAL  $7.48\nVISA ****5521\n"
        "Receipt 0042-1187-22  Thank you!",
        (
            _g("organization", "WHOLE F00DS MARKET"),
            _g("date", "03/14/2024"),
            _g("amount", "$7.48"),
            _g("reference_id", "0042-1187-22"),
            _g("document_type", "Receipt"),
        ),
    ),
    EvalCase(
        "lease_agreement",
        "pdf",
        "RESIDENTIAL Lease Agreement\nThis Lease Agreement is made on January 5, 2025 "
        'between Harbor View Properties LLC ("Landlord") and Maria Gonzalez '
        '("Tenant"). The term begins February 1, 2025 and runs for twelve months. '
        "Monthly rent is $2,150 payable on the first of each month. A security "
        "deposit of $4,300 is due at signing.",
        (
            _g("document_type", "Lease Agreement"),
            _g("date", "January 5, 2025"),
            _g("date", "February 1, 2025"),
            _g("organization", "Harbor View Properties LLC"),
            _g("person", "Maria Gonzalez"),
            _g("amount", "$2,150"),
            _g("amount", "$4,300"),
        ),
    ),
    EvalCase(
        "medical_discharge",
        "pdf",
        "Discharge Summary\nPatient: Robert Chen   MRN: 00482913\nAdmitted: 2024-06-02  "
        "Discharged: 2024-06-05\nAttending: Dr. Aisha Patel, St. Mary's Hospital\n"
        "Diagnosis: community-acquired pneumonia. Follow up in 2 weeks.",
        (
            _g("document_type", "Discharge Summary"),
            _g("person", "Robert Chen"),
            _g("reference_id", "00482913"),
            _g("date", "2024-06-02"),
            _g("date", "2024-06-05"),
            _g("person", "Aisha Patel"),
            _g("organization", "St. Mary's Hospital"),
        ),
    ),
    EvalCase(
        "email_meeting",
        "email",
        "From: jordan.lee@initech.com\nTo: team@initech.com\nSubject: Offsite planning\n\n"
        "Hi all, the offsite is confirmed for 18 April 2024 at the Riverside Conference "
        "Center. Sam Whitfield is coordinating travel. Budget approved at $12,000.\n"
        "Thanks, Jordan Lee",
        (
            _g("date", "18 April 2024"),
            _g("organization", "Riverside Conference Center"),
            _g("person", "Sam Whitfield"),
            _g("amount", "$12,000"),
            _g("person", "Jordan Lee"),
        ),
    ),
    EvalCase(
        "insurance_policy",
        "pdf",
        "Certificate of Insurance\nPolicy Number: HO-2291-5530-A\nInsurer: Evergreen Mutual "
        "Insurance Company\nNamed Insured: Daniel and Keiko Morrison\nPolicy Period: "
        "04/01/2024 to 04/01/2025\nAnnual Premium: $1,386.40",
        (
            _g("document_type", "Certificate of Insurance"),
            _g("reference_id", "HO-2291-5530-A"),
            _g("organization", "Evergreen Mutual Insurance Company"),
            _g("date", "04/01/2024"),
            _g("date", "04/01/2025"),
            _g("amount", "$1,386.40"),
        ),
    ),
    EvalCase(
        "bank_statement",
        "spreadsheet",
        "Date,Description,Amount\n2024-03-01,Payroll deposit - Tailspin Toys,3200.00\n"
        "2024-03-04,Rent - Harbor View Properties LLC,-2150.00\n"
        "2024-03-09,Grocery - Whole Foods,-86.12\n"
        "Account 4410-9921 statement period March 2024",
        (
            _g("date", "2024-03-01"),
            _g("date", "2024-03-04"),
            _g("date", "2024-03-09"),
            _g("organization", "Tailspin Toys"),
            _g("organization", "Harbor View Properties LLC"),
            _g("organization", "Whole Foods"),
            _g("reference_id", "4410-9921"),
            _g("document_type", "statement"),
        ),
    ),
    EvalCase(
        "tax_form_ocr",
        "pdf_scanned",
        "Form W-2  Wage and Tax Statement  2023\nEmployer: Blue Yonder Airlines Inc\n"
        "Employee: Chen Wei\nWages, tips, other comp: 84,250.00\n"
        "Federal income tax withheld: 12,410.33",
        (
            _g("document_type", "Wage and Tax Statement"),
            _g("organization", "Blue Yonder Airlines Inc"),
            _g("person", "Chen Wei"),
            _g("amount", "84,250.00"),
            _g("amount", "12,410.33"),
        ),
    ),
    EvalCase(
        "meeting_notes",
        "plain_text",
        "Meeting notes — 7 May 2024\nAttendees: Olivia Brooks, Marcus Hale, Yuki Tanaka\n"
        "Decisions: ship v2 of the onboarding flow; Marcus to follow up with Adventure "
        "Works on the contract renewal.",
        (
            _g("document_type", "Meeting notes"),
            _g("date", "7 May 2024"),
            _g("person", "Olivia Brooks"),
            _g("person", "Marcus Hale"),
            _g("person", "Yuki Tanaka"),
            _g("organization", "Adventure Works"),
        ),
    ),
    EvalCase(
        "code_no_entities",
        "code",
        "def fibonacci(n: int) -> int:\n    if n <= 1:\n        return n\n"
        "    return fibonacci(n - 1) + fibonacci(n - 2)\n",
        (),
    ),
    EvalCase(
        "order_confirmation",
        "email",
        "Your order has shipped!\nOrder # 112-5582910-7734401\nPlaced on Sep 3, 2024\n"
        "Sold by: Proseware Electronics\nItems: USB-C dock (1)\nOrder total: USD 189.99\n"
        "Estimated delivery: Sep 6, 2024",
        (
            _g("reference_id", "112-5582910-7734401"),
            _g("date", "Sep 3, 2024"),
            _g("organization", "Proseware Electronics"),
            _g("amount", "USD 189.99"),
            _g("date", "Sep 6, 2024"),
        ),
    ),
    EvalCase(
        "long_vendor_report",
        "pdf",
        _LONG_REPORT,
        (
            _g("document_type", "QUARTERLY VENDOR REVIEW"),
            _g("person", "Priya Raman"),
            _g("organization", "Northwind Traders"),
            _g("organization", "Contoso Office Supply"),
            _g("amount", "$48,210.55"),
            _g("reference_id", "PO-77120"),
            _g("person", "Luis Ortega"),
            _g("organization", "Fabrikam Logistics"),
            _g("amount", "$112,900.00"),
            _g("date", "30 June 2026"),
            _g("organization", "Litware Consulting"),
            _g("amount", "€18,500"),
            _g("date", "12 March 2026"),
            _g("person", "Hannah Becker"),
            _g("date", "9 July 2026"),
        ),
    ),
)


def validate_corpus(corpus: tuple[EvalCase, ...] = CORPUS) -> list[str]:
    """List duplicate IDs, unknown entity classes, and gold spans absent from text.

    Return an empty list when every case satisfies these checks.
    """
    problems: list[str] = []
    seen: set[str] = set()
    for case in corpus:
        if case.case_id in seen:
            problems.append(f"duplicate case_id {case.case_id!r}")
        seen.add(case.case_id)
        for ent in case.gold:
            if ent.entity_class not in ENTITY_CLASSES:
                problems.append(f"{case.case_id}: unknown class {ent.entity_class!r}")
            if ent.text not in case.text:
                problems.append(f"{case.case_id}: gold span {ent.text!r} not in text")
    return problems
