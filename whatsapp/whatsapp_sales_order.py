import frappe
import requests
import re
from frappe.utils import flt
from frappe.utils import formatdate
from frappe.utils import fmt_money
from frappe.utils.pdf import get_pdf


def clean_egypt_mobile(mobile):
    mobile = (mobile or "").strip()
    if not mobile:
        return ""

    # Keep explicit international format as-is, but without symbols.
    had_plus_prefix = mobile.startswith("+")
    mobile = re.sub(r"\D", "", mobile)

    if not mobile:
        return ""

    if had_plus_prefix:
        return mobile

    # Convert 00-prefixed international format to plain country-code format.
    if mobile.startswith("00"):
        return mobile[2:]

    # Keep Egypt local format compatibility (e.g. 010xxxxxxx -> 2010xxxxxxx).
    if mobile.startswith("20"):
        return mobile

    if mobile.startswith("0"):
        return "20" + mobile[1:]

    # Assume already in country-code format if it does not start with 0.
    return mobile


def get_customer_contact(customer, preferred_contact_name=None):
    if preferred_contact_name:
        preferred_exists = frappe.db.exists("Contact", preferred_contact_name)
        if preferred_exists:
            contact = frappe.get_doc("Contact", preferred_contact_name)
            mobile = contact.mobile_no or contact.phone or ""
            contact_person = contact.first_name or contact.full_name or ""
            if mobile:
                return preferred_contact_name, contact_person, mobile

    customer_primary_contact = frappe.db.get_value("Customer", customer, "customer_primary_contact")
    contact_name = customer_primary_contact

    if not contact_name:
        links = frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": customer,
                "parenttype": "Contact",
            },
            fields=["parent"],
            order_by="creation asc",
            limit=20,
        )

        for link in links:
            candidate_name = link.parent
            if not candidate_name:
                continue
            candidate = frappe.get_doc("Contact", candidate_name)
            if candidate.mobile_no or candidate.phone:
                contact_name = candidate_name
                break

        if not contact_name and links:
            contact_name = links[0].parent

    if not contact_name:
        return None, None, None

    contact = frappe.get_doc("Contact", contact_name)
    mobile = contact.mobile_no or contact.phone or ""
    contact_person = contact.first_name or contact.full_name or ""

    return contact_name, contact_person, mobile


def get_recipient_name(contact_person, customer_name, customer_code):
    """Return the best human-readable recipient name, avoiding email-like fallbacks."""
    candidates = [contact_person, customer_name, customer_code]
    for value in candidates:
        text = (value or "").strip()
        if text and "@" not in text:
            return text

    # If only email-like values exist, keep a neutral fallback.
    return "\u0639\u0645\u064a\u0644\u0646\u0627 \u0627\u0644\u0643\u0631\u064a\u0645"


def get_default_print_format(doctype):
    return frappe.get_meta(doctype).default_print_format or "Standard"


def get_doc_total_amount(doc):
    rounded = flt(getattr(doc, "rounded_total", 0))
    if rounded:
        return rounded
    return flt(getattr(doc, "grand_total", 0))


def format_doc_amount(amount, currency):
    return fmt_money(amount, currency=currency)


@frappe.whitelist()
def send_sales_order_pdf_now(name):
    if not name:
        frappe.throw("Sales Order name is required")

    doc = frappe.get_doc("Sales Order", name)
    send_sales_order_pdf(doc)
    return "OK"


@frappe.whitelist()
def send_sales_order_text_now(name):
    if not name:
        frappe.throw("Sales Order name is required")

    doc = frappe.get_doc("Sales Order", name)
    _send_sales_order_text(doc)
    return "OK"


@frappe.whitelist()
def send_sales_invoice_pdf_now(name):
    if not name:
        frappe.throw("Sales Invoice name is required")

    doc = frappe.get_doc("Sales Invoice", name)
    send_sales_invoice_pdf(doc)
    return "OK"


@frappe.whitelist()
def send_payment_entry_message_now(name):
    if not name:
        frappe.throw("Payment Entry name is required")

    doc = frappe.get_doc("Payment Entry", name)
    send_payment_entry_message(doc)
    return "OK"


