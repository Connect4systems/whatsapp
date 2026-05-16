import frappe
import requests
import re
from frappe.utils import formatdate
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


def get_customer_contact(customer):
    contact_name = frappe.db.get_value(
        "Dynamic Link",
        {
            "link_doctype": "Customer",
            "link_name": customer,
            "parenttype": "Contact",
        },
        "parent",
    )

    if not contact_name:
        return None, None, None

    contact = frappe.get_doc("Contact", contact_name)
    mobile = contact.mobile_no or contact.phone or ""
    contact_person = contact.first_name or contact.full_name or ""

    return contact_name, contact_person, mobile


def get_default_print_format(doctype):
    return frappe.get_meta(doctype).default_print_format or "Standard"


@frappe.whitelist()
def send_sales_order_pdf_now(name):
    if not name:
        frappe.throw("Sales Order name is required")

    doc = frappe.get_doc("Sales Order", name)
    send_sales_order_pdf(doc)
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


def _send_sales_order_pdf(doc, method=None):
    frappe.log_error(f"Triggered for Sales Order: {doc.name}", "WhatsApp Sales Order PDF Triggered")

    token, instance_id = _get_wapilot_settings("WhatsApp Sales Order PDF")
    if not token:
        return

    contact_name, contact_person, mobile = get_customer_contact(doc.customer)

    if not mobile:
        frappe.log_error(f"No mobile found for customer {doc.customer}", "WhatsApp Sales Order PDF")
        return

    whatsapp_no = clean_egypt_mobile(mobile)
    chat_id = f"{whatsapp_no}@c.us"

    caption = (
        f"Ø§Ù„Ø³ÙŠØ¯ {contact_person or doc.customer_name or doc.customer}\n\n"
        f"Ù†Ø´ÙƒØ±ÙƒÙ… Ø¹Ù„Ù‰ Ø·Ù„Ø¨ÙƒÙ… Ù…Ù†ØªØ¬Ø§ØªÙ†Ø§ Ø¨ØªØ§Ø±ÙŠØ® {formatdate(doc.transaction_date, 'dd-MM-yyyy')}.\n\n"
        f"Ø±Ù‚Ù… Ø£Ù…Ø± Ø§Ù„Ø¨ÙŠØ¹: {doc.name}\n\n"
        f"Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ø·Ù„Ø¨: {doc.grand_total} {doc.currency}\n\n"
        f"Ù…Ø¹ Ø®Ø§Ù„Øµ Ø§Ù„ØªØ­ÙŠØ©\n"
        f"PIT Tools"
    )

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

    contact_name, contact_person, mobile = get_customer_contact(doc.customer)

    if not mobile:
        frappe.log_error(f"No mobile found for customer {doc.customer}", "WhatsApp Sales Invoice PDF")
        return

    whatsapp_no = clean_egypt_mobile(mobile)
    chat_id = f"{whatsapp_no}@c.us"

    caption = (
        f"Ø§Ù„Ø³ÙŠØ¯ {contact_person or doc.customer_name or doc.customer}\n\n"
        f"ØªÙ… Ø¥ØµØ¯Ø§Ø± ÙØ§ØªÙˆØ±Ø© Ù…Ø¨ÙŠØ¹Ø§Øª Ø¨ØªØ§Ø±ÙŠØ® {formatdate(doc.posting_date, 'dd-MM-yyyy')}.\n\n"
        f"Ø±Ù‚Ù… Ø§Ù„ÙØ§ØªÙˆØ±Ø©: {doc.name}\n\n"
        f"Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„ÙØ§ØªÙˆØ±Ø©: {doc.grand_total} {doc.currency}\n\n"
        f"Ù…Ø¹ Ø®Ø§Ù„Øµ Ø§Ù„ØªØ­ÙŠØ©\n"
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
        f"Ø§Ù„Ø³ÙŠØ¯ / {contact_person or customer_name or doc.party}\n\n"
        f"Ù†Ø´ÙƒØ±ÙƒÙ… Ø¹Ù„Ù‰ Ø³Ø¯Ø§Ø¯ Ù…Ø¨Ù„Øº {paid_amount} {doc.paid_from_account_currency or doc.paid_to_account_currency} "
        f"Ø¨ØªØ§Ø±ÙŠØ® {formatdate(doc.posting_date, 'dd-MM-yyyy')}.\n\n"
        f"ÙŠØ±Ø¬Ù‰ Ø§Ù„Ø¹Ù„Ù… Ø£Ù† Ø§Ù„Ø±ØµÙŠØ¯ Ø§Ù„Ù…ØªØ¨Ù‚ÙŠ Ø¹Ù„ÙŠÙƒÙ… Ø­ØªÙ‰ ØªØ§Ø±ÙŠØ®Ù‡ Ù‡Ùˆ {balance} {doc.paid_from_account_currency or doc.paid_to_account_currency}.\n\n"
        f"Ù…Ø¹ Ø®Ø§Ù„Øµ Ø§Ù„ØªØ­ÙŠØ©\n"
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
