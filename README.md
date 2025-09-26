# Wikimore - A simple frontend for Wikimedia projects

[![Support Private.coffee!](https://shields.private.coffee/badge/private.coffee-support%20us!-pink?logo=coffeescript)](https://private.coffee)
[![Matrix](https://shields.private.coffee/badge/Matrix-join%20us!-blue?logo=matrix)](https://matrix.pcof.fi/#/#wikimore:private.coffee)
[![PyPI](https://shields.private.coffee/pypi/v/wikimore)](https://pypi.org/project/wikimore/)
[![PyPI - Python Version](https://shields.private.coffee/pypi/pyversions/wikimore)](https://pypi.org/project/wikimore/)
[![PyPI - License](https://shields.private.coffee/pypi/l/wikimore)](https://pypi.org/project/wikimore/)
[![Latest Git Commit](https://shields.private.coffee/gitea/last-commit/privatecoffee/wikimore?gitea_url=https://git.private.coffee)](https://git.private.coffee/privatecoffee/wikimore)

Wikimore is a simple frontend for Wikimedia projects. It uses the MediaWiki API to fetch data from Wikimedia projects and display it in a user-friendly way. It is built using Flask.

This project is still in development and more features will be added in the future. It is useful for anyone who wants to access Wikimedia projects with a more basic frontend, or to provide access to Wikimedia projects to users who cannot access them directly, for example due to state censorship.

## Features

- Supports all Wikimedia projects in all languages
- Search functionality
- Proxy support for Wikimedia images

## Instances

<!-- START_INSTANCE_LIST type:eq=clearnet -->

| URL                                                        | Provided by                              | Country               | Notes                 |
| ---------------------------------------------------------- | ---------------------------------------- | --------------------- | --------------------- |
| [wikimore.private.coffee](https://wikimore.private.coffee) | [Private.coffee](https://private.coffee) | Austria 🇦🇹 🇪🇺         | Main instance         |
| [wm.bloat.cat](https://wm.bloat.cat)                       | [Bloat.cat](https://bloat.cat)           | Germany 🇩🇪 🇪🇺         |                       |
| [wp.dc09.ru](https://wp.dc09.ru)                           | [dc09.ru](https://dc09.ru)               | Russian Federation 🇷🇺 |                       |
| [wikimore.privadency.com](https://wikimore.privadency.com) | [privadency](https://privadency.com)     | Germany 🇩🇪 🇪🇺         |                       |
| [wikimore.blitzw.in](https://wikimore.blitzw.in)           | [Blitzw.in](https://blitzw.in)           | Denmark 🇩🇰 🇪🇺         | Runs on modified code |

<!-- END_INSTANCE_LIST -->

### Tor Hidden Services

<!-- START_INSTANCE_LIST type:eq=onion -->

| URL                                                                                                                                                       | Provided by                              | Country       | Notes |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ------------- | ----- |
| [wikimore.coffee2m3bjsrrqqycx6ghkxrnejl2q6nl7pjw2j4clchjj6uk5zozad.onion](http://wikimore.coffee2m3bjsrrqqycx6ghkxrnejl2q6nl7pjw2j4clchjj6uk5zozad.onion) | [Private.coffee](https://private.coffee) | Austria 🇦🇹 🇪🇺 |       |

<!-- END_INSTANCE_LIST -->

### Adding Your Instance

To add your own instance to this list, please modify [instances.json](./instances.json), run [ilgen](https://pypi.org/project/ilgen/) to update README.md, and open a pull request, or just open an issue letting us know about your instance, see below.

## Opening Issues

If you're having problems using Wikimore, or if you have ideas or feedback for us, feel free to open an issue in the [Private.coffee Git](https://git.private.coffee/PrivateCoffee/wikimore/issues) or on [Github](https://github.com/PrivateCoffee/wikimore/issues).

Of course, you can also join our [Matrix room](https://matrix.pcof.fi/#/#wikimore:private.coffee) to discuss your ideas with us.

## Installation

### Production

1. Create a virtual environment and activate it

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install the package from PyPI

```bash
pip install wikimore
```

3. Run the application

```bash
wikimore
```

4. Open your browser and navigate to `http://localhost:8109`

### Docker

**Notice:** The current Docker image is now only hosted on the [Private.coffee Git](https://git.private.coffee/PrivateCoffee/-/packages/container/wikimore/latest). Please update your Docker Compose file to use `git.private.coffee/privatecoffee/wikimore:latest` instead of `privatecoffee/wikimore:latest`.

For your convenience, we also provide a Docker image. Note however that this is _not_ the recommended way to run Wikimore.

You can use the bundled `docker-compose-example.yml` file to run Wikimore with Docker Compose.

```bash
cp docker-compose-example.yml docker-compose.yml
docker compose up -d
```

This will start a container with Wikimore on port 8109. You can change the port in your `docker-compose.yml` file.

### Development

1. Clone the repository

```bash
git clone https://git.private.coffee/privatecoffee/wikimore.git
cd wikimore
```

2. Create a virtual environment and activate it

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install the package in editable mode

```bash
pip install -e .
```

4. Run the application

```bash
flask --app wikimore run
```

5. Open your browser and navigate to `http://localhost:5000`

## Configuration

You can configure Wikimore using environment variables. The following variables are available:

| Variable                   | Description                                                                               | Default Value                       |
| -------------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------- |
| WIKIMORE_HOST              | Which host / IP to listen on.                                                             | 0.0.0.0                             |
| WIKIMORE_PORT              | Which port to listen on                                                                   | 8109                                |
| WIKIMORE_SOCKET            | Path to a UNIX socket to listen on (overrides WIKIMORE_HOST and WIKIMORE_PORT)            | (not set)                           |
| WIKIMORE_DEBUG             | Enable debug mode (True if set to any value)                                              | False                               |
| WIKIMORE_INSTANCE_HOSTNAME | The hostname of your instance, used in the User-Agent header                              | (auto-detected)                     |
| WIKIMORE_ADMIN_EMAIL       | Email address of the instance administrator, used in the User-Agent header                | (not set)                           |
| WIKIMORE_NO_LANGSORT       | Disable custom language sorting (True if set to any value)                                | False                               |
| WIKIMORE_LANGSORT          | Custom language sorting, comma-separated list of language codes                           | en,es,ja,de,fr,zh,ru,it,pt,pl,nl,ar |
| WIKIMORE_CACHE_TYPE        | The type of cache to use (SimpleCache, FileSystemCache, RedisCache)                       | SimpleCache                         |
| WIKIMORE_CACHE_DIR         | The directory to use for FileSystemCache (only if WIKIMORE_CACHE_TYPE is FileSystemCache) | /tmp/wikimore_cache                 |
| WIKIMORE_REDIS_URL         | The Redis URL to use for RedisCache (if set, WIKIMORE_CACHE_TYPE is RedisCache)           | (not set)                           |
| WIKIMORE_CACHE_TIMEOUT     | The cache timeout in seconds                                                              | 3600 (= 1 hour)                     |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
