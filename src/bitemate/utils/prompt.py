import sys
from pathlib import Path

from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

params = load_params(CONFIG_REL_PATH)

session_prompt_params = params.get("prompt_loader", {})

log_file_path = session_prompt_params.get("file_path", "prompt_loader.log")

logger = setup_logger("PromptManager", log_file_path)


class PromptManager:
    """
    Manages prompt loading for conversational RAG systems.
    
    This class handles:
        - Loading of system prompts from local files with fallback defaults
        - Robust error handling and logging for observability
    
    Typical usage example:
        >>> manager = PromptManager()
        >>> prompt = manager.load_prompt("app/prompts/default_prompt.txt")
    """


    def load_prompt(self, path: str) -> str:
        """
        Load a system or contextual prompt from a given file path.

        Args:
            path (str): Path to the prompt file.

        Returns:
            str: The prompt text. Returns a default fallback prompt if file not found.
        """
        try:
            prompt_path = Path(path)
            if not prompt_path.exists():
                logger.warning(f"Prompt file not found: {path}. Using default prompt.")
                return "You are a helpful assistant. Answer questions based on the provided context."

            with open(prompt_path, "r", encoding="utf-8") as file:
                prompt_text = file.read().strip()
                logger.info(f"Prompt loaded successfully from: {path}")
                return prompt_text

        except Exception as e:
            logger.error(f"Error while loading prompt file {path}: {e}")
            raise AppException(e, sys)
