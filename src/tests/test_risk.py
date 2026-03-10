from engines.risk_engine import RiskEngine


def test_position_size():
    risk = RiskEngine(account_equity=10000)

    size = risk.position_size(
        entry_price=100,
        stop_price=95,
    )

    assert size > 0


def test_trade_validation():
    risk = RiskEngine(account_equity=10000, max_position_size_pct=0.5)

    approved, msg = risk.validate_trade(
        price=100,
        quantity=1,
    )

    assert approved is True
    assert msg == "Approved"
