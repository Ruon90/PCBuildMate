from django.shortcuts import render
from .forms import BudgetForm

def index(request):
    if request.method == "POST":
        form = BudgetForm(request.POST)
        if form.is_valid():
            # handle calculation logic here
            pass
    else:
        form = BudgetForm()
    return render(request, "calculator/index.html", {"form": form})

def build(request):
    # later: show component cards (CPU, GPU, etc.)
    return render(request, "calculator/build.html")
