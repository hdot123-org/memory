import warnings

warnings.filterwarnings(
    "ignore",
    message="workbot adapter is deprecated",
    category=DeprecationWarning,
)


def pytest_configure(config):
    """Re-apply workbot DeprecationWarning filter during pytest configure phase."""
    warnings.filterwarnings(
        "ignore",
        message="workbot adapter is deprecated",
        category=DeprecationWarning,
    )
