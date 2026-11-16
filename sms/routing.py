from django.urls import path
from .consumers import KeepAliveConsumer

websocket_urlpatterns = [
    path("ws/keepalive/", KeepAliveConsumer.as_asgi()),
]
