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
| URL                                                              | Provided by                                    | Country               | Notes         |
| ---------------------------------------------------------------- | ---------------------------------------------- | --------------------- | ------------- |
| [wikimore.private.coffee](https://wikimore.private.coffee)       | [Private.coffee](https://private.coffee)       | Austria 🇦🇹 🇪🇺         | Main instance |
| [wm.bloat.cat](https://wm.bloat.cat)                             | [Bloat.cat](https://bloat.cat)                 | Germany 🇩🇪 🇪🇺         |               |
| [wm2.bloat.cat](https://wm2.bloat.cat)                           | [Bloat.cat](https://bloat.cat)                 | Germany 🇩🇪 🇪🇺         |               |
| [wikimore.blitzw.in](https://wikimore.blitzw.in)                 | [Blitzw.in](https://blitzw.in)                 | Denmark 🇩🇰 🇪🇺         |               |
| [wikimore.lumaeris.com](https://wikimore.lumaeris.com)           | [Lumaeris](https://lumaeris.com)               | Germany 🇩🇪 🇪🇺         |               |
| [wikimore.darkness.services](https://wikimore.darkness.services) | [Darkness.services](https://darkness.services) | United States 🇺🇸      |               |
| [wp.dc09.ru](https://wp.dc09.ru)                                 | [dc09.ru](https://dc09.ru)                     | Russian Federation 🇷🇺 |               |
<!-- END_INSTANCE_LIST -->

### Tor Hidden Services

<!-- START_INSTANCE_LIST type:eq=onion -->
| URL                                                                                                                                                       | Provided by                                    | Country          | Notes |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ---------------- | ----- |
| [wikimore.coffee2m3bjsrrqqycx6ghkxrnejl2q6nl7pjw2j4clchjj6uk5zozad.onion](http://wikimore.coffee2m3bjsrrqqycx6ghkxrnejl2q6nl7pjw2j4clchjj6uk5zozad.onion) | [Private.coffee](https://private.coffee)       | Austria 🇦🇹 🇪🇺    |       |
| [wikimore.darknessrdor43qkl2ngwitj72zdavfz2cead4t5ed72bybgauww5lyd.onion](http://wikimore.darknessrdor43qkl2ngwitj72zdavfz2cead4t5ed72bybgauww5lyd.onion) | [Darkness.services](https://darkness.services) | United States 🇺🇸 |       |
<!-- END_INSTANCE_LIST -->

### Adding Your Instance

To add your own instance to this list, please open a pull request or issue, see below.

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

__Notice:__ The Docker image is now hosted on the [Private.coffee Git](https://git.private.coffee/PrivateCoffee/-/packages/container/wikimore/latest). Please update your Docker Compose file to use `git.private.coffee/privatecoffee/wikimore:latest` instead of `privatecoffee/wikimore:latest`. The Docker Hub deployment may be removed in the future.

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

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
