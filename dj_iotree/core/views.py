from django.shortcuts import render
from django.http import HttpResponse

# Temporärer context


def home(request):
    return render(request, 'core/home.html')

def about(request):
    return render(request, 'core/about.html', {'title': 'About'})

def contact_us(request):
    return render(request, 'core/contact_us.html', {'title': 'Contact Us'})

def impressum(request):
    return render(request, 'core/impressum.html', {'title': 'Impressum'})

def datenschutz(request):
    return render(request, 'core/datenschutz.html', {'title': 'Datenschutz'})
