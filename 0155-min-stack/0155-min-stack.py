class MinStack:

    def __init__(self):
        self.stack = []
        self.local_min = float("inf")

    def push(self, value: int) -> None:
        if value < self.local_min:
            self.local_min = value
        self.stack.append((value, self.local_min))

    def pop(self) -> None:
        self.stack.pop()
        if self.stack:
            self.local_min = self.stack[-1][1]
        else:
            self.local_min = float("inf")
            
    def top(self) -> int:
        return self.stack[-1][0]

    def getMin(self) -> int:
        return self.stack[-1][1]


# Your MinStack object will be instantiated and called as such:
# obj = MinStack()
# obj.push(value)
# obj.pop()
# param_3 = obj.top()
# param_4 = obj.getMin()