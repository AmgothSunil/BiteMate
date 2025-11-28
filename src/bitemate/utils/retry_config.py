# src/bitemate/utils/retry_config.py
import sys
from typing import Any, Dict, Union
from google.genai import types

from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

# Load params
params = load_params(CONFIG_REL_PATH)
retry_config_params = params.get("retry_config_params", {})

# Use correct keys (watch spelling in your YAML)
logs_file_path = retry_config_params.get("file_path", "retry_config.log")
attempts = retry_config_params.get("attempts", 5)            # fixed spelling
exp_base = retry_config_params.get("exp_base", 7)
initial_delay = retry_config_params.get("initial_delay", 1)
http_status_codes = retry_config_params.get("http_status_codes", [429, 500, 503, 504])  # fixed spelling

logger = setup_logger(
    name="RetryConfig",
    log_file_name=logs_file_path
)


def retry_config() -> Union[types.HttpRetryOptions, Dict[str, Any]]:
    """
    Builds and returns a retry configuration object compatible with
    google.genai types.HttpRetryOptions.

    Returns either a types.HttpRetryOptions instance (preferred) or a plain dict,
    depending on the environment. If types.HttpRetryOptions is unavailable,
    we return a dict that should be acceptable to Pydantic-based constructors.
    """
    try:
        logger.info("Initializing Retry Config")

        # Prefer constructing the typed HttpRetryOptions if available
        try:
            config = types.HttpRetryOptions(
                attempts=int(attempts),
                exp_base=float(exp_base),
                initial_delay=float(initial_delay),
                http_status_codes=list(http_status_codes)
            )
            logger.info("Retry Config initialized as types.HttpRetryOptions.")
            return config
        except Exception as inner_exc:
            # If for some reason the typed object isn't available or fails, fall back to dict
            logger.warning(
                "Failed to initialize typed HttpRetryOptions (%s). Falling back to dict.", inner_exc
            )
            config_dict = {
                "attempts": int(attempts),
                "exp_base": float(exp_base),
                "initial_delay": float(initial_delay),
                "http_status_codes": list(http_status_codes),
            }
            logger.info("Retry Config initialized as dict fallback.")
            return config_dict

    except Exception as e:
        logger.error("An error occurred while initializing Retry Config: %s", e)
        # Raise a clear AppException with a helpful message
        raise AppException(f"RetryConfig initialization failed: {e}", sys)
