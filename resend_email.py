import requests

requests.post(
  "https://api.resend.com/emails",
  headers={"Authorization": "Bearer re_4D1whQVU_7piPzrXA4qkj4MnEdewGFfhB"},
  json={
    "from": "noreply@renewtech.com.tw",
    "to": "lawrencelin2011@gmail.com",
    "subject": "Hello",
    "html": "<p>Test</p>"
  }
)