'''
stack:
'''
class Solution:
    def isValid(self, s: str) -> bool:
        stack = []
        closeToOpen = {")": "(",
                       "]": "[",
                       "}": "{" }
        for char in s:
            # If open bracket
            if char not in closeToOpen:
                stack.append(char)
            # If close bracket
            else:
                if stack and stack[-1] == closeToOpen[char]:
                    stack.pop()
                else:
                    return False
        if stack:
            return False
        return True