
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import parse_qs

import requests

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import SentMessages, DeliveryReport
from .nalo import send_sms


logger = logging.getLogger(__name__)


def home(request):
    sender_ids = settings.SENDER_IDS

    if request.method != "POST":
        return render(request, "sms/home.html", {
            "sender_ids": sender_ids
        })

    phone_numbers = request.POST.get("phone_number", "").strip()
    sender_id = request.POST.get("sender_id", "").strip()
    message = request.POST.get("message", "").strip()

    if not phone_numbers or not sender_id or not message:
        return render(request, "sms/home.html", {
            "error": "Please fill in all fields.",
            "sender_ids": sender_ids
        })

    numbers = list(dict.fromkeys(
        number.strip()
        for number in phone_numbers.split(",")
        if number.strip()
    ))

    if not numbers:
        return render(request, "sms/home.html", {
            "error": "Please enter at least one phone number.",
            "sender_ids": sender_ids
        })

    for number in numbers:
        if not number.isdigit() or not 10 <= len(number) <= 15:
            return render(request, "sms/home.html", {
                "error": f"Invalid phone number: {number}",
                "sender_ids": sender_ids
            })

    if sender_id not in sender_ids:
        return render(request, "sms/home.html", {
            "error": "Please select a valid Sender ID.",
            "sender_ids": sender_ids
        })

    results = []
    all_accepted = True

    try:
        for number in numbers:
            status_code, result = send_sms(
                number,
                message,
                sender_id
            )

            if isinstance(result, dict):
                result_data = result
            else:
                result_data = {"response": str(result)}

            accepted = (
                status_code == 200
                and str(result_data.get("status", "")) == "1701"
            )

            result_data["phone_number"] = number
            result_data["http_status"] = status_code
            result_data["accepted"] = accepted

            results.append(result_data)

            if not accepted:
                all_accepted = False

        successful_job_ids = [
            str(result.get("job_id"))
            for result in results
            if result.get("job_id") and result.get("accepted")
        ]

        api_status = "Accepted" if all_accepted else "Failed"

        SentMessages.objects.create(
            sender_id=sender_id,
            phone_numbers=",".join(numbers),
            message=message,
            job_id=",".join(successful_job_ids) or None,
            api_status=api_status,
            delivery_status="Pending" if all_accepted else "Failed",
            api_response=json.dumps(results)
        )

        if all_accepted:
            return render(request, "sms/home.html", {
                "success": "SMS submitted successfully.",
                "sender_ids": sender_ids
            })

        return render(request, "sms/home.html", {
            "error": "Some or all SMS messages could not be submitted.",
            "api_response": json.dumps(results, indent=2),
            "sender_ids": sender_ids
        })

    except requests.exceptions.RequestException:
        logger.exception("Error connecting to Nalo SMS API")

        SentMessages.objects.create(
            sender_id=sender_id,
            phone_numbers=",".join(numbers),
            message=message,
            api_status="Failed",
            delivery_status="Failed",
            api_response="Connection error while contacting Nalo."
        )

        return render(request, "sms/home.html", {
            "error": "Could not connect to the SMS service. Please try again.",
            "sender_ids": sender_ids
        })


def message_history(request):
    messages = SentMessages.objects.all().order_by("-created_at")

    return render(request, "sms/history.html", {
        "messages": messages
    })


def normalize_phone_number(number):
    """
    Remove spaces and common phone-number formatting characters.
    """

    return "".join(
        character
        for character in str(number)
        if character.isdigit()
    )


def parse_callback_data(request):
    """
    Convert Nalo callback data into a dictionary.

    Supports:
    - GET query parameters
    - Normal POST form data
    - JSON objects
    - JSON strings containing another JSON object
    - URL-encoded strings inside JSON
    """

    if request.method == "GET":
        return request.GET.dict()

    content_type = (request.content_type or "").lower()

    if "application/json" in content_type:
        try:
            data = json.loads(request.body.decode("utf-8"))

        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Nalo sent invalid JSON")
            return None

        # Handle JSON containing another JSON string.
        if isinstance(data, str):
            try:
                data = json.loads(data)

            except json.JSONDecodeError:
                # Check whether the string contains URL-encoded fields.
                parsed = parse_qs(data)

                if parsed:
                    data = {
                        key: values[0]
                        for key, values in parsed.items()
                    }

        # Handle a list containing one callback dictionary.
        if isinstance(data, list) and len(data) == 1:
            data = data[0]

        return data

    return request.POST.dict()


