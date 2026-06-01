# -*- coding: utf-8 -*-
"""
SurveyWebhookHandler - Survey Webhook Handler

Phase 9: Survey system integration with master orchestrator

Handles third-party platform callback notifications:
- answer.create: New answer submitted
- survey.complete: Survey completed
- survey.timeout: Survey timed out
- quota.reached: Quota reached

Security features:
- HMAC signature verification
- Timestamp replay attack prevention
- External ID index for optimized lookups
- PII data encryption
- Rate limiting
- Authorization verification

Design doc: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/SURVEY_ORCHESTRATOR_INTEGRATION.md
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from src.survey.models import SurveyTask, SurveyStatus, SurveyResponse
from src.survey.backends.factory import BackendFactory

logger = logging.getLogger(__name__)


class WebhookSecurityError(Exception):
    """Webhook security error"""
    pass


class RateLimitExceeded(Exception):
    """Rate limit exceeded"""
    pass


class PIIEncryption:
    """
    PII data encryption utility
    
    Uses Fernet symmetric encryption (based on AES-128-CBC)
    Production environment must configure a strong key!
    """
    
    # PII field list (fields that need masking/encryption)
    PII_FIELDS = {
        "email", "phone", "name", "address", "ip_address",
        "user_id", "respondent_id", "contact", "personal_info"
    }
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryptor
        
        Args:
            encryption_key: Encryption key (must be configured in production)
        """
        self._key = encryption_key
        self._fernet = None
        self._warned = False
        
        # Attempt to initialize Fernet encryption
        if encryption_key:
            try:
                from cryptography.fernet import Fernet
                # If key is not Fernet format, derive from password
                if len(encryption_key) == 44 and encryption_key.endswith('='):
                    self._fernet = Fernet(encryption_key.encode())
                else:
                    # Derive key from password
                    import base64
                    key_bytes = hashlib.sha256(encryption_key.encode()).digest()
                    fernet_key = base64.urlsafe_b64encode(key_bytes)
                    self._fernet = Fernet(fernet_key)
            except ImportError:
                logger.warning(
                    "cryptography library not installed. "
                    "Install with: pip install cryptography"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Fernet encryption: {e}")
    
    def encrypt_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt/mask PII fields in data
        
        Args:
            data: Raw data
            
        Returns:
            Processed data (PII fields encrypted/masked)
        """
        return self._process_data(data, encrypt=True)
    
    def decrypt_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt PII fields in data
        
        Args:
            data: Encrypted data
            
        Returns:
            Decrypted data
        """
        return self._process_data(data, encrypt=False)
    
    def _process_data(self, data: Any, encrypt: bool) -> Any:
        """Recursively process data"""
        if not isinstance(data, dict):
            return data
        
        result = {}
        for key, value in data.items():
            if key.lower() in self.PII_FIELDS or key.lower().endswith("_pii"):
                # PII field
                if encrypt:
                    result[key] = self._encrypt_value(str(value))
                else:
                    result[key] = self._decrypt_value(value)
            elif isinstance(value, dict):
                result[key] = self._process_data(value, encrypt)
            elif isinstance(value, list):
                result[key] = [self._process_data(item, encrypt) for item in value]
            else:
                result[key] = value
        
        return result
    
    def _encrypt_value(self, value: str) -> str:
        """Encrypt a single value"""
        if self._fernet:
            # Use real Fernet encryption
            encrypted = self._fernet.encrypt(value.encode())
            return f"FERNET:{encrypted.decode()}"
        
        if not self._warned:
            logger.warning(
                "Using HMAC-based pseudo-encryption. "
                "Set encryption_key and install cryptography for proper encryption!"
            )
            self._warned = True
        
        # Fallback to HMAC pseudo-encryption (development only)
        signature = hmac.new(
            self._key.encode() if self._key else b"default_key",
            value.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"ENC:{signature[:16]}:{value[:2]}***"  # Keep first 2 chars for identification
    
    def _decrypt_value(self, value: str) -> str:
        """Decrypt a single value"""
        if isinstance(value, str) and value.startswith("FERNET:"):
            # Fernet encrypted, can decrypt
            if self._fernet:
                try:
                    encrypted = value[7:].encode()  # Remove "FERNET:" prefix
                    decrypted = self._fernet.decrypt(encrypted)
                    return decrypted.decode()
                except Exception as e:
                    logger.warning(f"Failed to decrypt value: {e}")
                    return "[DECRYPT_FAILED]"
            else:
                return "[NO_DECRYPT_KEY]"
        
        if isinstance(value, str) and value.startswith("ENC:"):
            # HMAC pseudo-encryption cannot be decrypted
            return "[ENCRYPTED]"
        
        return value


class RateLimiter:
    """
    Rate limiter
    
    Uses sliding window algorithm to limit request frequency
    """
    
    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
    ):
        """
        Initialize rate limiter
        
        Args:
            max_requests: Max requests within the time window
            window_seconds: Time window (seconds)
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self, key: str) -> bool:
        """
        Check if rate limit is exceeded
        
        Args:
            key: Limit key (e.g. backend_type or IP address)
            
        Returns:
            True if allowed, False if rate limited
        """
        async with self._lock:
            now = time.time()
            cutoff = now - self._window_seconds
            
            # Clean up expired records
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > cutoff
            ]
            
            # Check if limit exceeded
            if len(self._requests[key]) >= self._max_requests:
                return False
            
            # Record this request
            self._requests[key].append(now)
            return True
    
    def get_stats(self) -> Dict[str, int]:
        """Get rate limit stats"""
        return {
            key: len(reqs) for key, reqs in self._requests.items()
        }


class SurveyWebhookHandler:
    """
    Survey Webhook handler
    
    Handles third-party platform callback notifications, supporting multiple event types.
    
    Security features:
    - HMAC signature verification prevents forged requests
    - Timestamp verification prevents replay attacks
    - External ID index for optimized lookup performance
    - PII data encryption
    - Rate limiting prevents DDoS
    - Authorization verification ensures webhooks correspond to valid tasks
    
    Usage example:
        handler = SurveyWebhookHandler(
            task_manager=task_manager,
            message_bus=message_bus,
            shared_memory=shared_memory,
            webhook_secrets={"api_tencent": "secret_key_123"},
            encryption_key="your_encryption_key",
        )
        
        # Handle webhook (with signature verification)
        result = await handler.handle_webhook(
            backend_type="api_tencent",
            event={"action": "survey.complete", "payload": {...}},
            signature="sha256=abc123...",
        )
    """
    
    # Allowed timestamp drift (seconds)
    MAX_TIMESTAMP_DRIFT = 300  # 5 minutes
    
    # Max payload size (bytes)
    MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB
    
    def __init__(
        self,
        task_manager: Any,       # SurveyTaskManager
        message_bus: Any,        # MessageBus
        shared_memory: Any,      # SharedMemory
        on_completion: Optional[Callable[[SurveyTask, List[SurveyResponse]], Any]] = None,
        webhook_secrets: Optional[Dict[str, str]] = None,  # backend_type -> secret
        enable_signature_verification: bool = True,
        encryption_key: Optional[str] = None,
        rate_limit_max: int = 100,
        rate_limit_window: int = 60,
    ):
        self._task_manager = task_manager
        self._message_bus = message_bus
        self._shared_memory = shared_memory
        self._on_completion = on_completion
        self._webhook_secrets = webhook_secrets or {}
        self._enable_signature_verification = enable_signature_verification
        
        # PII encryptor
        self._pii_encryption = PIIEncryption(encryption_key)
        
        # Rate limiter
        self._rate_limiter = RateLimiter(
            max_requests=rate_limit_max,
            window_seconds=rate_limit_window,
        )
        
        # External ID index (backend_type, external_id) -> task_id
        self._external_id_index: Dict[tuple, str] = {}
        self._index_built = False
        self._index_lock = asyncio.Lock()  # Index build lock
        
        # Event handler mapping
        self._handlers: Dict[str, Callable] = {
            "answer.create": self._handle_answer_create,
            "survey.complete": self._handle_survey_complete,
            "survey.timeout": self._handle_survey_timeout,
            "quota.reached": self._handle_quota_reached,
        }
        
        # Processed webhook IDs (replay prevention)
        self._processed_webhooks: Set[str] = set()
        self._webhook_cleanup_interval = 3600  # Cleanup every 1 hour
        
        # Statistics
        self._stats = {
            "total_webhooks": 0,
            "total_processed": 0,
            "total_failed": 0,
            "signature_failures": 0,
            "timestamp_failures": 0,
            "rate_limit_exceeded": 0,
            "authorization_failures": 0,
            "payload_size_exceeded": 0,
        }
    
    async def _build_external_id_index(self) -> None:
        """Build external ID index (thread-safe)"""
        if self._index_built:
            return
        
        async with self._index_lock:
            # Double-check
            if self._index_built:
                return
            
            try:
                all_tasks = await self._task_manager.store.list_all()
                for task in all_tasks:
                    if task.external_id:
                        key = (task.backend_type, str(task.external_id))
                        self._external_id_index[key] = task.task_id
                
                self._index_built = True
                logger.debug(f"Built external_id index with {len(self._external_id_index)} entries")
            except Exception as e:
                logger.warning(f"Failed to build external_id index: {e}")
    
    def _verify_signature(
        self,
        backend_type: str,
        event: Dict[str, Any],
        signature: Optional[str],
    ) -> bool:
        """
        Verify webhook signature
        
        Args:
            backend_type: Backend type
            event: Event data
            signature: Signature string (format: "sha256=hex_digest")
            
        Returns:
            Whether the signature is valid
        """
        if not self._enable_signature_verification:
            logger.warning("Signature verification is DISABLED - only use in development!")
            return True
        
        secret = self._webhook_secrets.get(backend_type)
        if not secret:
            # Security fix: reject request when no secret configured, prevent forgery attacks
            logger.error(f"No secret configured for backend: {backend_type}, rejecting webhook")
            return False
        
        if not signature:
            logger.warning(f"Missing signature for backend: {backend_type}")
            return False
        
        # Parse signature format
        if not signature.startswith("sha256="):
            logger.warning(f"Invalid signature format for backend: {backend_type}")
            return False
        
        provided_sig = signature[7:]  # Remove "sha256=" prefix
        
        # Compute expected signature
        payload = json.dumps(event, sort_keys=True, ensure_ascii=False)
        expected_sig = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        
        # Use constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(provided_sig, expected_sig):
            logger.warning(f"Signature mismatch for backend: {backend_type}")
            return False
        
        return True
    
    def _verify_timestamp(
        self,
        event: Dict[str, Any],
    ) -> bool:
        """
        Verify timestamp to prevent replay attacks
        
        Args:
            event: Event data
            
        Returns:
            Whether the timestamp is valid
        """
        timestamp_str = event.get("timestamp")
        if not timestamp_str:
            # No timestamp, log warning but allow through (some platforms may not support it)
            logger.warning("Webhook event missing timestamp - potential replay attack risk")
            return True
        
        try:
            event_time = datetime.fromisoformat(timestamp_str)
            now = datetime.now()
            drift = abs((now - event_time).total_seconds())
            
            if drift > self.MAX_TIMESTAMP_DRIFT:
                logger.warning(f"Webhook timestamp drift too large: {drift}s")
                return False
            
            return True
        except (ValueError, TypeError) as e:
            # Security fix: reject request on invalid timestamp format
            logger.warning(f"Invalid timestamp format: {e}")
            return False
    
    def _validate_payload_size(self, event: Dict[str, Any]) -> bool:
        """
        Validate payload size
        
        Args:
            event: Event data
            
        Returns:
            Whether within allowed range
        """
        try:
            payload_size = len(json.dumps(event, ensure_ascii=False))
            if payload_size > self.MAX_PAYLOAD_SIZE:
                logger.warning(f"Payload size {payload_size} exceeds limit {self.MAX_PAYLOAD_SIZE}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to validate payload size: {e}")
            return False
    
    def _validate_input(self, payload: Dict[str, Any], required_fields: List[str]) -> bool:
        """
        Validate input data
        
        Args:
            payload: Payload data
            required_fields: Required field list
            
        Returns:
            Whether valid
        """
        if not isinstance(payload, dict):
            return False
        
        for field in required_fields:
            if field not in payload:
                logger.warning(f"Missing required field: {field}")
                return False
        
        return True
    
    async def _check_authorization(
        self,
        backend_type: str,
        external_id: str,
    ) -> Optional[SurveyTask]:
        """
        Authorization check: verify webhook corresponds to a valid task
        
        Args:
            backend_type: Backend type
            external_id: External survey ID
            
        Returns:
            Corresponding task object, or None if invalid
        """
        task = await self._find_task_by_external_id(backend_type, external_id)
        
        if not task:
            logger.warning(
                f"Authorization failed: no task found for "
                f"backend={backend_type}, external_id={external_id}"
            )
            return None
        
        # Check if task status allows webhook processing
        if task.status == SurveyStatus.COMPLETED:
            logger.warning(f"Task {task.task_id} already completed, ignoring webhook")
            return None
        
        if task.status == SurveyStatus.FAILED:
            logger.warning(f"Task {task.task_id} already failed, ignoring webhook")
            return None
        
        return task
    
    async def handle_webhook(
        self,
        backend_type: str,
        event: Dict[str, Any],
        signature: Optional[str] = None,
        webhook_id: Optional[str] = None,
    ) -> bool:
        """
        Handle webhook event
        
        Args:
            backend_type: Backend type (e.g. "api_tencent")
            event: Event data
                {
                    "action": "survey.complete",
                    "payload": {...},
                    "timestamp": "2026-04-15T10:00:00",
                }
            signature: Signature string (format: "sha256=hex_digest")
            webhook_id: Optional unique webhook ID (for replay prevention)
            
        Returns:
            Whether processing succeeded
        """
        self._stats["total_webhooks"] += 1
        
        # 0. Check for replay (if webhook_id provided)
        if webhook_id:
            if webhook_id in self._processed_webhooks:
                logger.warning(f"Duplicate webhook detected: {webhook_id}")
                return False
            self._processed_webhooks.add(webhook_id)
        
        # 1. Rate limit check
        if not await self._rate_limiter.check_rate_limit(backend_type):
            self._stats["rate_limit_exceeded"] += 1
            self._stats["total_failed"] += 1
            logger.warning(f"Rate limit exceeded for backend: {backend_type}")
            raise RateLimitExceeded(f"Rate limit exceeded for {backend_type}")
        
        # 2. Validate payload size
        if not self._validate_payload_size(event):
            self._stats["payload_size_exceeded"] += 1
            self._stats["total_failed"] += 1
            raise WebhookSecurityError("Payload size exceeds limit")
        
        # 3. Verify signature
        if not self._verify_signature(backend_type, event, signature):
            self._stats["signature_failures"] += 1
            self._stats["total_failed"] += 1
            raise WebhookSecurityError("Invalid webhook signature")
        
        # 4. Verify timestamp
        if not self._verify_timestamp(event):
            self._stats["timestamp_failures"] += 1
            self._stats["total_failed"] += 1
            raise WebhookSecurityError("Webhook timestamp expired")
        
        action = event.get("action", "")
        payload = event.get("payload", {})
        
        # 5. Validate action
        if not action:
            logger.warning("Missing action in webhook event")
            self._stats["total_failed"] += 1
            return False
        
        handler = self._handlers.get(action)
        if not handler:
            logger.warning(f"Unknown webhook action: {action}")
            self._stats["total_failed"] += 1
            return False
        
        try:
            result = await handler(backend_type, payload)
            
            if result:
                self._stats["total_processed"] += 1
            else:
                self._stats["total_failed"] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling webhook {action}: {e}")
            self._stats["total_failed"] += 1
            return False
    
    async def _handle_answer_create(
        self,
        backend_type: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Handle new answer submission event
        
        Updates survey task collection progress
        """
        # Input validation
        if not self._validate_input(payload, ["survey_id"]):
            return False
        
        external_id = payload.get("survey_id")
        if not external_id:
            return False
        
        # Authorization check
        task = await self._check_authorization(backend_type, str(external_id))
        if not task:
            self._stats["authorization_failures"] += 1
            return False
        
        # Update progress
        task.collected_count += 1
        
        # Save
        await self._task_manager.store.save(task)
        
        logger.debug(
            f"Survey {task.task_id} progress updated: "
            f"collected={task.collected_count}/{task.target_count}"
        )
        
        return True
    
    async def _handle_survey_complete(
        self,
        backend_type: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Handle survey completion event
        
        Key flow:
        1. Lookup task by external_id (authorization check)
        2. Fetch complete results
        3. Encrypt PII data
        4. Store to SharedMemory
        5. Publish to MessageBus
        """
        # Input validation
        if not self._validate_input(payload, ["survey_id"]):
            return False
        
        external_id = payload.get("survey_id")
        if not external_id:
            return False
        
        # Authorization check
        task = await self._check_authorization(backend_type, str(external_id))
        if not task:
            self._stats["authorization_failures"] += 1
            return False
        
        try:
            # Fetch complete results
            backend = BackendFactory.get_or_create(backend_type)
            responses = await backend.get_results(external_id)
            
            # Update task status
            task.status = SurveyStatus.COMPLETED
            task.completed_at = datetime.now()
            task.collected_count = len(responses)
            task.valid_count = sum(1 for r in responses if r.is_valid)
            
            await self._task_manager.store.save(task)
            
            # Prepare result data (encrypt PII)
            responses_data = [r.to_dict() for r in responses[:100]]
            encrypted_responses = self._pii_encryption.encrypt_data(
                {"responses": responses_data}
            )
            
            result_key = f"survey_result.{task.task_id}"
            result_data = {
                "task_id": task.task_id,
                "parent_task_id": task.parent_task_id,
                "parent_phase": task.parent_phase,
                "collected_count": len(responses),
                "valid_count": task.valid_count,
                "completed_at": task.completed_at.isoformat(),
                "responses": encrypted_responses.get("responses", responses_data),
                "total_responses": len(responses),
                "pii_encrypted": True,  # Mark PII as encrypted
            }
            
            if self._shared_memory:
                await self._shared_memory.write(result_key, result_data)
            
            # Publish completion event to MessageBus (without PII)
            if self._message_bus and task.callback_topic:
                from src.core.communication import Event
                
                await self._message_bus.publish(
                    task.callback_topic,
                    Event(
                        type="survey.completed",
                        data={
                            "task_id": task.task_id,
                            "parent_task_id": task.parent_task_id,
                            "collected_count": len(responses),
                            "valid_count": task.valid_count,
                        },
                        source="SurveyWebhookHandler",
                    )
                )
            
            # Execute callback
            if self._on_completion:
                try:
                    await self._on_completion(task, responses)
                except Exception as e:
                    logger.error(f"Completion callback failed: {e}")
            
            logger.info(
                f"Survey {task.task_id} completed via webhook "
                f"(collected={len(responses)}, valid={task.valid_count}, pii_encrypted=True)"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing survey completion: {e}")
            return False
    
    async def _handle_survey_timeout(
        self,
        backend_type: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Handle survey timeout event
        
        Third-party platform reports survey timeout
        """
        # Input validation
        if not self._validate_input(payload, ["survey_id"]):
            return False
        
        external_id = payload.get("survey_id")
        if not external_id:
            return False
        
        # Authorization check
        task = await self._check_authorization(backend_type, str(external_id))
        if not task:
            self._stats["authorization_failures"] += 1
            return False
        
        # Update status
        task.status = SurveyStatus.TIMEOUT
        task.completed_at = datetime.now()
        task.error_message = "Backend reported timeout"
        
        await self._task_manager.store.save(task)
        
        # Publish timeout event
        if self._message_bus and task.callback_topic:
            from src.core.communication import Event
            
            await self._message_bus.publish(
                task.callback_topic,
                Event(
                    type="survey.timeout",
                    data={
                        "task_id": task.task_id,
                        "parent_task_id": task.parent_task_id,
                    },
                    source="SurveyWebhookHandler",
                )
            )
        
        logger.warning(f"Survey {task.task_id} timed out (reported by backend)")
        
        return True
    
    async def _handle_quota_reached(
        self,
        backend_type: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Handle quota reached event
        
        Triggered when collected samples reach the target
        """
        # Input validation
        if not self._validate_input(payload, ["survey_id"]):
            return False
        
        external_id = payload.get("survey_id")
        if not external_id:
            return False
        
        quota_type = payload.get("quota_type", "total")
        
        # Authorization check
        task = await self._check_authorization(backend_type, str(external_id))
        if not task:
            self._stats["authorization_failures"] += 1
            return False
        
        # Publish quota reached event
        if self._message_bus and task.callback_topic:
            from src.core.communication import Event
            
            await self._message_bus.publish(
                task.callback_topic,
                Event(
                    type="survey.quota_reached",
                    data={
                        "task_id": task.task_id,
                        "parent_task_id": task.parent_task_id,
                        "quota_type": quota_type,
                        "collected_count": task.collected_count,
                    },
                    source="SurveyWebhookHandler",
                )
            )
        
        logger.info(
            f"Survey {task.task_id} quota reached: "
            f"type={quota_type}, collected={task.collected_count}"
        )
        
        return True
    
    async def _find_task_by_external_id(
        self,
        backend_type: str,
        external_id: str,
    ) -> Optional[SurveyTask]:
        """
        Find task by external ID
        
        Uses index for optimized lookup performance (O(1) instead of O(n))
        """
        # Ensure index is built
        await self._build_external_id_index()
        
        # Lookup from index
        key = (backend_type, str(external_id))
        task_id = self._external_id_index.get(key)
        
        if task_id:
            # Load task from storage
            task = await self._task_manager.store.load(task_id)
            if task:
                return task
        
        # Index miss, fall back to scan
        logger.debug(f"Index miss for ({backend_type}, {external_id}), falling back to scan")
        all_tasks = await self._task_manager.store.list_all()
        
        for task in all_tasks:
            if task.backend_type == backend_type and str(task.external_id) == str(external_id):
                # Update index
                async with self._index_lock:
                    self._external_id_index[key] = task.task_id
                return task
        
        return None
    
    def rebuild_index(self) -> None:
        """Force rebuild index (takes effect on next lookup)"""
        self._index_built = False
        self._external_id_index.clear()
    
    def register_handler(
        self,
        action: str,
        handler: Callable,
    ) -> None:
        """
        Register custom event handler
        
        Args:
            action: Event type
            handler: Handler function
        """
        self._handlers[action] = handler
        logger.info(f"Registered custom webhook handler for: {action}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            **self._stats,
            "supported_actions": list(self._handlers.keys()),
            "index_size": len(self._external_id_index),
            "rate_limiter_stats": self._rate_limiter.get_stats(),
            "processed_webhooks_count": len(self._processed_webhooks),
        }


# Global singleton
_webhook_handler: Optional[SurveyWebhookHandler] = None


def get_webhook_handler(
    webhook_secrets: Optional[Dict[str, str]] = None,
    enable_signature_verification: bool = True,
    encryption_key: Optional[str] = None,
) -> SurveyWebhookHandler:
    """
    Get global webhook handler
    
    Args:
        webhook_secrets: Backend secret mapping {"api_tencent": "secret_key"}
        enable_signature_verification: Whether to enable signature verification
        encryption_key: PII encryption key
    """
    global _webhook_handler
    if _webhook_handler is None:
        from src.survey.task_manager import get_task_manager
        from src.core.communication import SharedMemory, MessageBus
        
        _webhook_handler = SurveyWebhookHandler(
            task_manager=get_task_manager(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
            webhook_secrets=webhook_secrets,
            enable_signature_verification=enable_signature_verification,
            encryption_key=encryption_key,
        )
    return _webhook_handler