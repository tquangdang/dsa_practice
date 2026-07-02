'''
For each bar i, the largest rectangle using bar i as the height 
stretches left and right until it hits a bar shorter than heights[i]. 
In other words, treat each height as a bottleneck of its maximum area rectangle it can creates
'''

class Solution:
    def largestRectangleArea(self, heights: List[int]) -> int:
        # Stack keeps bars in increasing height order.
        # Each entry is (start, height), where `start` is the LEFTMOST index
        # this bar can stretch back to — not necessarily where the bar sits.
        stack = []
        max_area = 0

        for i, h in enumerate(heights):
            # Assume this bar can only start at its own position for now.
            start = i

            # While the bar on top is TALLER than the current one, it's blocked:
            # it can't extend past index i, so finalize its rectangle now.
            while stack and stack[-1][1] > h:
                index, height = stack.pop()

                # Width runs from where that bar started up to (but not including) i.
                width = i - index
                max_area = max(max_area, height * width)

                # KEY STEP: every popped bar was taller than h, so the whole
                # span from `index` to i was at least height h. That means the
                # current bar can reach all the way back to `index` — it inherits
                # the left reach of the bars it just knocked out.
                start = index

            # Push the current bar with its (possibly inherited) start index.
            stack.append((start, h))

        # Any bar left on the stack was never blocked on its right side,
        # so it extends all the way to the end of the histogram.
        for i, height in stack:
            # Here `i` is the stored start index, so (len - i) is the full width.
            max_area = max(max_area, height * (len(heights) - i))

        return max_area