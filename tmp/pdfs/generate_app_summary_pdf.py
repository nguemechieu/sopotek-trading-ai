from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

OUTPUT = r"output/pdf/sopotek_app_summary_one_page.pdf"

PAGE_W, PAGE_H = letter
MARGIN = 0.6 * inch
CONTENT_W = PAGE_W - (2 * MARGIN)

TITLE_SIZE = 16
H_SIZE = 11
BODY_SIZE = 9
LINE_GAP = 2

c = canvas.Canvas(OUTPUT, pagesize=letter)

def wrap_text(text, font_name="Helvetica", font_size=BODY_SIZE, width=CONTENT_W):
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        if stringWidth(test, font_name, font_size) <= width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def draw_lines(lines, x, y, font_name="Helvetica", font_size=BODY_SIZE):
    c.setFont(font_name, font_size)
    lh = font_size + LINE_GAP
    for line in lines:
        c.drawString(x, y, line)
        y -= lh
    return y

def section_header(text, x, y):
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", H_SIZE)
    c.drawString(x, y, text)
    y -= (H_SIZE + 3)
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.6)
    c.line(x, y, x + CONTENT_W, y)
    y -= 8
    c.setFillColor(colors.black)
    return y

y = PAGE_H - MARGIN

c.setFont("Helvetica-Bold", TITLE_SIZE)
c.setFillColor(colors.HexColor("#0B3A53"))
c.drawString(MARGIN, y, "Sopotek Trading AI - One-Page App Summary")
y -= TITLE_SIZE + 8
c.setFont("Helvetica", 8)
c.setFillColor(colors.HexColor("#475569"))
c.drawString(MARGIN, y, "Evidence sources: src/sopotek_trading_ai/* and docs/architecture.md")
y -= 14

# What it is
y = section_header("What It Is", MARGIN, y)
what_it_is = (
    "Sopotek Trading AI is a modular, event-driven algorithmic trading platform for crypto, forex, "
    "and stock markets. It combines live trading, backtesting, strategy modules, and a desktop UI "
    "in a Python codebase."
)
y = draw_lines(wrap_text(what_it_is), MARGIN, y)
y -= 6

# Who it's for
y = section_header("Who It's For", MARGIN, y)
who = "Primary persona: Not found in repo. Inferred from README/docs: quant developers and algorithmic traders building multi-asset automated systems."
y = draw_lines(wrap_text(who), MARGIN, y)
y -= 6

# What it does
y = section_header("What It Does", MARGIN, y)
features = [
    "Event-driven messaging via async publish/subscribe EventBus.",
    "Broker abstraction with factory support for crypto, forex, stocks, and paper brokers.",
    "Strategy layer with registry and built-in strategy modules (momentum, mean reversion, arbitrage).",
    "Risk and portfolio controls, including exposure and drawdown-related modules.",
    "Historical backtesting engine plus simulator and report generation modules.",
    "Desktop GUI workflow built with PySide6 + qasync (dashboard and terminal views).",
]
for item in features:
    bullet_lines = wrap_text(item, width=CONTENT_W - 14)
    if bullet_lines:
        c.setFont("Helvetica", BODY_SIZE)
        c.drawString(MARGIN, y, "-")
        c.drawString(MARGIN + 10, y, bullet_lines[0])
        y -= BODY_SIZE + LINE_GAP
        for cont in bullet_lines[1:]:
            c.drawString(MARGIN + 10, y, cont)
            y -= BODY_SIZE + LINE_GAP
y -= 4

# How it works
y = section_header("How It Works (Repo-Evidenced Architecture)", MARGIN, y)
arch_lines = [
    "Components/services: UI (AppController/Terminal), SopotekTrading + TradingEngine, BrokerFactory + broker adapters,",
    "EventBus, Strategy modules, Risk modules, ExecutionManager/OrderRouter, PortfolioManager, SQLAlchemy storage repositories.",
    "Data flow: market data (broker/websocket + candle buffers) -> strategy signals -> risk validation -> order execution ->",
    "portfolio updates -> logs/storage/analytics. Orchestration classes exist under core/ (orchestrator, scheduler, system_state).",
]
for line in arch_lines:
    y = draw_lines(wrap_text(line), MARGIN, y)
y -= 6

# How to run
y = section_header("How To Run (Minimal Getting Started)", MARGIN, y)
steps = [
    "From repo root: cd src/sopotek_trading_ai",
    "Create and activate venv: python -m venv .venv, then .venv\\Scripts\\activate (Windows)",
    "Install deps: pip install -r requirements.txt",
    "Run desktop app: python main.py",
    "Optional scripts: python scripts/run_backtest.py or python scripts/run_live.py",
    "Credentials source: .env format shown in README. Verified production-ready run command: Not found in repo.",
]
for s in steps:
    lines = wrap_text(s, width=CONTENT_W - 14)
    c.drawString(MARGIN, y, "-")
    c.drawString(MARGIN + 10, y, lines[0])
    y -= BODY_SIZE + LINE_GAP
    for cont in lines[1:]:
        c.drawString(MARGIN + 10, y, cont)
        y -= BODY_SIZE + LINE_GAP

if y < MARGIN - 4:
    raise RuntimeError(f"Content overflowed one page (y={y})")

c.save()
print(OUTPUT)
