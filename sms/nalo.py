
import requests
from django.conf import settings


def send_sms(phone_number, message, sender_id):

    url = "https://sms.nalosolutions.com/smsbackend/clientapi/Resl_Nalo/send-message/"

    callback_url = settings.CALLBACK_BASE_URL.rstrip("/") + "/callback/"

    data = {
        "key": settings.SMS_API_KEY,
        "type": "0",
        "destination": phone_number,
        "dlr": "1",
        "source": sender_id,
        "message": message,
        "callback_url": callback_url
    }

    response = requests.get(url, params=data, timeout=30)

    try:
        result = response.json()
    except ValueError:
        parts = response.text.strip().split("|")

        if len(parts) >= 3:
            result = {
                "status": parts[0],
                "msisdn": parts[1],
                "job_id": parts[2]
            }
        else:
            result = response.text

    return response.status_code, result
