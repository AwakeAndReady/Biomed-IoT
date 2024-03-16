import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, UserLoginForm, MQTTClientForm
from .models import NodeRedUserData, MQTTClient
import docker
import secrets
from django.http import JsonResponse
from django.db import IntegrityError
import random
import string
from django.db import transaction
from django.conf import settings
from .services.nodered_utils import NoderedContainer, update_nodered_nginx_conf


def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                username = form.cleaned_data.get('username')
                messages.success(request, f'Your account has been created! You are now able to log in')
                return redirect('login')
            except Exception as e:
                messages.error(request, f'An error occurred while creating your account. Please try again.')
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})
    

def user_login(request):
    if request.method == "POST":
        form = UserLoginForm(data=request.POST)
        if form.is_valid():
            # The 'username' field can be either a username or an email
            user = authenticate(request, 
                                username=form.cleaned_data['username'],
                                password=form.cleaned_data['password'])
            if user:
                login(request, user)
                return redirect('core-home')
    else:
        form = UserLoginForm()

    return render(request, 'users/login.html', {'form': form})


@login_required
def profile(request):
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST,
                                   request.FILES,
                                   instance=request.user.profile) # FILES = Image
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, f'Your account has been updated!')
            return redirect('profile')

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'u_form': u_form,
        'p_form': p_form
    }

    return render(request, 'users/profile.html', context)


# Prepare a map of common locations to timezone choices you wish to offer.
common_timezones = {
    "Berlin": "Europe/Berlin",
    "London": "Europe/London",
    "New York": "America/New_York",
}
timezones = [('New York', 'America/New_York'), ('London', 'Europe/London')]

# Experimental function
@login_required
def set_timezone(request):
    if request.method == "POST":
        request.session["django_timezone"] = request.POST["timezone"]
        return redirect("/")
    else:
         # Convert the dictionary to a list of tuples and sort by city name
        timezones_list = sorted(common_timezones.items(), key=lambda x: x[0])
        return render(request, "set_timezone.html", {"timezones": timezones_list})

@login_required
def client_list(request):
    # Filter clients by the current user and pass to the template
    clients = MQTTClient.objects.filter(user=request.user)
    mock_clients = [
        {'client_username': 'user1', 'client_id': '001', 'textname': 'Client 1', 'textdescription': 'Description for Client 1'},
        {'client_username': 'user2', 'client_id': '002', 'textname': 'Client 2', 'textdescription': 'Description for Client 2'},
        {'client_username': 'user3', 'client_id': '003', 'textname': 'Client 3', 'textdescription': 'Description for Client 3'},
    ]
    context = {'clients': mock_clients}
    return render(request, 'users/client_list.html', context)

@login_required
def add_client(request):
    if request.method == 'POST':
        form = MQTTClientForm(request.POST)
        if form.is_valid():
            # Instead of directly saving the form, save it to a model instance without committing to the database yet
            new_client = form.save(commit=False)
            # Set the user field to the currently logged-in user
            new_client.user = request.user
            # Now save the model instance to the database
            new_client.save()
            return redirect('client-list')
    else:
        form = MQTTClientForm()
    return render(request, 'users/add_client.html', {'form': form})

@login_required
def modify_client(request, client_username):
    client = get_object_or_404(MQTTClient, pk=client_username)
    if request.method == 'POST':
        form = MQTTClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            return redirect('client-list')
    else:
        form = MQTTClientForm(instance=client)
    return render(request, 'users/modify_client.html', {'form': form, 'client': client})

@login_required
def delete_client(request, client_username):
    client = get_object_or_404(MQTTClient, pk=client_username)
    if request.method == 'POST':
        # If the 'delete' action is confirmed
        if 'confirm_delete' in request.POST:
            client.delete()
            return redirect('client-list')
        else:
            # If any other action, just redirect back to the client list
            return redirect('client-list')
    else:
        # Render a confirmation page/template
        return render(request, 'users/delete_client.html', {'client': client})
        

@login_required
def nodered_manager(request):
    context = {}
    
    with transaction.atomic():
        try:
            # Attempt to create NodeRedUserData with a unique container name
            nodered_data, created = NodeRedUserData.objects.get_or_create(
                user=request.user,
                defaults={
                    'container_name': NodeRedUserData.generate_unique_container_name(),
                    'access_token': secrets.token_urlsafe(22)
                }
            )
        except IntegrityError:
            # TODO: log error
            pass

        nodered_container = NoderedContainer(nodered_data)
        nodered_container.state = nodered_container.determine_state()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'run':
            nodered_container.determine_port()
            if nodered_data.container_port != nodered_container.port:
                update_nodered_data_container_port(nodered_data, nodered_container)
                update_nodered_nginx_conf(nodered_data)
            request.session['container_name'] = nodered_container.name
            return redirect('nodered-embedded')
        
        elif action == 'create':
            if nodered_container.get_existing_container() is None:
                # Generate completely new data if no container is found
                nodered_data.container_name = NodeRedUserData.generate_unique_container_name()
                nodered_data.access_token = secrets.token_urlsafe(22)
                nodered_data.save()

                # Update the NoderedContainer instance with the new nodered_data
                nodered_container.name = nodered_data.container_name
                nodered_container.access_token = nodered_data.access_token

                # Proceed to create the container
                nodered_container.create()

                # After creation, update the database with the new port
                update_nodered_data_container_port(nodered_data, nodered_container)

                update_nodered_nginx_conf(nodered_data)
            else:
                messages.info(request, f'Node-RED is already running.')

        elif action == 'restart':
            if nodered_container.state == 'stopped':
                nodered_container.restart()
                update_nodered_data_container_port(nodered_data, nodered_container)
                update_nodered_nginx_conf(nodered_data)
            else:
                messages.info(request, f'Cannot restart Node-RED. Node-RED is {nodered_container.state}.')

        elif action == 'stop':
            if nodered_container.state == 'running':
                update_nodered_data_container_port(nodered_data, nodered_container)
                update_nodered_nginx_conf(nodered_data)
                nodered_container.stop()
            else:
                messages.info(request, f'Cannot stop Node-RED. Node-RED is {nodered_container.state}.')
    
    container_state = nodered_container.determine_state()  # default for new NodeRedUserData: 'no-container'
    context['container_state'] = container_state

    if container_state == 'unavailable':
        messages.error(request, f'Unable to start Node-RED. Please try again or contact the site admin.')
        
    return render(request, 'users/nodered_manager.html', context)

def update_nodered_data_container_port(nodered_data, nodered_container):
    if nodered_container.port is not None:
        nodered_data.container_port = nodered_container.port
    else:
        # Clear the port in nodered_data if the container is stopped or port is not available
        nodered_data.container_port = ''
    nodered_data.save()

@login_required
def nodered_embedded(request):
    container_name = request.session.get('container_name')
    context = {'container_name': container_name}
    return render(request, 'users/nodered_embedded.html', context)
