"""Circuit breaker pattern for system stability."""
import time
from enum import Enum
from typing import Callable, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    """Circuit breaker for fault tolerance."""
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Exception = Exception
    ):
        """
        Args:
            name: Circuit breaker name
            failure_threshold: Failures before opening
            recovery_timeout: Seconds to wait before half-open
            expected_exception: Exception type to catch
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.success_count = 0
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"🗔️ [{self.name}] Circuit breaker: HALF_OPEN")
            else:
                raise CircuitBreakerOpen(
                    f"🗔️ Circuit breaker '{self.name}' is OPEN. Service unavailable."
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        
        except self.expected_exception as e:
            self._on_failure()
            if self.state == CircuitState.OPEN:
                raise CircuitBreakerOpen(
                    f"🗔️ Circuit breaker '{self.name}' opened after {self.failure_count} failures"
                ) from e
            raise
    
    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"🗔️ [{self.name}] Circuit breaker: HALF_OPEN")
            else:
                raise CircuitBreakerOpen(
                    f"🗔️ Circuit breaker '{self.name}' is OPEN. Service unavailable."
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        
        except self.expected_exception as e:
            self._on_failure()
            if self.state == CircuitState.OPEN:
                raise CircuitBreakerOpen(
                    f"🗔️ Circuit breaker '{self.name}' opened after {self.failure_count} failures"
                ) from e
            raise
    
    def _on_success(self):
        """Handle successful call."""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 2:  # 2 successful calls to close
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info(f"✅ [{self.name}] Circuit breaker: CLOSED (recovered)")
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.success_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            logger.warning(f"❌ [{self.name}] Recovery attempt failed, opening circuit")
            self.state = CircuitState.OPEN
        
        elif self.failure_count >= self.failure_threshold:
            logger.error(
                f"🗔️ [{self.name}] Circuit breaker opened after "
                f"{self.failure_count} failures"
            )
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Check if recovery timeout has elapsed."""
        if not self.last_failure_time:
            return True
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
    
    def reset(self):
        """Manually reset circuit breaker."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        logger.info(f"🔄 [{self.name}] Circuit breaker manually reset")
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
        }

class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass

class RetryPolicy:
    """Retry policy with exponential backoff."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)
    
    def should_retry(self, attempt: int, exception: Exception) -> bool:
        """Determine if should retry."""
        if attempt >= self.max_retries:
            return False
        
        # Don't retry on circuit breaker open
        if isinstance(exception, CircuitBreakerOpen):
            return False
        
        return True

def with_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60
):
    """Decorator for circuit breaker pattern."""
    cb = CircuitBreaker(
        name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout
    )
    
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            return await cb.call_async(func, *args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            return cb.call(func, *args, **kwargs)
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

# Global circuit breakers
circuit_breakers = {
    "database": CircuitBreaker("database", failure_threshold=5, recovery_timeout=60),
    "redis": CircuitBreaker("redis", failure_threshold=5, recovery_timeout=30),
    "crawler": CircuitBreaker("crawler", failure_threshold=10, recovery_timeout=120),
    "renderer": CircuitBreaker("renderer", failure_threshold=3, recovery_timeout=90),
}
