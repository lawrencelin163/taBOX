import requests

from tabox_config import load_config


RESEND_CONFIG = load_config()["resend"]
RESEND_DEFAULTS = RESEND_CONFIG["defaults"]


def send_resend_email(
  subject: str | None = None,
  html: str | None = None,
  to: str | None = None,
  from_email: str | None = None,
) -> requests.Response:
  payload = {
    "from": from_email or RESEND_DEFAULTS["from"],
    "to": to or RESEND_DEFAULTS["to"],
    "subject": subject or RESEND_DEFAULTS["subject"],
    "html": html or RESEND_DEFAULTS["html"],
  }
  headers = {"Authorization": f"Bearer {RESEND_CONFIG['auth']['api_key']}"}
  return requests.post(
    RESEND_CONFIG["base_url"],
    headers=headers,
    json=payload,
    timeout=int(RESEND_CONFIG["requests"]["timeout_seconds"]),
  )


if __name__ == "__main__":
  response = send_resend_email()
  print(response.status_code)
  print(response.text)