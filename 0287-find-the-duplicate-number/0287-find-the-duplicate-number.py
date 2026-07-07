class Solution:
    def findDuplicate(self, nums: List[int]) -> int:
        n = len(nums) - 1

        left, right = 1, n
        result = -1 

        while left <= right:
            mid = (left + right) // 2

            # Count how many numbers are <= mid
            count = sum(1 for num in nums if num <= mid)

            # Feasible? There should be 3 number in the list that is <= 3, assume no duplicate
            # 1, 2, 3, 4
            # If count > mid, lower mid  to find that number
            if count > mid:
                result = mid
                right = mid - 1
            else:
                left = mid + 1
        return result
