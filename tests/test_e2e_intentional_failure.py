"""Intentional failure test for VAL-CROSS-006 e2e validation"""
def test_intentional_failure():
    """This test intentionally fails to trigger red PR sweeper"""
    assert False, "Intentional failure for e2e validation"