@frappe.whitelist()
def send_whatsapp_ping_now(mobile=None, chat_id=None, text=None):
    """Send a plain text WhatsApp message for delivery diagnostics."""
    token, instance_id = _get_wapilot_settings("WhatsApp Ping")
    if not token:
        frappe.throw("wapilot_token missing in site_config.json")

    resolved_chat_id = (chat_id or "").strip()
    if not resolved_chat_id:
        normalized_mobile = clean_egypt_mobile(mobile)
        if not normalized_mobile:
            frappe.throw("Provide either chat_id or mobile")
        resolved_chat_id = f"{normalized_mobile}@c.us"

    ping_text = (text or "WhatsApp connectivity test from ERPNext").strip()
    if not ping_text:
        ping_text = "WhatsApp connectivity test from ERPNext"

    response = _send_message(resolved_chat_id, ping_text, instance_id, token)

    log_body = (
        f"Status: {response.status_code}\n"
        f"Response: {response.text}\n"
        f"Chat ID: {resolved_chat_id}"
    )

    if response.status_code >= 400:
        frappe.log_error(log_body, "WhatsApp Ping Failed")
        frappe.throw(f"WhatsApp ping failed: {response.status_code}")

    frappe.log_error(log_body, "WhatsApp Ping Sent")
    return {
        "status_code": response.status_code,
        "response": response.text,
        "chat_id": resolved_chat_id,
    }


@frappe.whitelist()
def debug_sales_order_recipient(name):
    """Return resolved recipient details for a Sales Order WhatsApp send."""
    if not name:
        frappe.throw("Sales Order name is required")

    doc = frappe.get_doc("Sales Order", name)
    contact_name, recipient_name, mobile = _get_sales_order_recipient(doc)
    normalized_mobile = clean_egypt_mobile(mobile)
    chat_id = f"{normalized_mobile}@c.us" if normalized_mobile else ""

    return {
        "sales_order": doc.name,
        "customer": doc.customer,
        "customer_name": doc.customer_name,
        "document_contact_person": getattr(doc, "contact_person", None),
        "document_contact_mobile": getattr(doc, "contact_mobile", None),
        "document_contact_phone": getattr(doc, "contact_phone", None),
        "contact_name": contact_name,
        "mobile_raw": mobile,
        "mobile_normalized": normalized_mobile,
        "chat_id": chat_id,
        "recipient_name": recipient_name,
    }


def send_sales_order_pdf(doc, method=None):
    try:
        _send_sales_order_pdf(doc, method=method)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "WhatsApp Sales Order PDF Exception")


def send_sales_invoice_pdf(doc, method=None):
    try:
        _send_sales_invoice_pdf(doc, method=method)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "WhatsApp Sales Invoice PDF Exception")


def send_payment_entry_message(doc, method=None):
    try:
        _send_payment_entry_message(doc, method=method)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "WhatsApp Payment Entry Message Exception")


def _get_wapilot_settings(log_title):
    token = frappe.conf.get("wapilot_token")
    instance_id = frappe.conf.get("wapilot_instance_id") or "4027"

    if not token:
        frappe.log_error("wapilot_token missing in site_config.json", log_title)
        return None, None

    return token, instance_id


def _send_file(chat_id, caption, filename, pdf_content, instance_id, token):
    url = f"https://api.wapilot.net/api/v2/instance{instance_id}/send-file"
    response = requests.post(
        url,
        headers={"token": token},
        data={"chat_id": chat_id, "caption": caption},
        files={"media": (filename, pdf_content, "application/pdf")},
        timeout=60,
    )
    return response


def _send_message(chat_id, text, instance_id, token):
    url = f"https://api.wapilot.net/api/v2/instance{instance_id}/send-message"
    response = requests.post(
        url,
        headers={"token": token},
        json={"chat_id": chat_id, "text": text},
        timeout=60,
    )
    return response


def _get_sales_order_recipient(doc):
    contact_name, contact_person, mobile = get_customer_contact(
        doc.customer,
        preferred_contact_name=getattr(doc, "contact_person", None),
    )
    mobile = mobile or getattr(doc, "contact_mobile", None) or getattr(doc, "contact_phone", None)
    recipient_name = get_recipient_name(contact_person, doc.customer_name, doc.customer)

    return contact_name, recipient_name, mobile


