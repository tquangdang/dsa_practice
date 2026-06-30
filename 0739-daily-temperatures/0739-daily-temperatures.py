class Solution:
    def dailyTemperatures(self, temperatures: List[int]) -> List[int]:
        # Decreasing stack?
        stack = []
        result = [0] * len(temperatures)
        
        for i in range(len(temperatures)):
            if not stack or temperatures[i] <= temperatures[stack[-1]]:
                stack.append(i)
            else:
                while stack and temperatures[i] > temperatures[stack[-1]]:
                    temp_index = stack.pop()
                    result[temp_index] = i - temp_index
                stack.append(i)
        return result


