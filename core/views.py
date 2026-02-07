from django.http import JsonResponse
from django.shortcuts import render


def home(request):
    return render(request, "core/home.html")


def health_check(request):
    return JsonResponse({"status": "ok"})
