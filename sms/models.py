from django.db import models


class SentMessages(models.Model):
    sender_id = models.CharField(max_length=25)
    phone_numbers = models.TextField()
    message = models.TextField()
    job_id = models.CharField(max_length=100, blank=True, null=True)
    api_status = models.CharField(max_length=50, default='Pending')
    delivery_status = models.CharField(max_length=50, default='Pending')
    api_response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivery_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.sender_id} - {self.created_at}"


class DeliveryReport(models.Model):
    sent_message = models.ForeignKey(
        SentMessages,
        on_delete=models.CASCADE,
        related_name='delivery_reports'
    )
    msisdn = models.CharField(max_length=20)
    status = models.CharField(max_length=50)
    received_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.msisdn} - {self.status}"