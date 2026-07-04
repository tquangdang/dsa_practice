class Solution:
    def findMin(self, nums: List[int]) -> int:
        left, right = 0, len(nums) - 1

        # Edge case: List is already sorted
        if nums[left] < nums[right]:
            return nums[left]
        
        while left < right:
            mid = (left + right) // 2
            if nums[mid] < nums[right]:
                right = mid
            else:
                left = mid + 1
        return nums[left]
