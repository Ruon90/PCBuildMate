from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),  # landing page
    path('build/', views.build, name='build'),  # build calculator page
]