def _get_sales_order_message(doc, recipient_name):
    amount = get_doc_total_amount(doc)
    amount_display = format_doc_amount(amount, doc.currency)

    return (
        f"السيد {recipient_name}\n\n"
        f"نشكركم على طلبكم منتجاتنا بتاريخ {formatdate(doc.transaction_date, 'dd-MM-yyyy')}.\n\n"
        f"رقم أمر البيع: {doc.name}\n\n"
        f"إجمالي الطلب: {amount_display}\n\n"
        f"مع خالص التحية\n"
        f"PIT Tools"
    )


def _send_sales_order_text(doc):
    frappe.log_error(f"Triggered for Sales Order text: {doc.name}", "WhatsApp Sales Order Text Triggered")

    token, instance_id = _get_wapilot_settings("WhatsApp Sales Order Text")
    if not token:
        return

    contact_name, recipient_name, mobile = _get_sales_order_recipient(doc)

    if not mobile:
        frappe.log_error(f"No mobile found for customer {doc.customer}", "WhatsApp Sales Order Text")
        return

    whatsapp_no = clean_egypt_mobile(mobile)
    if not whatsapp_no:
        frappe.log_error(f"Invalid mobile for customer {doc.customer}: {mobile}", "WhatsApp Sales Order Text")
        return

    chat_id = f"{whatsapp_no}@c.us"
    text = _get_sales_order_message(doc, recipient_name)

    response = _send_message(chat_id, text, instance_id, token)

    if response.status_code >= 400:
        frappe.log_error(
            f"Status: {response.status_code}\nResponse: {response.text}\nChat ID: {chat_id}\nContact: {contact_name}",
            "WhatsApp Sales Order Text Failed",
        )
    else:
        frappe.log_error(
            f"Sent successfully\nResponse: {response.text}\nChat ID: {chat_id}\nContact: {contact_name}",
            "WhatsApp Sales Order Text Sent",
        )


def _send_sales_order_pdf(doc, method=None):
    frappe.log_error(f"Triggered for Sales Order: {doc.name}", "WhatsApp Sales Order PDF Triggered")

    token, instance_id = _get_wapilot_settings("WhatsApp Sales Order PDF")
    if not token:
        return

    contact_name, recipient_name, mobile = _get_sales_order_recipient(doc)

    if not mobile:
        frappe.log_error(f"No mobile found for customer {doc.customer}", "WhatsApp Sales Order PDF")
        return

    whatsapp_no = clean_egypt_mobile(mobile)
    if not whatsapp_no:
        frappe.log_error(f"Invalid mobile for customer {doc.customer}: {mobile}", "WhatsApp Sales Order PDF")
        return

    chat_id = f"{whatsapp_no}@c.us"
    caption = _get_sales_order_message(doc, recipient_name)

    html = frappe.get_print(
        doctype="Sales Order",
        name=doc.name,
        print_format=get_default_print_format("Sales Order"),
        no_letterhead=0,
    )

    pdf_content = get_pdf(html)
    filename = f"Sales Order {doc.name}.pdf"

    response = _send_file(chat_id, caption, filename, pdf_content, instance_id, token)

    if response.status_code >= 400:
        frappe.log_error(
            f"Status: {response.status_code}\nResponse: {response.text}\nChat ID: {chat_id}",
            "WhatsApp Sales Order PDF Failed",
        )
    else:
        frappe.log_error(
            f"Sent successfully\nResponse: {response.text}\nChat ID: {chat_id}",
            "WhatsApp Sales Order PDF Sent",
        )


