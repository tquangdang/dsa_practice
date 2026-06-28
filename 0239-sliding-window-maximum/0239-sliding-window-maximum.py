class Solution:
    def maxSlidingWindow(self, nums: List[int], k: int) -> List[int]:
        result = []
        left, right = 0, 0
        queue = deque()

        while right < len(nums):
            while queue and nums[queue[-1]] < nums[right]:
                queue.pop()
            queue.append(right)

             # Remove index that is no longer inside [l, r].
            if left > queue[0]:
                queue.popleft()
            
            # The window is full: its max is at q[0].
            if right + 1 >= k:
                result.append(nums[queue[0]])
                left += 1
            right += 1
        
        return result