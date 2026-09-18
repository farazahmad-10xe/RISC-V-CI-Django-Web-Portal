from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("", lambda request: redirect("dashboard")),
    path("portal/admin/", admin.site.urls),
    path(
        "portal/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("portal/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("portal/", include("results.urls")),
]
