class Solution:
    def generateParenthesis(self, n: int) -> List[str]:
        result = []

        def backtrack(open_count, close_count, current):
            # A complete valid combination has 2 * n characters
            if len(current) == n * 2:
                result.append(current)
                return

            # Can still add an opening parenthesis
            if open_count < n:
                backtrack(open_count + 1, close_count, current + "(")
            
            # Can only close something that was already opened
            if close_count < open_count:
                backtrack(open_count, close_count + 1, current + ")")

        
        backtrack(0, 0, "")
        return result       