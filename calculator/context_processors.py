from importlib import import_module
from django.conf import settings
from allauth.account.forms import LoginForm as AllauthLoginForm, SignupForm as AllauthSignupForm


def _get_signup_form_class():
    """Resolve the signup form class from settings.ACCOUNT_FORMS if configured,
    otherwise fall back to allauth's default SignupForm.
    """
    form_path = getattr(settings, 'ACCOUNT_FORMS', {}).get('signup')
    if form_path:
        try:
            module_path, cls_name = form_path.rsplit('.', 1)
            mod = import_module(module_path)
            return getattr(mod, cls_name)
        except Exception:
            # Fall back to the default if anything goes wrong
            return AllauthSignupForm
    return AllauthSignupForm


def auth_forms(request):
    SignupCls = _get_signup_form_class()
    return {
        "login_form": AllauthLoginForm(),
        "signup_form": SignupCls(),
        "preview_build": request.session.get("preview_build"),
    }
