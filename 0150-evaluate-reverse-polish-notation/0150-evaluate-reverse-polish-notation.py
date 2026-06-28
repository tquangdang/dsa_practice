# When encounter an operation, do the operation on the first 2 number on the stack
class Solution:
    def evalRPN(self, tokens: List[str]) -> int:
        stack = []
        for char in tokens:
            if char in {"+", "-", "*", "/"}:
                right = stack.pop()
                left = stack.pop()
                if char == "+":
                    stack.append(left + right)
                elif char == "-":
                    stack.append(left - right)
                elif char == "*":
                    stack.append(left * right)
                else:
                    stack.append(int(left / right))
            else:
                stack.append(int(char))
        return stack[-1]