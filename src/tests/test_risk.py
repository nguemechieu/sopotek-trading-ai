from sopotek_trading_ai.src.sopotek_trading_ai.risk.institutional_risk import InstitutionalRiskEngine

def test_position_size():

    risk = InstitutionalRiskEngine(
        account_equity=10000
    )

    size = risk.position_size(
        entry_price=100,
        stop_price=95
    )

    assert size > 0


def test_trade_validation():

    risk = InstitutionalRiskEngine(
        account_equity=10000
    )

    approved, msg = risk.validate_trade(
        price=100,
        quantity=1
    )

    assert approved is True