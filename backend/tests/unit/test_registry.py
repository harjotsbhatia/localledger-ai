from localledger.connectors.registry import default_connectors


def test_shipped_providers_describe_who_sees_the_data():
    infos = {k: c.info for k, c in default_connectors().items()}
    assert set(infos) == {"simplefin", "plaid_sandbox"}
    assert "passes through the SimpleFIN Bridge" in infos["simplefin"].data_path
    assert infos["simplefin"].min_sync_interval_seconds >= 3600
    assert infos["plaid_sandbox"].environment == "sandbox"
    assert "synthetic" in infos["plaid_sandbox"].data_path
    # Secret inputs are flagged so the UI masks them.
    assert {f.name for i in infos.values() for f in i.fields if f.secret} == {
        "setup_token", "secret"}
