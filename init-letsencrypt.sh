#!/bin/bash

if ! [ -x "$(command -v docker-compose -f docker-compose.prod.yml)" ]; then
  echo 'Error: docker-compose -f docker-compose.prod.yml is not installed.' >&2
  exit 1
fi

. .env # get variable from .env file

domain=${DOMAIN} # www.${DOMAIN})
rsa_key_size=4096
cert_path=${CERT_PATH}
email=${EMAIL} # Adding a valid address is strongly recommended
staging=0 # Set to 1 if you're testing your setup to avoid hitting request limits

if [ -d "$cert_path" ]; then
  read -p "Existing data found for $domain. Continue and replace existing certificate? (y/N) " decision
  if [ "$decision" != "Y" ] && [ "$decision" != "y" ]; then
    exit
  fi
fi


# Download TLS parameters
if [ ! -e "$cert_path/conf/options-ssl-nginx.conf" ] || [ ! -e "$cert_path/conf/ssl-dhparams.pem" ]; then
  echo "### Downloading recommended TLS parameters ..."
  mkdir -p "$cert_path/conf"
  curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > "$cert_path/conf/options-ssl-nginx.conf"
  curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > "$cert_path/conf/ssl-dhparams.pem"
  echo
fi

echo "### Creating dummy certificate for $domain ..."
path="/etc/letsencrypt/live/$domain"
mkdir -p "$cert_path/conf/live/$domain"
docker-compose -f docker-compose.prod.yml run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1\
    -keyout '$path/privkey.pem' \
    -out '$path/fullchain.pem' \
    -subj '/CN=localhost'" certbot
echo


echo "### Starting nginx ..."
docker-compose -f docker-compose.prod.yml up --force-recreate -d nginx
echo

echo "### Deleting dummy certificate for $domain ..."
docker-compose -f docker-compose.prod.yml run --rm --entrypoint "\
  rm -Rf /etc/letsencrypt/live/$domain && \
  rm -Rf /etc/letsencrypt/archive/$domain && \
  rm -Rf /etc/letsencrypt/renewal/$domain.conf" certbot
echo


echo "### Requesting Let's Encrypt certificate for $domain ..."
#Join $domain to -d args
domain_args=""
for domain in "${domain[@]}"; do
  domain_args="$domain_args -d $domain"
done
echo $domain_args
# Select appropriate email arg
case "$email" in
  "") email_arg="--register-unsafely-without-email" ;;
  *) email_arg="--email $email" ;;
esac

# Enable staging mode if needed
if [ $staging != "0" ]; then staging_arg="--staging"; fi

docker-compose -f docker-compose.prod.yml run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    $email_arg \
    $domain_args \
    --rsa-key-size $rsa_key_size \
    --agree-tos \
    --force-renewal" certbot
echo

echo "### Reloading nginx ..."
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
docker-compose -f docker-compose.prod.yml build certbot
docker-compose -f docker-compose.prod.yml up -d
