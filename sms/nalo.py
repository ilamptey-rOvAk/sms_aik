
import requests
from django.conf import settings


def send_sms(phone_number, message, sender_id):

    url = "https://sms.nalosolutions.com/smsbackend/Resl_Nalo/send-message/"

    callback_url = settings.CALLBACK_BASE_URL.rstrip("/") + "/callback/"

    data = {
        "key": settings.SMS_API_KEY,
        "msisdn": phone_number,
        "message": message,
        "sender_id": sender_id,
        "callback_url": callback_url
    }

    response = requests.post(url, json=data, timeout=30)

    try:
        result = response.json()
    except ValueError:
        result = response.text

    return response.status_code, result

 