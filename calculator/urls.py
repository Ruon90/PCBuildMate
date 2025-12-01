from django.urls import path
from . import views

urlpatterns = [
    # Landing page with budget form
    path("", views.index, name="home"),

    # AJAX endpoint for calculation
    path("calculate/", views.calculate_build, name="calculate_build"),

    # Build preview page (redirect target after calculation)
    path("build/preview/", views.build_preview, name="build_preview"),

    # Save build (requires login)
    path("build/save/", views.save_build, name="save_build"),

    # List of saved builds (requires login)
    path("builds/", views.saved_builds, name="saved_builds"),
]
