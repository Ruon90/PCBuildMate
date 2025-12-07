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
        widget=forms.Select,
        label="Build Type"
    )
    resolution = forms.ChoiceField(
        choices=RESOLUTION_CHOICES,
        widget=forms.Select,
        label="Resolution"
    )
    # Optional preferences
    CPU_BRAND_CHOICES = [('', 'No preference'), ('AMD', 'AMD'), ('Intel', 'Intel')]
    GPU_BRAND_CHOICES = [('', 'No preference'), ('NVIDIA', 'NVIDIA'), ('AMD', 'AMD'), ('Intel', 'Intel')]
    RAM_SIZE_CHOICES = [('', 'No preference'), ('16', '16GB'), ('32', '32GB')]
    STORAGE_CAPACITY_CHOICES = [('', 'No preference'), ('512', '512GB'), ('1000', '1TB'), ('2000', '2TB')]

    cpu_brand = forms.ChoiceField(choices=CPU_BRAND_CHOICES, required=False, label='CPU brand')
    gpu_brand = forms.ChoiceField(choices=GPU_BRAND_CHOICES, required=False, label='GPU brand')
    ram_size = forms.ChoiceField(choices=RAM_SIZE_CHOICES, required=False, label='RAM capacity')
    storage_capacity = forms.ChoiceField(choices=STORAGE_CAPACITY_CHOICES, required=False, label='Storage capacity')
