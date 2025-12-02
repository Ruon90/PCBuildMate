from allauth.account.forms import LoginForm, SignupForm

def auth_forms(request):
    return {
        "login_form": LoginForm(),
        "signup_form": SignupForm(),
        "preview_build": request.session.get("preview_build"),
    }
