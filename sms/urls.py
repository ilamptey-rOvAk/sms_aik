from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('history/', views.message_history, name='message_history'),
    path('callback/', views.nalo_callback, name='nalo_callback'),
]
