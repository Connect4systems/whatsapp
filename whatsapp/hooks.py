app_name = "whatsapp"
app_title = "WhatsApp"
app_publisher = "Connect4systems"
app_description = "WhatsApp automation for Frappe and ERPNext"
app_email = "info@connect4systems.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

web_include_css = ["/assets/whatsapp/css/whatsapp.css"]
web_include_js = ["/assets/whatsapp/js/website_whatsapp.js"]

doc_events = {
    "Sales Invoice": {
        "on_submit": "whatsapp.whatsapp_sales_order.send_sales_invoice_pdf",
    },
    "Payment Entry": {
        "on_submit": "whatsapp.whatsapp_sales_order.send_payment_entry_message",
    },
}
