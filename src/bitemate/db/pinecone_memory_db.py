import os
import sys
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

# Third-party imports
from pinecone import Pinecone
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

# Internal imports
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

# Load environment variables
load_dotenv()

# Constants
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

class UserProfileMemory:
    """
    Manages persistent 'Core Memory' for user profiles and preferences using Pinecone.

    This class is designed to store high-level user attributes (Dietary restrictions,
    flavor preferences, kitchen equipment) that must be recalled in every session.
    
    Attributes:
        index_name (str): The name of the Pinecone index.
        embedder (HuggingFaceEmbeddings): Model used for vectorization.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initializes the Pinecone client and Embedding model based on configuration.

        Args:
            config_path (Optional[str]): Path to params.yaml.
        """
        # 1. Configuration Loading
        try:
            path_to_load = config_path if config_path else CONFIG_REL_PATH
            self.params = load_params(path_to_load)
            
            self.memory_params = self.params.get("pinecone_memory_params", {})
            self.log_path = self.memory_params.get("file_path", "pinecone_memory.log")
            self.index_name = os.getenv("PINECONE_MEMORY_INDEX_NAME")
            self.api_key = os.getenv("PINECONE_API_KEY")
            
            # Embedding Model Config
            self.model_name = self.memory_params.get("embedding_model", "all-MiniLM-L6-v2")

        except Exception as e:
            # Fallback logger if config fails
            print(f"CRITICAL: Config load failed. {e}")
            sys.exit(1)

        # 2. Logger Setup
        self.logger = setup_logger("UserProfileMemory", self.log_path)

        # 3. Validation
        if not self.api_key or not self.index_name:
            error_msg = "Missing PINECONE_API_KEY or PINECONE_MEMORY_INDEX_NAME in environment."
            self.logger.critical(error_msg)
            raise AppException(error_msg, sys)

        # 4. Service Initialization
        try:
            self.logger.info("Initializing Pinecone Client...")
            self.pc = Pinecone(api_key=self.api_key)
            self.index = self.pc.Index(self.index_name)
            
            self.logger.info(f"Loading Embedding Model: {self.model_name}")
            self.embedder = HuggingFaceEmbeddings(model_name=self.model_name)
            
        except Exception as e:
            self.logger.exception("Failed to initialize external services (Pinecone/HF).")
            raise AppException(f"Memory Service Initialization Failed: {e}", sys)

    def _generate_memory_id(self, user_id: str, text: str) -> str:
        """Generates a deterministic ID for idempotency."""
        raw_string = f"{user_id}-{text.lower().strip()}"
        return hashlib.md5(raw_string.encode()).hexdigest()

    def embed_text(self, text: str) -> List[float]:
        """
        Generates vector embeddings for a given text.
        
        Raises:
            AppException: If the embedding model fails.
        """
        try:
            # Clean text before embedding
            clean_text = text.replace("\n", " ").strip()
            return self.embedder.embed_query(clean_text)
        except Exception as e:
            self.logger.error(f"Embedding generation failed for text: '{text[:20]}...'")
            raise AppException(f"Embedding Error: {e}", sys)

    def add_user_preference(
        self, 
        user_id: str, 
        text: str, 
        category: str = "general_preference",
        medical_info: str = "not_mentioned"
    ) -> str:
        """
        Stores a specific user preference into the Core Memory.

        Args:
            user_id (str): Unique user identifier.
            text (str): The preference text (e.g., "I am allergic to peanuts").
            category (str): Classification (e.g., 'dietary_restriction', 'appliance', 'goal').
            medical_info (str): The medical preference information (e.g., "I am diabetic patient")

        Returns:
            str: The ID of the stored memory.
        """
        try:
            vector = self.embed_text(text)
            memory_id = self._generate_memory_id(user_id, text)
            
            # ISO 8601 Timestamp
            created_at = datetime.now(timezone.utc).isoformat()

            metadata = {
                "user_id": user_id,
                "text": text,
                "category": category,
                "medical_info": medical_info,
                "created_at": created_at,
                "type": "core_profile" # Distinguishes profile vs chat history
            }

            self.index.upsert(
                vectors=[{
                    "id": memory_id,
                    "values": vector,
                    "metadata": metadata
                }]
            )

            self.logger.info(
                f"Preference stored. [User: {user_id}, Category: {category}]"
            )
            return memory_id

        except Exception as e:
            self.logger.error(f"Failed to upsert memory for user {user_id}: {e}")
            raise AppException(f"Memory Storage Error: {e}", sys)

    def get_relevant_profile(
        self, 
        user_id: str, 
        query_context: str, 
        categories: Optional[List[str]] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves relevant profile information based on the current context.

        Args:
            user_id (str): The user ID.
            query_context (str): The context (e.g., "planning a dinner for 2").
            categories (List[str], optional): Filter by categories (e.g., ['allergy']).
            top_k (int): Number of memories to fetch.

        Returns:
            List[Dict]: List of memory objects with metadata.
        """
        try:
            vector = self.embed_text(query_context)

            # Build Metadata Filter
            filter_dict = {"user_id": user_id, "type": "core_profile"}
            
            if categories:
                # Pinecone syntax for "in list"
                filter_dict["category"] = {"$in": categories}

            results = self.index.query(
                vector=vector,
                top_k=top_k,
                include_metadata=True,
                filter=filter_dict
            )

            matches = []
            for match in results.get("matches", []):
                if match.score > 0.75:  # Threshold to avoid irrelevant noise
                    matches.append(match["metadata"])

            self.logger.debug(f"Retrieved {len(matches)} profile memories for user {user_id}.")
            return matches

        except Exception as e:
            self.logger.error(f"Memory retrieval failed: {e}")
            raise AppException(f"Memory Retrieval Error: {e}", sys)

    def delete_preference(self, user_id: str, text: str):
        """Removes a specific preference if the user changes their mind."""
        try:
            memory_id = self._generate_memory_id(user_id, text)
            self.index.delete(ids=[memory_id], filter={"user_id": user_id})
            self.logger.info(f"Deleted preference: {memory_id}")
        except Exception as e:
            self.logger.error(f"Failed to delete memory: {e}")
            raise AppException(e, sys)

if __name__=="__main__":
    user_profile = UserProfileMemory()