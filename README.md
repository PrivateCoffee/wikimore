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

| URL                                                         | Provided by                               | Country | Comments |
| ----------------------------------------------------------- | ----------------------------------------- | ------- | -------- |
| [wikimore.private.coffee](https://wikimore.private.coffee/) | [Private.coffee](https://private.coffee/) | Austria |          |
| [wm.bloat.cat](https://wm.bloat.cat/)                       | [bloat.cat](https://bloat.cat/)           | Germany |          |

If you operate a public instance of Wikimore and would like to have it listed here, please open an issue or a pull request.

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

## Development

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
