# Sopotek Trading AI

<img alt="logo" height="170" src="../sopotek-trading-ai/src/assets/logo_170X170.png" width="170"/>


Sopotek Trading AI is a modular, event-driven algorithmic trading platform for crypto, forex, and equities.

## Status
This package is currently **alpha** and includes core broker, market-data websocket, model persistence, and GUI modules.

## Features
- Multi-asset broker integration (crypto, forex, stocks, paper)
- Async websocket market data clients
- Model checkpoint and model persistence utilities
- PySide6 + PyQtGraph UI components

## Requirements
- Python 3.11+

## Installation
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Or install as a package:
```bash
python -m pip install .
```

## Build and package checks
Use module invocations to avoid PATH script warnings:
```bash
python -m pip install -U build twine
python -m build
python -m twine check dist/*
```

## Configuration
Copy `.env.example` to `.env` and set values:
```env
ALPACA_API_KEY=your_key
ALPACA_SECRET=your_secret
```

## Security Note
Never commit real API keys. `.env` is ignored by default.

## License
MIT. See [LICENSE](LICENSE).


## Documentation
- Full application guide: [docs/FULL_APP_GUIDE.md](docs/FULL_APP_GUIDE.md)

