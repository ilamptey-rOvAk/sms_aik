from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.conf import settings
from .nalo import send_sms
import requests
from .models import SentMessages, DeliveryReport
import json
from django.utils import timezone

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

    if request.method not in ["POST", "GET"]:
        return HttpResponse("Method not allowed", status=405)

    if request.method == "POST":
        data = request.POST.dict()

        if not data:
            try:
                data = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = {}
    else:
        data = request.GET.dict()

    job_id = data.get("job_id")
    msisdn = data.get("msisdn")
    status = data.get("status")

    if not job_id or not msisdn or not status:
        return HttpResponse("Missing callback information", status=400)

    message_record = SentMessages.objects.filter(
        job_id=job_id
    ).first()

    if not message_record:
        return HttpResponse("Message not found", status=404)

    phone_numbers = [
        number.strip()
        for number in message_record.phone_numbers.split(",")
    ]

    if msisdn.strip() not in phone_numbers:
        return HttpResponse("Recipient not found", status=404)

    DeliveryReport.objects.update_or_create(
        sent_message=message_record,
        msisdn=msisdn.strip(),
        defaults={
            "status": str(status)
        }
    )

    message_record.delivery_time = timezone.now()

    if len(phone_numbers) == 1:
        message_record.delivery_status = str(status)

    message_record.save(update_fields=[
        "delivery_status",
        "delivery_time"
    ])

    return HttpResponse("Delivery report received", status=200)