def get_callback_timestamp(mid):
    """
    Extract the timestamp from the fourth section of the message ID.

    IMPORTANT:
    This follows the format assumed by the previous implementation.
    It must be verified against an actual Nalo callback.
    """

    parts = str(mid).split(".")

    if len(parts) < 4:
        raise ValueError("Unexpected Nalo message ID format")

    timestamp = int(parts[3])

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.get_current_timezone()
    )


@csrf_exempt
def nalo_callback(request):
    """
    Receive Nalo delivery reports and update SMS delivery statuses.
    """

    if request.method not in ["POST", "GET"]:
        return HttpResponse("Method not allowed", status=405)

    data = parse_callback_data(request)

    # Temporary diagnostics to help identify Nalo's actual payload.
    logger.warning(
        "NALO CALLBACK DEBUG: content_type=%s, body_length=%s, parsed_type=%s",
        request.content_type,
        len(request.body),
        type(data).__name__
    )

    if isinstance(data, str):
        logger.warning(
            "NALO CALLBACK STRING SAMPLE: %s",
            data[:500]
        )

    elif isinstance(data, dict):
        logger.warning(
            "NALO CALLBACK FIELD NAMES: %s",
            list(data.keys())
        )

    if not isinstance(data, dict):
        logger.warning(
            "Nalo callback invalid data type: %s",
            type(data).__name__
        )
        return HttpResponse("Invalid callback data", status=400)

    mid = data.get("mid")
    msisdn = data.get("msisdn")
    status = data.get("status")

    if not mid or not msisdn or not status:
        logger.warning(
            "Nalo callback missing required fields: %s",
            list(data.keys())
        )
        return HttpResponse("Missing callback fields", status=400)

    mid = str(mid).strip()
    msisdn = normalize_phone_number(msisdn)
    status = str(status).strip().upper()

    if not msisdn:
        return HttpResponse("Invalid recipient number", status=400)

    try:
        callback_time = get_callback_timestamp(mid)

    except (ValueError, TypeError, OverflowError):
        logger.exception(
            "Could not extract timestamp from Nalo message ID"
        )
        return HttpResponse("Invalid message ID or timestamp", status=400)

    start_time = callback_time - timedelta(seconds=2)
    end_time = callback_time + timedelta(seconds=60)

    try:
        possible_messages = SentMessages.objects.filter(
            created_at__range=(start_time, end_time),
            api_status="Accepted"
        )

        matching_messages = []

        for sent_message in possible_messages:
            saved_numbers = [
                normalize_phone_number(number)
                for number in sent_message.phone_numbers.split(",")
            ]

            if msisdn in saved_numbers:
                matching_messages.append(sent_message)

        if not matching_messages:
            logger.warning(
                "No matching SMS record found for callback recipient"
            )
            return HttpResponse("SMS record not found", status=404)

        if len(matching_messages) > 1:
            logger.warning(
                "Multiple SMS records matched the callback"
            )
            return HttpResponse("Multiple matching records", status=409)

        sent_message = matching_messages[0]

        with transaction.atomic():
            DeliveryReport.objects.update_or_create(
                sent_message=sent_message,
                msisdn=msisdn,
                defaults={
                    "status": status
                }
            )

            expected_numbers = {
                normalize_phone_number(number)
                for number in sent_message.phone_numbers.split(",")
                if number.strip()
            }

            reports = list(
                sent_message.delivery_reports.all()
            )

            received_numbers = {
                normalize_phone_number(report.msisdn)
                for report in reports
            }

            if expected_numbers.issubset(received_numbers):

                if all(
                    report.status == "DELIVRD"
                    for report in reports
                ):
                    sent_message.delivery_status = "DELIVRD"

                else:
                    sent_message.delivery_status = "Delivery issues"

                sent_message.delivery_time = timezone.now()

                sent_message.save(
                    update_fields=[
                        "delivery_status",
                        "delivery_time"
                    ]
                )

            else:
                sent_message.delivery_status = "Pending"

                sent_message.save(
                    update_fields=["delivery_status"]
                )

        logger.info(
            "Nalo delivery report processed successfully"
        )

        return HttpResponse(
            "Delivery report received",
            status=200
        )

    except Exception:
        logger.exception(
            "Error processing Nalo delivery report"
        )

        return HttpResponse(
            "Could not process delivery report",
            status=500
        )
