# WhatsApp

WhatsApp automation app for Frappe and ERPNext v15.

## Features

- Sends Sales Invoice PDFs to the customer's WhatsApp number on submit.
- Sends Payment Entry confirmation messages to the customer's WhatsApp number on submit.
- Uses customer Contact mobile/phone values and normalizes Egyptian mobile numbers.
- Uses WAPilot credentials from `site_config.json`.
- Adds a reusable website floating WhatsApp button.

## Required Site Config

Add these keys to your site config:

```json
{
  "wapilot_token": "your-token",
  "wapilot_instance_id": "4027"
}
```

`wapilot_instance_id` defaults to `4027` if omitted.

The website floating button defaults to `201006676145`. You can override it before the website script runs:

```html
<script>
  window.whatsappNumber = "201234567890";
</script>
```

## Install

```bash
cd ~/frappe-bench
bench get-app /path/to/whatsapp
bench --site <site-name> install-app whatsapp
bench --site <site-name> migrate
bench restart
```

For local development from this folder:

```bash
cd ~/frappe-bench
bench get-app D:/2026/Apps/whatsapp
bench --site <site-name> install-app whatsapp
```
