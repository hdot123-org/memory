"""Tests for the unified _redaction module.

Covers:
- 6 API token formats (sk-, sk-ant-, ghp_, AKIA, lin_api_, glpat-)
- JWT tokens
- Auth headers (Bearer, Basic)
- Password/secret parameters
- Private IP addresses (192.168, 10.x, 172.16-31)
- User home paths (/Users/, /home/)
- redact_user_paths parameter
- max_len truncation
- redact_dict recursive handling
- Consumer module integration
"""

import pytest
from memory_core.tools._redaction import redact, redact_dict

# Test fixtures — NOT real credentials, just random strings with token prefixes
_SK_TOKEN = "sk-" + "a1b2c3d4e5f6g7h8"
_SKANT_TOKEN = "sk-ant-" + "a1b2c3d4e5f6g7h8i9j0"
_GHP_TOKEN = "ghp_" + "a1b2c3d4e5f6g7h8i9j0k1l2m3n4"
_AKIA_TOKEN = "AKIA" + "A1B2C3D4E5F6G7H8"
_LIN_TOKEN = "lin_api_" + "a1b2c3d4e5f6g7h8i9j0"
_GLPAT_TOKEN = "glpat-" + "a1b2c3d4e5f6g7h8i9j0"


class TestApiTokens:
    """Test API token redaction (6 formats)."""

    def test_redacts_openai_sk(self):
        result = redact("api_key=" + _SK_TOKEN)
        assert _SK_TOKEN not in result
        assert "[REDACTED]" in result

    def test_redacts_anthropic_sk_ant(self):
        result = redact("api_key=" + _SKANT_TOKEN)
        assert _SKANT_TOKEN not in result
        assert "[REDACTED]" in result

    def test_redacts_github_ghp(self):
        result = redact("token=" + _GHP_TOKEN)
        assert _GHP_TOKEN not in result
        assert "[REDACTED]" in result

    def test_redacts_aws_akia(self):
        result = redact("aws_key=" + _AKIA_TOKEN)
        assert _AKIA_TOKEN not in result
        assert "[REDACTED]" in result

    def test_redacts_linear_lin_api(self):
        result = redact("token=" + _LIN_TOKEN)
        assert _LIN_TOKEN not in result
        assert "[REDACTED]" in result

    def test_redacts_gitlab_glpat(self):
        result = redact("token=" + _GLPAT_TOKEN)
        assert _GLPAT_TOKEN not in result
        assert "[REDACTED]" in result

    def test_sk_ant_before_sk(self):
        """sk-ant- must be matched before sk- to avoid residue."""
        result = redact(_SKANT_TOKEN)
        assert _SKANT_TOKEN not in result
        assert "[REDACTED]" in result


class TestAuthHeaders:
    """Test auth header redaction."""

    def test_redacts_bearer_token(self):
        result = redact("Authorization: Bearer my-secret-token-value")
        assert "my-secret-token-value" not in result
        assert "Bearer" in result
        assert "[REDACTED]" in result

    def test_redacts_basic_auth(self):
        result = redact("Authorization: Basic PLACEHOLDER_AUTH")
        assert "PLACEHOLDER_AUTH" not in result
        assert "Basic" in result
        assert "[REDACTED]" in result

    def test_case_insensitive_bearer(self):
        result = redact("authorization: bearer mytoken123456789")
        assert "mytoken123456789" not in result

    def test_redacts_bare_bearer_without_authorization_prefix(self):
        """Bare 'Bearer <cred>' without 'Authorization:' prefix must be redacted.

        Regression test for VAL-REDACT-008: the old SanitizingFilter had pattern
        `(Bearer\\s+)\\S+` matching bare Bearer. The shared _redaction module
        must preserve this coverage.
        """
        fake_cred = "somecredential123abc"
        text = "Bearer " + fake_cred
        result = redact(text)
        assert fake_cred not in result
        assert "Bearer" in result
        assert "[REDACTED]" in result

    def test_authorization_bearer_still_works(self):
        """Ensure Authorization: Bearer pattern is not broken by bare Bearer addition."""
        fake_cred = "auth-header-secret-value"
        text = "Authorization: Bearer " + fake_cred
        result = redact(text)
        assert fake_cred not in result
        assert "Bearer" in result
        assert "[REDACTED]" in result


class TestPasswordSecretParams:
    """Test password/secret parameter redaction."""

    def test_redacts_password(self):
        result = redact("password=test_password_value")
        assert "test_password_value" not in result
        assert "password=[REDACTED]" in result

    def test_redacts_passwd(self):
        result = redact("passwd=anotherSecret")
        assert "anotherSecret" not in result

    def test_redacts_pwd(self):
        result = redact("pwd=shortPass")
        assert "shortPass" not in result

    def test_redacts_secret_key(self):
        result = redact("secret_key=mysupersecretkey123")
        assert "mysupersecretkey123" not in result
        assert "[REDACTED]" in result

    def test_redacts_api_key(self):
        result = redact("api_key=key123456789abcdef")
        assert "key123456789abcdef" not in result
        assert "[REDACTED]" in result

    def test_redacts_token_param(self):
        result = redact("token=test_token_value")
        assert "test_token_value" not in result
        assert "[REDACTED]" in result

    def test_redacts_credential(self):
        result = redact("credential=cred_xyz789abc123")
        assert "cred_xyz789abc123" not in result
        assert "[REDACTED]" in result


