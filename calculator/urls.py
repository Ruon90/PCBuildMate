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
    path(
        "build/preview/<int:pk>/",
        views.build_preview_pk,
        name="build_preview_pk",
    ),
    path(
        "build/upgrade_preview/", views.upgrade_preview, name="upgrade_preview"
    ),
    # View a saved upgrade in the upgrade-preview UI
    path(
        "build/view_upgrade/<int:pk>/",
        views.view_saved_upgrade,
        name="view_saved_upgrade",
    ),
    # Alternatives for the last calculated build
    path(
        "build/preview/alternatives/", views.alternatives, name="alternatives"
    ),
    path(
        "build/preview/alternatives/select/",
        views.select_alternative,
        name="select_alternative",
    ),
    # Upgrade calculator for an existing preview or saved build
    path(
        "build/upgrade/", views.upgrade_calculator, name="upgrade_calculator"
    ),
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
