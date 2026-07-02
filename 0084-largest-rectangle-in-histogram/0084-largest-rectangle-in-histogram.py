class Solution:
    def largestRectangleArea(self, heights: List[int]) -> int:
        stack = []
        result = float("-inf")

        for i, h in enumerate(heights):
            # Assume this bar can only start at its own position for now.
            start = i

            while stack and stack[-1][1] > h:
                index, height = stack.pop()
                width = i - index
                result = max(result, height * width)
                start = index 
                # current bar can reach all the way back to `index`
            stack.append((start, h))

        # Any bar left on the stack was never blocked on its right side,
        # so it extends all the way to the end of the histogram.
        for i, height in stack:
            # Here `i` is the stored start index, so (len - i) is the full width.
            result = max(result, height * (len(heights) - i))
        return result