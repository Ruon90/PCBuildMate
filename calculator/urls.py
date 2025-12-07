from django.urls import path
from . import views
from .views import ai_chat
urlpatterns = [
    # Landing page with budget form
    path("", views.index, name="home"),

    # AJAX endpoint for calculation
    path("calculate/", views.calculate_build, name="calculate_build"),

    # Build preview page (redirect target after calculation)
    path("build/preview/", views.build_preview, name="build_preview"),
    # Preview a specific saved UserBuild
    path("build/preview/<int:pk>/", views.build_preview_pk, name="build_preview_pk"),

    # Save build (requires login)
    path("build/save/", views.save_build, name="save_build"),
    # Clear current preview build
    path("build/clear/", views.clear_build, name="clear_build"),
    # Edit the current session preview (GET/POST)
    path("build/preview/edit/", views.preview_edit, name="preview_edit"),
    # List of saved builds (requires login)
    path("builds/", views.saved_builds, name="saved_builds"),
    # Delete a saved build (requires login)
    path("build/<int:pk>/delete/", views.delete_build, name="delete_build"),
    # Edit a saved build (requires login)
    path("build/<int:pk>/edit/", views.edit_build, name="edit_build"),
    path("ai-chat/", ai_chat, name="ai_chat"),
]
