from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, DB_PATH
from auth import get_current_user
from mpesa import MpesaService
from pydantic import BaseModel
import sqlite3

router = APIRouter()
mpesa_service = MpesaService()


def get_mpesa_setting(key):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
    return result[0] if result else None


class STKPushRequest(BaseModel):
    phone_number: str
    amount: float
    receipt_no: str


@router.post("/stk-push")
async def stk_push(
    request: STKPushRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Send an STK push to the customer's phone.
    Also saves CheckoutRequestID against the pending sale for later matching.
    If mpesa_mock_mode is on, simulates a successful callback after 5 seconds.
    """
    enabled = get_mpesa_setting("mpesa_enabled")
    if enabled != "true":
        raise HTTPException(
            status_code=400,
            detail="M-Pesa is not enabled. Contact admin.",
        )

    # Find the pending sale by receipt_no
    from models import Sale
    sale = db.query(Sale).filter(Sale.receipt_no == request.receipt_no).first()
    if not sale:
        raise HTTPException(status_code=404, detail=f"Pending sale {request.receipt_no} not found")

    # Check mock mode
    mock_mode = get_mpesa_setting("mpesa_mock_mode") == "true"

    if mock_mode:
        # Save a fake CheckoutRequestID and generate a mock callback
        mock_checkout_id = f"ws_CO_MOCK_{int(__import__('time').time())}"
        sale.mpesa_checkout_id = mock_checkout_id
        db.commit()

        # Fire a mock callback to the Cloudflare relay after 5 seconds
        try:
            import threading
            import requests
            shop_id = get_mpesa_setting("mpesa_shop_id") or "testshop"

            def _deliver_mock():
                __import__('time').sleep(5)
                mock_payload = {
                    "Body": {
                        "stkCallback": {
                            "MerchantRequestID": "mock-merchant-" + mock_checkout_id,
                            "CheckoutRequestID": mock_checkout_id,
                            "ResultCode": 0,
                            "ResultDesc": "The service request is processed successfully.",
                            "CallbackMetadata": {
                                "Item": [
                                    {"Name": "Amount", "Value": int(request.amount)},
                                    {"Name": "MpesaReceiptNumber", "Value": "MOCK" + str(int(__import__('time').time()))},
                                    {"Name": "TransactionDate", "Value": int(__import__('time').time())},
                                    {"Name": "PhoneNumber", "Value": request.phone_number},
                                ]
                            }
                        }
                    }
                }
                try:
                    requests.post(
                        f"https://relay.safari-pos.co.ke/callback/{shop_id}",
                        json=mock_payload,
                        timeout=10,
                    )
                    print(f"[mpesa-mock] Sent mock callback for sale {sale.id}")
                except Exception as e:
                    print(f"[mpesa-mock] Failed to send: {e}")

            threading.Thread(target=_deliver_mock, daemon=True).start()
        except Exception as e:
            print(f"[mpesa-mock] Setup error: {e}")

        return {
            "status": "success",
            "message": "MOCK: STK push simulated. Callback will arrive in ~5s.",
            "data": {"CheckoutRequestID": mock_checkout_id, "mock": True},
        }

    # Real M-Pesa flow
    consumer_key = get_mpesa_setting("mpesa_consumer_key")
    consumer_secret = get_mpesa_setting("mpesa_consumer_secret")
    passkey = get_mpesa_setting("mpesa_passkey")
    shortcode = get_mpesa_setting("mpesa_shortcode")

    if not all([consumer_key, consumer_secret, passkey, shortcode]):
        raise HTTPException(
            status_code=400,
            detail="M-Pesa credentials not configured. Contact admin.",
        )

    mpesa_service.consumer_key = consumer_key
    mpesa_service.consumer_secret = consumer_secret
    mpesa_service.passkey = passkey
    mpesa_service.shortcode = shortcode
    mpesa_service.access_token = None

    try:
        response = mpesa_service.stk_push(
            request.phone_number,
            request.amount,
            request.receipt_no,
        )

        # Save CheckoutRequestID on the pending sale
        checkout_id = response.get("CheckoutRequestID")
        if checkout_id:
            sale.mpesa_checkout_id = checkout_id
            db.commit()
            print(f"[mpesa] Saved CheckoutID={checkout_id} to sale {sale.id}")

        return {
            "status": "success",
            "message": "STK push sent to customer phone",
            "data": response,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"M-Pesa error: {e}")


@router.post("/callback")
async def mpesa_callback(request: dict):
    """
    Safaricom calls this endpoint after the customer pays (or cancels).

    ResultCode 0 = success, anything else = failed.
    We always respond 200 so Safaricom doesn't retry.
    """
    body = request.get("Body", {})
    stk = body.get("stkCallback", {})
    result_code = stk.get("ResultCode")

    if result_code == 0:
        # Payment successful — could log to a table here in future
        return {"ResultCode": 0, "ResultDesc": "Success"}

    return {"ResultCode": 0, "ResultDesc": "Failed"}
