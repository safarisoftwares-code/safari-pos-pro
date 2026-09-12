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
    enabled = get_mpesa_setting("mpesa_enabled")
    if enabled != "true":
        raise HTTPException(
            status_code=400,
            detail="M-Pesa is not enabled. Contact admin.",
        )

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
    mpesa_service.access_token = None  # force refresh

    try:
        response = mpesa_service.stk_push(
            request.phone_number,
            request.amount,
            request.receipt_no,
        )
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