def _send_sales_invoice_pdf(doc, method=None):
    frappe.log_error(f"Triggered for Sales Invoice: {doc.name}", "WhatsApp Sales Invoice PDF Triggered")

    token, instance_id = _get_wapilot_settings("WhatsApp Sales Invoice PDF")
    if not token:
        return

    contact_name, contact_person, mobile = get_customer_contact(
        doc.customer,
        preferred_contact_name=getattr(doc, "contact_person", None),
    )
    mobile = getattr(doc, "contact_mobile", None) or getattr(doc, "contact_phone", None) or mobile

    if not mobile:
        frappe.log_error(f"No mobile found for customer {doc.customer}", "WhatsApp Sales Invoice PDF")
        return

    whatsapp_no = clean_egypt_mobile(mobile)
    chat_id = f"{whatsapp_no}@c.us"
    amount = get_doc_total_amount(doc)
    amount_display = format_doc_amount(amount, doc.currency)

    recipient_name = get_recipient_name(contact_person, doc.customer_name, doc.customer)

    caption = (
        f"\u0627\u0644\u0633\u064a\u062f {recipient_name}\n\n"
        f"\u062a\u0645 \u0625\u0635\u062f\u0627\u0631 \u0641\u0627\u062a\u0648\u0631\u0629 \u0645\u0628\u064a\u0639\u0627\u062a \u0628\u062a\u0627\u0631\u064a\u062e {formatdate(doc.posting_date, 'dd-MM-yyyy')}.\n\n"
        f"\u0631\u0642\u0645 \u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629: {doc.name}\n\n"
        f"\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629: {amount_display}\n\n"
        f"\u0645\u0639 \u062e\u0627\u0644\u0635 \u0627\u0644\u062a\u062d\u064a\u0629\n"
        f"PIT Tools"
    )

    html = frappe.get_print(
        doctype="Sales Invoice",
        name=doc.name,
        print_format=get_default_print_format("Sales Invoice"),
        no_letterhead=0,
    )

    pdf_content = get_pdf(html)
    filename = f"Sales Invoice {doc.name}.pdf"

    response = _send_file(chat_id, caption, filename, pdf_content, instance_id, token)

    if response.status_code >= 400:
        frappe.log_error(
            f"Status: {response.status_code}\nResponse: {response.text}\nChat ID: {chat_id}",
            "WhatsApp Sales Invoice PDF Failed",
        )
    else:
        frappe.log_error(
            f"Sent successfully\nResponse: {response.text}\nChat ID: {chat_id}",
            "WhatsApp Sales Invoice PDF Sent",
        )


def _send_payment_entry_message(doc, method=None):
    frappe.log_error(f"Triggered for Payment Entry: {doc.name}", "WhatsApp Payment Entry Message Triggered")

    if doc.party_type != "Customer" or not doc.party:
        return

    token, instance_id = _get_wapilot_settings("WhatsApp Payment Entry Message")
    if not token:
        return

    contact_name, contact_person, mobile = get_customer_contact(doc.party)

    if not mobile:
        frappe.log_error(f"No mobile found for customer {doc.party}", "WhatsApp Payment Entry Message")
        return

    from erpnext.accounts.utils import get_balance_on

    customer_name = frappe.db.get_value("Customer", doc.party, "customer_name") or doc.party
    recipient_name = get_recipient_name(contact_person, customer_name, doc.party)
    paid_amount = doc.paid_amount or doc.received_amount or 0
    balance = get_balance_on(
        party_type="Customer",
        party=doc.party,
        date=doc.posting_date,
        company=doc.company,
    )

    whatsapp_no = clean_egypt_mobile(mobile)
    chat_id = f"{whatsapp_no}@c.us"

    text = (
        f"\u0627\u0644\u0633\u064a\u062f / {recipient_name}\n\n"
        f"\u0646\u0634\u0643\u0631\u0643\u0645 \u0639\u0644\u0649 \u0633\u062f\u0627\u062f \u0645\u0628\u0644\u063a {paid_amount} {doc.paid_from_account_currency or doc.paid_to_account_currency} "
        f"\u0628\u062a\u0627\u0631\u064a\u062e {formatdate(doc.posting_date, 'dd-MM-yyyy')}.\n\n"
        f"\u064a\u0631\u062c\u0649 \u0627\u0644\u0639\u0644\u0645 \u0623\u0646 \u0627\u0644\u0631\u0635\u064a\u062f \u0627\u0644\u0645\u062a\u0628\u0642\u064a \u0639\u0644\u064a\u0643\u0645 \u062d\u062a\u0649 \u062a\u0627\u0631\u064a\u062e\u0647 \u0647\u0648 {balance} {doc.paid_from_account_currency or doc.paid_to_account_currency}.\n\n"
        f"\u0645\u0639 \u062e\u0627\u0644\u0635 \u0627\u0644\u062a\u062d\u064a\u0629\n"
        f"PIT Tools"
    )

    response = _send_message(chat_id, text, instance_id, token)

    if response.status_code >= 400:
        frappe.log_error(
            f"Status: {response.status_code}\nResponse: {response.text}\nChat ID: {chat_id}",
            "WhatsApp Payment Entry Message Failed",
        )
    else:
        frappe.log_error(
            f"Sent successfully\nResponse: {response.text}\nChat ID: {chat_id}",
            "WhatsApp Payment Entry Message Sent",
        )
