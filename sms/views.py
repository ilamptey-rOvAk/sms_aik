from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.conf import settings
from .nalo import send_sms
import requests
from .models import SentMessages, DeliveryReport
import json
from django.utils import timezone
from datetime import datetime, timezone as dt_timezone, timedelta
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
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.POST.dict()
    else:
        data = request.GET.dict()

    if not isinstance(data, dict):
        return HttpResponse("Invalid callback data", status=400)

    mid = data.get("mid", "")
    msisdn = str(data.get("msisdn", "")).strip()
    status = str(data.get("status", "")).strip()

    if not mid or not msisdn or not status:
        return HttpResponse("Missing callback information", status=400)

    try:
        mid_parts = mid.split(".")
        callback_timestamp = int(mid_parts[3])

        callback_time = datetime.fromtimestamp(
            callback_timestamp,
            tz=dt_timezone.utc
        )
    except (ValueError, IndexError, TypeError):
        return HttpResponse("Invalid message ID", status=400)

    start_time = callback_time - timedelta(seconds=2)
    end_time = callback_time + timedelta(seconds=60)

    matching_messages = []

    messages = SentMessages.objects.filter(
        created_at__gte=start_time,
        created_at__lte=end_time
    )

    for message in messages:
        recipients = [
            number.strip()
            for number in message.phone_numbers.split(",")
        ]

        if msisdn in recipients:
            matching_messages.append(message)

    if len(matching_messages) == 0:
        return HttpResponse("Message not found", status=404)

    if len(matching_messages) > 1:
        return HttpResponse("Multiple matching messages", status=409)

    message_record = matching_messages[0]

    DeliveryReport.objects.update_or_create(
        sent_message=message_record,
        msisdn=msisdn,
        defaults={
            "status": status
        }
    )

    recipients = [
        number.strip()
        for number in message_record.phone_numbers.split(",")
    ]

    reports = {
        report.msisdn: report.status
        for report in DeliveryReport.objects.filter(
            sent_message=message_record
        )
    }

    if all(number in reports for number in recipients):
        if all(reports[number] == "DELIVRD" for number in recipients):
            message_record.delivery_status = "DELIVRD"
        else:
            message_record.delivery_status = "Delivery issues"
    else:
        message_record.delivery_status = "Pending"

    message_record.delivery_time = timezone.now()

    message_record.save(update_fields=[
        "delivery_status",
        "delivery_time"
    ])

    return HttpResponse("Delivery report received", status=200)