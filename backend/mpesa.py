import base64
import requests
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


class MpesaService:
    """
    M-Pesa Daraja API service.

    Credentials come from settings (set via UI) or .env fallback.
    Each transaction:
      1. Get OAuth access token
      2. Build STK push payload
      3. POST to Safaricom
      4. Return response (Safaricom calls our callback separately)
    """

    def __init__(self):
        self.consumer_key = os.getenv("MPESA_CONSUMER_KEY", "")
        self.consumer_secret = os.getenv("MPESA_CONSUMER_SECRET", "")
        self.passkey = os.getenv("MPESA_PASSKEY", "")
        self.shortcode = os.getenv("MPESA_SHORTCODE", "174379")
        self.base_url = os.getenv("MPESA_BASE_URL", "https://sandbox.safaricom.co.ke")
        self.callback_url = os.getenv(
            "MPESA_CALLBACK_URL",
            "https://your-domain.com/api/v1/mpesa/callback",
        )
        self.access_token = None

    def get_access_token(self):
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        response = requests.get(
            url,
            auth=(self.consumer_key, self.consumer_secret),
            timeout=15,
        )
        if response.status_code == 200:
            self.access_token = response.json()["access_token"]
            return self.access_token
        raise Exception(f"Failed to get M-Pesa token: {response.text}")

    def stk_push(self, phone_number, amount, receipt_no):
        if not self.access_token:
            self.get_access_token()

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password_str = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(password_str.encode()).decode()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(round(amount)),
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": receipt_no,
            "TransactionDesc": "Safari POS Pro payment",
        }

        response = requests.post(
            f"{self.base_url}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers,
            timeout=20,
        )
        return response.json()
