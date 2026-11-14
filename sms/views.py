from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.conf import settings
from .nalo import send_sms
import requests
from .models import SentMessages


def home(request):

    feedback = ""

    if request.method == "POST":

        phone_number = request.POST.get("phone_number", "").strip()
        sender_id = request.POST.get("sender_id", "").strip()
        message = request.POST.get("message", "").strip()

        if not phone_number or not sender_id or not message:
            feedback = "Please fill in all the fields."

        elif not all(
            number.strip().isdigit() and 10 <= len(number.strip()) <= 15
            for number in phone_number.split(",")
        ):
            feedback = "Please enter valid phone numbers."

        else:
            try:
                status_code, result = send_sms(phone_number, message, sender_id)

                nalo_status = ""

                if isinstance(result, dict):
                    nalo_status = str(result.get("status", ""))

                if status_code == 200 and nalo_status == "1701":
                    api_status = "Accepted"
                    delivery_status = "Pending"
                    job_id = result.get("job_id", "") if isinstance(result, dict) else ""
                else:
                    api_status = "Failed"
                    delivery_status = "Failed"
                    job_id = ""

                SentMessages.objects.create(
                    sender_id=sender_id,
                    phone_numbers=phone_number,
                    message=message,
                    job_id=job_id,
                    api_status=api_status,
                    delivery_status=delivery_status,
                    api_response=str(result)
                )

                feedback = f"Nalo response ({status_code}): {result}"

            except requests.exceptions.RequestException:
                SentMessages.objects.create(
                    sender_id=sender_id,
                    phone_numbers=phone_number,
                    message=message,
                    api_status="Failed",
                    delivery_status="Failed",
                    api_response="Unable to connect to Nalo"
                )

                feedback = "Unable to connect to Nalo. Please try again."

    return render(request, 'sms/home.html', {
        'sender_ids': settings.SENDER_IDS,
        'feedback': feedback
    })


def message_history(request):
    messages = SentMessages.objects.all().order_by('-created_at')

    return render(request, 'sms/history.html', {
        'messages': messages
    })

@csrf_exempt
def nalo_callback(request):
    return HttpResponse("Nalo callback endpoint is active", status=200)
