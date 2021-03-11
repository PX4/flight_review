# Description

Work with docker

# Arguments

- PORT - The number of port, what listen service in docker, default 5006
- USE_PROXY - The set his, if you use reverse proxy (Nginx, ...)
- DOMAIN - The address domain name for origin, default = *

# Paths

- /opt/service/config_user.ini - Path for config
- /opt/service/data - Folder where stored database

# Build

```bash
docker build -t px4flightreview -f docker/Dockerfile .
```

# Example

docker-compse.yml - example work with image