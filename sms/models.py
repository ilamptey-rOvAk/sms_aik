from django.db import models

# Create your models here.
class SentMessages(models.Model):
    sender_id = models.CharField(max_length=25)
    phone_numbers = models.TextField()
    message = models.TextField()
    job_id = models.CharField(max_length=100, blank=True, null=True)
    api_status = models.CharField(max_length=50, default='Pending')
    delivery_status = models.CharField(max_length=50, default='Pending')
    api_response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender_id} - {self.created_at}"