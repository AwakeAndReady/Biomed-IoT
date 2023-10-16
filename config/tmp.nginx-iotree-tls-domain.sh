#!/bin/sh

# Get passed parameter
SETUP_DIR=$1
DOMAIN=$2

# Define nginx server block template:
# Certbot updates the server blocks automatically. 
# Nevertheless, listen 443, redirect are prepared here to include custom ssl-params.conf

cat << EOF
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN www.$DOMAIN;
    include snippets/ssl-params.conf;  # in addition to certbots parameters

    location = /favicon.ico { access_log off; log_not_found off; }
    location /static/ {
        root $SETUP_DIR/dj_iotree;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
    }
}

server {
    listen 80;
    listen [::]:80;

    server_name $DOMAIN www.$DOMAIN;

    return 302 https://$server_name$request_uri;  # change 302 to 301 after successfull testing
}
EOF