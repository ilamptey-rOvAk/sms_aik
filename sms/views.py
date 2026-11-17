
import json
import logging
import requests

from datetime import datetime, timezone as dt_timezone, timedelta

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import SentMessages, DeliveryReport
from .nalo import send_sms


logger = logging.getLogger(__name__)


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
                status_code, result = send_sms(
                    phone_number,
                    message,
                    sender_id
                )

                nalo_status = ""

                if isinstance(result, dict):
                    nalo_status = str(result.get("status", ""))

                if status_code == 200 and nalo_status == "1701":
                    api_status = "Accepted"
                    delivery_status = "Pending"

                    job_id = (
                        result.get("job_id", "")
                        if isinstance(result, dict)
                        else ""
                    )

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

                logger.exception("Unable to connect to Nalo SMS API")

                SentMessages.objects.create(
                    sender_id=sender_id,
                    phone_numbers=phone_number,
                    message=message,
                    api_status="Failed",
                    delivery_status="Failed",
                    api_response="Unable to connect to Nalo"
                )

                feedback = "Unable to connect to Nalo. Please try again."

    return render(request, "sms/home.html", {
        "sender_ids": settings.SENDER_IDS,
        "feedback": feedback
    })


def message_history(request):

    messages = SentMessages.objects.all().order_by("-created_at")

    return render(request, "sms/history.html", {
        "messages": messages
    })


@csrf_exempt
def nalo_callback(request):

    if request.method not in ["POST", "GET"]:
        return HttpResponse("Method not allowed", status=405)

    data = {}

    # Read incoming callback information
    if request.method == "POST":

        content_type = request.content_type or ""

        if "application/json" in content_type:

            try:
                data = json.loads(request.body.decode("utf-8"))

            except (json.JSONDecodeError, UnicodeDecodeError):

                logger.warning("Nalo callback contained invalid JSON")

                return HttpResponse("Invalid JSON", status=400)

        else:
            data = request.POST.dict()

    else:
        data = request.GET.dict()

    # Handle different JSON structures
    if isinstance(data, list):

        logger.info(
            "Nalo callback received a JSON list containing %s item(s)",
            len(data)
        )

        if len(data) == 1 and isinstance(data[0], dict):
            data = data[0]

        else:
            logger.warning(
                "Nalo callback JSON list could not be processed automatically"
            )

            return HttpResponse("Unsupported callback format", status=400)

    elif not isinstance(data, dict):

        logger.warning(
            "Nalo callback invalid data type: %s",
            type(data).__name__
        )

        logger.warning(
            "Nalo callback content type: %s",
            request.content_type
        )

        return HttpResponse("Invalid callback data", status=400)

    logger.info(
        "Nalo callback received: method=%s, content_type=%s, fields=%s",
        request.method,
        request.content_type,
        list(data.keys())
    )

    # Extract callback information
    mid = str(data.get("mid", "")).strip()
    msisdn = str(data.get("msisdn", "")).strip()
    status = str(data.get("status", "")).strip()

    # Check required fields
    if not mid or not msisdn or not status:

        logger.warning(
            "Nalo callback missing fields: mid=%s, msisdn=%s, status=%s",
            bool(mid),
            bool(msisdn),
            bool(status)
        )

        return HttpResponse("Missing callback information", status=400)

    # Extract timestamp from message ID
    try:

        mid_parts = mid.split(".")

        if len(mid_parts) < 4:
            raise ValueError("Invalid message ID structure")

        callback_timestamp = int(mid_parts[3])

        callback_time = datetime.fromtimestamp(
            callback_timestamp,
            tz=dt_timezone.utc
        )

    except (ValueError, IndexError, TypeError, OverflowError):

        logger.warning("Invalid Nalo message ID format")

        return HttpResponse("Invalid message ID", status=400)

    # Search for the original SMS submission
    start_time = callback_time - timedelta(seconds=2)
    end_time = callback_time + timedelta(seconds=60)

    messages = SentMessages.objects.filter(
        created_at__gte=start_time,
        created_at__lte=end_time
    )

    matching_messages = []

    for message_record in messages:

        recipients = [
            number.strip()
            for number in message_record.phone_numbers.split(",")
        ]

        if msisdn in recipients:
            matching_messages.append(message_record)

    if len(matching_messages) == 0:

        logger.warning("No matching SMS record found for delivery callback")

        return HttpResponse("Message not found", status=404)

    if len(matching_messages) > 1:

        logger.warning("Multiple SMS records matched delivery callback")

        return HttpResponse("Multiple matching messages", status=409)

    message_record = matching_messages[0]

    # Save delivery report
    DeliveryReport.objects.update_or_create(
        sent_message=message_record,
        msisdn=msisdn,
        defaults={
            "status": status
        }
    )

    # Check delivery status for all recipients
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

        if all(
            reports[number] == "DELIVRD"
            for number in recipients
        ):
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

    logger.info(
        "Delivery report successfully saved for SMS record %s",
        message_record.id
    )

    return HttpResponse("Delivery report received", status=200)
