# Temporary fixture for live validation of stale-check race fix
# This file exists to trigger droid-review with actual code to review
def validation_fixture_function(x: int, y: int) -> int:
    """Temporary function for validation testing."""
    return x + y

def another_helper(items: list[str]) -> str:
    """Another temporary helper."""
    return ", ".join(sorted(items))
