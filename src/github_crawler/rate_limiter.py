import time

class TokenBucket:
    def __init__(self, capacity: float, fill_rate: float):
        self.capacity = float(capacity)
        self.fill_rate = float(fill_rate)
        self.tokens = float(capacity)
        self.last_fill = time.time()

    def get_token(self) -> bool:
        now = time.time()
        elapsed = now - self.last_fill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_fill = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