class TestPrivateIPs:
    """Test private IP address redaction."""

    def test_redacts_192_168_range(self):
        result = redact("connecting to 192.168.1.100:5432")
        assert "192.168.1.100" not in result
        assert "[REDACTED_IP]" in result

    def test_redacts_10_range(self):
        result = redact("server at 10.0.0.50:8080")
        assert "10.0.0.50" not in result
        assert "[REDACTED_IP]" in result

    def test_redacts_172_16_31_range(self):
        result = redact("internal 172.16.0.1")
        assert "172.16.0.1" not in result
        assert "[REDACTED_IP]" in result

        result2 = redact("internal 172.31.255.255")
        assert "172.31.255.255" not in result2
        assert "[REDACTED_IP]" in result2

    def test_preserves_public_ips(self):
        result = redact("public server 8.8.8.8")
        assert "8.8.8.8" in result
        assert "[REDACTED_IP]" not in result

    def test_preserves_172_outside_range(self):
        result = redact("edge case 172.15.0.1")
        assert "172.15.0.1" in result

        result2 = redact("edge case 172.32.0.1")
        assert "172.32.0.1" in result2


class TestUserPaths:
    """Test user home path redaction."""

    def test_redacts_macos_user_path(self):
        result = redact("file at /Users/johnsmith/project/file.txt")
        assert "johnsmith" not in result
        assert "[USER_PATH]" in result

    def test_redacts_linux_home_path(self):
        result = redact("config at /home/developer/.config/app")
        assert "developer" not in result
        assert "[USER_PATH]" in result

    def test_redact_user_paths_false(self):
        text = "file at /Users/johnsmith/project"
        result = redact(text, redact_user_paths=False)
        assert "johnsmith" in result
        assert "[USER_PATH]" not in result

    def test_redact_user_paths_false_still_redacts_secrets(self):
        text = "file at /Users/johnsmith/ secret=" + _SK_TOKEN
        result = redact(text, redact_user_paths=False)
        assert "johnsmith" in result
        assert _SK_TOKEN not in result
        assert "[REDACTED]" in result


class TestMaxLen:
    """Test max_len truncation."""

    def test_default_max_len(self):
        text = "x" * 3000
        result = redact(text)
        assert len(result) <= 2000

    def test_custom_max_len(self):
        text = "x" * 500
        result = redact(text, max_len=100)
        assert len(result) <= 100


class TestEdgeCases:
    """Test edge cases and empty inputs."""

    def test_empty_string(self):
        assert redact("") == ""

    def test_none_input(self):
        assert redact(None) is None

    def test_no_secrets(self):
        text = "normal log message with no secrets"
        result = redact(text)
        assert result == text

    def test_multiple_secrets(self):
        text = "api_key=" + _SK_TOKEN + " password=test_password host=192.168.1.1"
        result = redact(text)
        assert _SK_TOKEN not in result
        assert "test_password" not in result
        assert "192.168.1.1" not in result


class TestRedactDict:
    """Test recursive dict redaction."""

    def test_redacts_top_level_strings(self):
        d = {"key": _SK_TOKEN, "another": _GHP_TOKEN}
        result = redact_dict(d)
        assert _SK_TOKEN not in result["key"]
        assert _GHP_TOKEN not in result["another"]

    def test_preserves_non_strings(self):
        d = {"count": 42, "flag": True, "none": None, "list": [1, 2, 3]}
        result = redact_dict(d)
        assert result["count"] == 42
        assert result["flag"] is True
        assert result["none"] is None
        assert result["list"] == [1, 2, 3]

    def test_redacts_nested_dicts(self):
        d = {
            "outer": {
                "inner": _SK_TOKEN,
                "another": "password=hidden_value"
            }
        }
        result = redact_dict(d)
        assert _SK_TOKEN not in result["outer"]["inner"]
        assert "hidden_value" not in result["outer"]["another"]

    def test_redacts_strings_in_lists(self):
        d = {
            "tokens": [_SK_TOKEN, _GHP_TOKEN],
            "plain": ["normal", "text"]
        }
        result = redact_dict(d)
        assert _SK_TOKEN not in result["tokens"][0]
        assert _GHP_TOKEN not in result["tokens"][1]
        assert result["plain"] == ["normal", "text"]

    def test_redacts_dicts_in_lists(self):
        d = {
            "items": [
                {"api_key": _SK_TOKEN},
                {"password": "password=hidden_value"}
            ]
        }
        result = redact_dict(d)
        assert _SK_TOKEN not in result["items"][0]["api_key"]
        assert "hidden_value" not in result["items"][1]["password"]

    def test_empty_dict(self):
        assert redact_dict({}) == {}

    def test_kwargs_forwarded(self):
        d = {"path": "/Users/johnsmith/file.txt"}
        result = redact_dict(d, redact_user_paths=False)
        assert "johnsmith" in result["path"]
        assert "[USER_PATH]" not in result["path"]


class TestConsumerIntegration:
    """Test that consumer modules use shared redaction."""

    def test_log_utils_imports_redaction(self):
        from memory_core.tools import log_utils
        import inspect
        source = inspect.getsource(log_utils)
        assert "_redaction" in source or "redact" in source

    def test_error_logger_imports_redaction(self):
        from memory_core.tools import error_logger
        import inspect
        source = inspect.getsource(error_logger)
        assert "_redaction" in source or "redact" in source

    def test_telemetry_bridge_imports_redaction(self):
        from memory_core.tools import telemetry_bridge
        import inspect
        source = inspect.getsource(telemetry_bridge)
        assert "_redaction" in source or "redact" in source

    def test_memory_hook_gateway_imports_redaction(self):
        from memory_core.tools import memory_hook_gateway
        import inspect
        source = inspect.getsource(memory_hook_gateway)
        assert "_redaction" in source or "redact" in source
