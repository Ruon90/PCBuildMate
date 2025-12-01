from django import forms

CURRENCY_CHOICES = [
    ("USD", "$ US Dollar"),
    ("GBP", "£ British Pound"),
    ("EUR", "€ Euro"),
]

BUILD_TYPE_CHOICES = [
    ("gaming", "Gaming PC"),
    ("workstation", "Workstation"),
]

RESOLUTION_CHOICES = [
    ("1080p", "1080p"),
    ("1440p", "1440p"),
    ("4k", "4K"),
]

class BudgetForm(forms.Form):
    budget = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label="Budget",
        widget=forms.NumberInput(attrs={"placeholder": "Enter your budget"})
    )
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        label="Currency"
    )
    build_type = forms.ChoiceField(
        choices=BUILD_TYPE_CHOICES,
        widget=forms.RadioSelect,
        label="Build Type"
    )
    resolution = forms.ChoiceField(
        choices=RESOLUTION_CHOICES,
        widget=forms.RadioSelect,
        label="Resolution"
    )
